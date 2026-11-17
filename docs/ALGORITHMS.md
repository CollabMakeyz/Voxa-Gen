# Algoritmos

Todas as cadeias processam o sample na **taxa original** e reamostram **uma única vez** para a
taxa de exportação (soxr). Em todas as cadeias o pitch alvo é exato: a f0 de destino é plana
sobre a nota e nunca há variação aleatória de afinação.

## Afinação

`f = A4 · 2^((midi − 69 + desvio_temperamento/100) / 12)`. Os temperamentos *just* (5-limit)
e *pitagórico* são tabelas de desvio em cents relativas à *root*; *custom* usa 12 offsets.

## Natural (e Lab)

Implementação própria sobre o vocoder **WORLD** (pyworld):

1. **f0**: Harvest (robusto para voz) com refinamento StoneMask, quadros de 5/2,5/1 ms
   (*Processing quality*). Limpeza da trilha: remove "voicing" com menos de 30 ms, corrige
   saltos de oitava contra uma mediana móvel e preenche lacunas não sonoras com menos de 25 ms.
2. **Gate de vozeamento**: a aperiodicidade D4C na banda de 100 a 1500 Hz fica perto de 1,0
   para ruído e perto de 0,01 para voz. Quadros com valor acima de 0,5 são marcados como não
   sonoros, o que evita "afinar" ruído.
3. **Envelope e aperiodicidade**: CheapTrick + D4C **por canal**, todos com a mesma trilha de
   f0. O stereo é preservado e a imagem fica coerente.
4. **f0 de destino**: o desvio da fonte em relação ao seu centro é dividido em parte lenta
   (média de 150 ms, *drift*) e rápida (vibrato/jitter). *Pitch Correction* remove o drift.
   *Humanization* mantém a parte rápida. O que é mantido fica limitado a ±N cents e é forçado
   a **média zero**, então a altura percebida é exatamente a nota.
5. **Formantes**: o eixo de frequência do envelope é escalado por `razão^(1 − preservação)`.
   Com 100% os formantes ficam onde estavam (mesma voz em qualquer altura); com 0% eles
   acompanham o pitch.
6. **Smoothing**: suavização temporal (gaussiana) do envelope em log e da aperiodicidade.
7. **Artifact Reduction**: filtro de mediana temporal na aperiodicidade e piso de
   aperiodicidade crescente acima de 3 kHz (menos "buzz" metálico). Também limita os saltos
   do envelope entre quadros, com reancoragem lenta (menos *warble*).
8. **Síntese WORLD**: a duração fica idêntica à da fonte (ou ao alvo, no *time-stretch*, em
   que os parâmetros por quadro são interpolados no tempo).
9. **Híbrido sonoro/não sonoro**: consoantes, respirações e silêncios não têm pitch, então
   vêm do **original alinhado no tempo**, com bordas suavizadas (*Voiced/Unvoiced
   Processing*).
10. **Transient Control**: ataques detectados por fluxo espectral recebem o original numa
    janela curta (com peso menor quando o ataque é sonoro, para não vazar o pitch da fonte).
11. **Wet/Dry** entre a saída refinada e a ressíntese simples (as duas no pitch alvo, então
    nunca desafina) e **compensação de ganho** por RMS ativo (máximo de ±12 dB).

No modo automático (padrão), a faixa de busca de pitch (40 a 1100 Hz) e todos os ajustes
recomendados vêm prontos.

## Robot

Perfil de velocidade. A f0 vem do DIO + StoneMask (muito mais rápido que o Harvest), com
quadros de 10 ms. Há uma só análise e síntese, no sinal *mid*, e o stereo é reconstruído
pela razão de nível de cada canal. Não há estágios de refinamento e a reamostragem é MQ.
A f0 de destino continua plana e exata, e os formantes são preservados. No teste
`test_robot_is_faster_than_natural`, o Robot fica em torno de 5x mais rápido.

## Legacy

Cadeia clássica modelada no **comportamento** do Chromatic Scale Generator Deluxe, com
implementação independente e nenhum código copiado:

- converte para mono e reamostra para 48 kHz pelo Praat (`Resample`, precisão 1);
- `To Manipulation` (passo 0,03 s, pitch de 20 a 1200 Hz), *pitch tier* substituído por uma
  linha plana no alvo, ressíntese *overlap-add* (PSOLA);
- pós-processamento na ordem clássica: fade → pad/trim → normalização de pico por nota (0,98).

Não havia um exportador anterior do Voxa GEN no histórico. O Legacy **não** afirma reproduzir
bit a bit uma versão histórica: é uma cadeia clássica documentada e congelada
(`LEGACY_CHAIN_VERSION = 1`), que não recebe as melhorias dos outros modos.

## Detecção de pitch (Sample Manager)

Autocorrelação do Praat (`to_pitch_ac`, *very accurate*). Medem-se a mediana, o desvio em
cents, a fração de quadros sonoros, a dispersão interquartil em cents e a força média. O
resultado é **não confiável** (com motivo) quando menos de 25% dos quadros são sonoros ou
quando a dispersão passa de 120 cents.

## Pipeline compartilhado: preview = exportação

`plan_notes → NoteRenderer (engine + reamostragem + canais, cache em disco por chave de
conteúdo) → post_process_note (fit, fades, normalização por nota) → compute_gains
(normalização global, master volume, proteção contra clipping) → assemble_positions`.

O Chrom Preview e a exportação chamam exatamente essas funções com a mesma configuração.
A chave do cache inclui o hash do conteúdo do sample, os parâmetros do engine, o pitch alvo,
a taxa e os canais de saída e o estiramento, então qualquer mudança relevante invalida o
render.

## Exportação e marcadores

Writer RIFF próprio, em streaming: `fmt` (PCM para 16/24 bits, IEEE float + `fact` para 32
bits), `data`, `cue ` (um ponto por nota, `dwPosition = dwSampleOffset = frame inicial`) e
`LIST/adtl` com `labl` (nome da nota). Os tamanhos são corrigidos no fechamento e chunks
ímpares recebem byte de padding. As posições dos marcadores são calculadas na taxa de saída
e consideram a duração de cada nota e o gap. A validação relê cada arquivo e compara posições
e conteúdo com o render.

## Tolerância de pitch nos testes

Os testes exigem erro **< 5 cents** em sinais estáveis (vogal sintética com formantes e com
25 cents de vibrato na entrada), medidos de forma independente pelo Praat. Os resultados
observados ficam abaixo de 0,15 cent nos três modos. Ruído puro é reportado como "sem
conteúdo sonoro", nunca afinado.

## Efeitos do LAB (opcionais)

Todos trabalham em float64, na taxa de exportação, e mantêm o tamanho do áudio. Nenhum é aplicado
sem a chave **Use effects** ligada; a cadeia faz parte da chave do cache, então preview, exportação e
lote produzem o mesmo resultado.

| Efeito | Implementação |
| --- | --- |
| Distortion | curvas tanh / clip / wavefold / fuzz assimétrico com oversampling 4× (`resample_poly`), DC block, passa-baixa Butterworth de tom |
| Saturation | tanh com bias (válvula: harmônicos pares) ou joelho suave + leve passa-baixa (fita), oversampling 2×, RMS ativo igualado à entrada |
| Formant Shift | WORLD (DIO + StoneMask, CheapTrick, D4C) por canal; o envelope espectral é escalado em frequência (`warp_envelope`) e o f0 fica igual |
| Tremolo | ganho `1 − d·(0,5 − 0,5·lfo)`; onda quadrada com bordas suaves (sem cliques); fase por canal |
| Vibrato | linha de atraso modulada com interpolação fracionária; amplitude `A = (2^(c/1200) − 1)/ω`, então o desvio máximo é exatamente `c` cents; entrada suave (onset) |
| Pitch Variation | curva aleatória suave (PCHIP) com média zero, lida como razão de leitura; seed = seed do efeito + índice da nota (determinístico) |
| BitCrusher | sample-and-hold na taxa escolhida + quantização em `2^(bits−1)` níveis |
| Double Pitch | cópia ressintetizada pelo WORLD com f0 × 2^(semitons/12) (+detune), formantes mantidos ou seguindo; soma em `level` com atraso opcional |
| Frequency Shifter | sinal analítico (Hilbert) × `e^(j2πft)`, parte real: desloca em Hz, não em razão |
| Chorus | 1–4 vozes com atraso modulado (taxas levemente diferentes, fases espalhadas), pan em estéreo |
| Phaser | cascata de all-pass de 1ª ordem calculada por blocos de 64 amostras com estado contínuo; realimentação dentro da função de transferência `B/(A − fb·B)`; nível compensado |
| Ring Modulator | multiplicação por portadora seno/triângulo/quadrada; frequência fixa ou `nota × razão` |
| Noise | branco, rosa (filtro de Paul Kellet), marrom (integrador com DC block) ou estalos; nível relativo ao RMS ativo da voz; seguidor de envelope opcional |
| EQ | biquads RBJ (shelf grave, pico, shelf agudo) + Butterworth de 2ª ordem para os cortes, em `sosfilt` |

Os testes medem o efeito no sinal: tremolo muda o envelope e não a frequência, vibrato muda a
frequência instantânea em torno da média, o frequency shifter leva 500 Hz a 700 Hz e 1000 Hz a
1200 Hz, o formant shift move o centroide espectral sem mudar o f0, e assim por diante.

## Limitações conhecidas

- Deslocamentos acima de duas oitavas aumentam a chance de artefatos (o motor avisa).
- O *time-stretch* desliga a mistura com o original (V/UV e transientes), porque o original
  não está alinhado com a nova duração.
- A avaliação de qualidade é objetiva (pitch, formantes, duração). A comparação auditiva com
  vozes reais do time deve ser feita no Lab (A/B com volume igualado).
