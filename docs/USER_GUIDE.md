# Guia de uso

> **Como a interface funciona.** Cada página é dividida em abas (em cima do painel). Cada bloco começa
> com uma frase explicando para que serve, e cada configuração tem um **“?”**. Clicar nele abre uma
> janelinha com **O que é** e **Por que usar**. Ela fica aberta até você fechar (×, Esc ou outro “?”),
> então dá pra ler com calma; dá pra arrastar e selecionar o texto. As opções avançadas ficam em blocos
> **“Advanced”** fechados. Ações menos usadas ficam no botão **“More”**.

A sidebar tem quatro áreas (atalhos Ctrl+1 … Ctrl+4):

| Área | Abas | Para quê |
| --- | --- | --- |
| **Generator** | Basic · Samples · Order · Exporting · Preview · Batch | samples, ordem, modo, exportação, fila em lote e projetos |
| **LAB** | Source & tools · Effects · Compare · Profiles | ferramentas do Natural, cadeia de efeitos, comparação A/B |
| **Appearance** | Themes · Colours · Text & layout | temas, cores, fonte, tamanho, arredondamento, densidade |
| **Settings** | General · Sounds · Notifications · Export & preview · About | idioma, sons, notificações, padrões |

Os **presets** ficam numa janela própria, aberta por **Manage presets** no Generator e no LAB.
Tudo o que você configura é salvo automaticamente e restaurado na próxima abertura.

## 1. Importar samples

- **Generator → Source → Browse…** escolhe uma pasta; todos os `.wav` dela são carregados.
- Arraste arquivos ou pastas para a área tracejada (Generator ou Sample Manager).
- O identificador de cada sample é o nome do arquivo sem extensão, em minúsculas:
  `1.wav → 1`, `a.wav → a`, `a2.wav → a2`, `Breath_Long.wav → breath_long`.
- **`a2` é outro arquivo (`a2.wav`), nunca uma variação de `a.wav`.**
- A ordenação é natural: `1, 2, 10` (nunca `1, 10, 2`) e `a, a2, a3, a10, e`.
- Os originais nunca são alterados. "Remove from session" só tira o sample do Voxa GEN.

### Aba Samples (antigo Sample Manager)

**Generator → Samples → All samples**: tabela com ID, arquivo, duração, sample rate, bit depth, canais, pitch e status.

- **Detect pitch** analisa em segundo plano (selecionados, ou todos). Quando a análise não é
  confiável (pouco conteúdo sonoro, pitch instável), aparece **"uncertain — motivo"**; o
  programa nunca inventa uma nota.
- Filtros: famílias de nomes (numerados, letras, variações, outros), arquivos ausentes,
  duplicados (conteúdo idêntico), ilegíveis, fora de uso, pitch incerto.
- **Use / skip** (ou a coluna *Use*) inclui/exclui o sample do Order System.
- **Replace…** aponta o identificador para outro arquivo (o ID é mantido).
- **Reload** relê os arquivos do disco e detecta alterações e ausências.
- Painel direito: **Audio Preview** do sample selecionado.

### Verificação de samples (Sample Analyzer)

**Generator → Samples → Check for problems → Check all samples** lê todos os arquivos (sem
alterá-los) em segundo plano e lista, para cada problema, **o que está errado e como resolver**:

| Nível | Exemplos |
| --- | --- |
| Problem | arquivo ausente, ilegível/incompatível, sample totalmente em silêncio |
| Check | clipping, silêncio demais antes/depois da voz, sample muito curto, volume 6 dB ou mais acima/abaixo dos outros, duração muito diferente das outras |
| Note | offset DC, conteúdo duplicado, sample rates ou canais misturados (são convertidos automaticamente) |

Duplo clique num resultado seleciona o sample na lista. A tabela **Technical details** mostra
pico, volume da parte cantada, silêncio antes/depois, duração, formato e amostras clipadas.

## 2. Configurações musicais

- **Start note / octave**: notação científica (C4 = dó central). O Deluxe usa a mesma
  convenção (C2 = 65,41 Hz).
- **Notes (semitones)**: quantidade de notas.
- **Reference A4**: padrão 440 Hz.
- **Temperament**: igual (12-TET), justo (5-limit), pitagórico (ambos sobre a *root*) ou
  offsets personalizados por classe de nota.
- **Retune**: desligado = os samples mantêm o pitch original.

## 3. Order System

| Modo | Comportamento |
| --- | --- |
| Sequential | ordem natural dos nomes, repetindo em ciclo |
| Shuffle | ordem aleatória; cada sample é usado uma vez por ciclo; nunca repete na virada do ciclo |
| Random | sorteio independente a cada nota (pode repetir em sequência) |
| Vocal sequence | sua própria sequência de nomes, executada exatamente na ordem |

Shuffle e Random sempre usam uma *seed*, de modo que **o preview e a exportação produzem a
mesma ordem**. Com *Fixed seed* desligado, uma nova seed é sorteada a cada abertura do app ou
em **Reroll**.

### Sequências (Visual Sequence Editor)

Aparece com o modo *Vocal sequence*.

- Digite nomes (`a e2 o`) e pressione Enter ou **Add**; **Insert** insere após a seleção.
- Clique em um sample da paleta "Available samples" para adicioná-lo.
- Arraste os elementos para reordenar; duplo clique ou F2 edita; Del remove; Ctrl+D duplica;
  Ctrl+Z / Ctrl+Y desfazem e refazem.
- Cores: borda vermelha = arquivo ausente; amarela = mapeado explicitamente; riscado = pulado.
- **Fix missing…** abre a resolução de ausentes. Para cada nome sem arquivo você escolhe
  **mapear para outro sample** ou **pular o elemento** (ou cancelar). Nada é substituído
  silenciosamente: `a2` ausente nunca vira `a` sem a sua decisão.
- Presets: Load, Save (sobrescrever), Save as, Duplicate, Restore (versão nativa), Import
  (`.json` ou `.txt`), Export.
- **Sequence preview**: toca a sequência com os samples originais ou processada pelo modo
  atual. O elemento tocando fica destacado.

**BF Classic Sequence** (preset nativo, 45 elementos, exata):

```
a e2 o e a2 o u i a o a2 e2 e u i a o i u a2 e2 u i u2 i u a a3 e2 e3 u a2 a e e2 u e2 e2 u a a2 e e2 u e2
```

## 4. Modos de exportação

- **Natural** — máxima qualidade e naturalidade; automático por padrão. *Show advanced
  controls* expõe todos os ajustes (descritos em cada controle). Presets: Clean, Expressive,
  Smooth, Ultra.
- **Robot** — perfil leve e rápido (não adiciona efeito robótico). Afinação exata.
- **Legacy** — cadeia clássica congelada para compatibilidade (mono 48 kHz, PSOLA do Praat).
- **Lab profile** — o motor Natural com as configurações do Lab.

Detalhes técnicos: [ALGORITHMS.md](ALGORITHMS.md).

## 5. LAB

1. Escolha o sample e a nota alvo (**Detected** usa a nota mais próxima do pitch detectado).
2. Ajuste as ferramentas: Pitch Correction, Humanization, Formant Preservation, Transient
   Control, Smoothing, Artifact Reduction, Voiced/Unvoiced Processing, Wet/Dry, qualidade e
   resampling. Cada ferramenta tem liga/desliga (desligada = totalmente neutralizada),
   slider, valor numérico, descrição e reset.
3. Com *Auto-render on change*, o resultado é recalculado automaticamente em segundo plano.
4. Compare **A · Original** e **B · Processed**. A troca mantém a posição e o volume é
   igualado (RMS ativo), para que diferenças de nível não influenciem a comparação.
5. Veja waveform ou espectro (A e B) e as métricas: pitch da fonte, pitch medido na saída e
   **erro em cents**, durações, tempo de processamento, frames sonoros e níveis.
6. Salve como **Lab profile** e use **Use in Generator** (o Generator passa para o modo
   *Lab profile*).
7. **Undo / Redo** (Ctrl+Z / Ctrl+Y, botões no topo do LAB) desfazem mudanças nas ferramentas,
   nos efeitos, na ordem dos efeitos e no carregamento de perfis e presets. Arrastar um slider
   conta como um passo só.

### 5.1 Efeitos (LAB → Effects)

Uma cadeia de efeitos **opcional**. Ela **nunca é aplicada sozinha**: só entra nos previews, na
exportação e na fila em lote quando você liga **Use effects in previews and exports** (no LAB)
ou **Add the LAB effects to this export** (Generator → Exporting) — é a mesma chave. Os efeitos
rodam depois do modo de exportação (Natural, Robot, Legacy ou Lab), de cima para baixo, e nunca
alteram os arquivos de sample.

| Efeito | O que muda |
| --- | --- |
| Distortion | clipping duro (soft, hard, wavefold, fuzz) com drive, tom e saída; com oversampling |
| Saturation | calor de fita/válvula; o volume é igualado ao da entrada |
| Formant Shift | timbre/tamanho da garganta, **sem** mudar a nota (análise WORLD) |
| Tremolo | **volume** periódico (rate, depth, forma, fase estéreo) |
| Vibrato | **altura** periódica em cents, com entrada suave (onset) |
| Pitch Variation | deriva **aleatória** e lenta da altura, média afinada; igual no preview e na exportação |
| BitCrusher | menos bits e sample rate menor (lo-fi) |
| Double Pitch | soma uma cópia transposta em semitons (oitava, quinta…), com detune e formantes |
| Frequency Shifter | desloca todas as frequências pelo mesmo número de **Hz** (inarmônico) |
| Chorus | cópias com atraso modulado (vozes, rate, depth, delay, abertura estéreo) |
| Phaser | entalhes que varrem o espectro (estágios, centro, feedback) |
| Ring Modulator | multiplica por uma portadora fixa ou que **segue a nota** |
| Noise | branco, rosa, marrom ou estalos de vinil, relativo à voz, opcionalmente seguindo a voz |
| EQ | low cut, low shelf, banda média (Q), high shelf, high cut |

- **Add effect** adiciona após o efeito selecionado; **Up/Down** (Ctrl+↑/↓) ou arrastar reordena;
  a caixinha de cada linha liga/desliga (bypass); **Duplicate** e **Remove** (Delete).
- **Wet / Dry** aparece nos efeitos em que faz sentido (nos outros, o próprio efeito já é uma
  mistura, como o *Level* do Double Pitch).
- **Effect presets**: 16 presets nativos em 8 categorias (Horror, Normal FNF, Robot, Retro, Monster,
  Glitch, Funny / Meme, Experimental). Load, Save as new (com categoria), e em **More**: salvar no
  preset, duplicar, renomear, apagar, restaurar o original, importar e exportar.
- **Listen: before / after**: A = modo de exportação sem efeitos, B = com a cadeia (mesmo com a
  chave desligada). A/B (ou a tecla **B**) troca na mesma posição; **Match loudness** iguala o volume.

## 6. Previews e comparação A/B

**Audio Preview** (Generator → aba Audio Preview, Sample Manager e Lab) mostra um sample
antes e depois do processamento: Original / Natural / Robot / Legacy / Lab, com A/B, loop,
seek por clique ou arraste na waveform, volume e tempo. A troca A/B (botão ou tecla **B**) mantém a
posição, o selo **Now playing** mostra qual versão está tocando e **Match loudness** (ligado por
padrão) toca A e B no mesmo volume — só no preview, nunca na exportação.

**Chrom Preview** (Generator) toca a chromatic gerada completa:

- Render em segundo plano com progresso e cancelamento. Com a variante igual ao modo de
  exportação aparece **"Same pipeline as export"**: é exatamente o que será exportado.
- Teclado cromático: clique numa tecla para ouvir a nota. A faixa verde indica nota OK,
  amarela aviso, vermelha erro e cinza sample ausente. A nota tocando fica destacada.
- Transporte: play/pause, stop, restart, loop, nota anterior e próxima, volume, posição, faixa
  de notas (*Notes x to y*) e *Play all*.
- O cache é invalidado automaticamente quando samples, ordem, pitch ou processamento mudam.
  Renders idênticos são reaproveitados (cache em disco compartilhado com a exportação).

## 7. Exportação

Configurações: sample rate (44.1/48/88.2/96 kHz ou valor personalizado entre 8000 e 384000),
bit depth (16-bit PCM com dither TPDF opcional, 24-bit PCM, 32-bit float), mono ou stereo,
normalização de pico (cromática inteira ou por nota, alvo em dBFS), fade in/out em ms, gap
entre notas, duração fixa (*pad + trim*, *pad only* que nunca corta, ou *time-stretch*),
master volume, proteção contra clipping, remoção de silêncio das fontes.

Saída padrão:

```
Voxa GEN Export/
  chromatic.wav          (com marcadores cue/labl para o Slicex)
  samples/note_001.wav … (modelo configurável: {index} {note} {pitch} {octave} {midi} {sample} {hz})
  export_info.json       (configurações, notas, posições, validação)
```

- Nada é sobrescrito sem perguntar. Se existirem arquivos com o mesmo nome, você escolhe
  entre exportar para *"Voxa GEN Export (2)"*, sobrescrever ou cancelar.
- A exportação acontece numa pasta temporária. Ela só é movida para o destino depois de
  **validada**: estrutura RIFF, formato, sample rate, canais, duração, quantidade, posição e
  rótulo dos marcadores, conteúdo amostra por amostra, ausência de clipping e todos os
  arquivos individuais.
- Cancelar não deixa nenhum arquivo para trás.
- A barra mostra a etapa, a nota atual, o progresso e o tempo decorrido. **Open folder**
  abre o resultado.

## 8. Projetos

Um **projeto** (`.vxproj`) guarda o trabalho completo — diferente de um preset, que guarda uma
configuração reutilizável. A barra no topo do Generator tem **New**, **Open** (a seta lista os
recentes), **Save** (Ctrl+S) e **Save as…**. O projeto guarda:

- os samples usados (caminho absoluto, caminho relativo ao projeto e hash do conteúdo) e quais estão em uso;
- a sequência vocal, a ordem e a seed; as configurações musicais, de pitch e de afinação;
- o modo de exportação e as configurações de Natural, Robot, Legacy e LAB;
- a cadeia de efeitos e se ela está ligada; os presets usados; as configurações de exportação;
- a fila em lote.

Ao abrir, cada sample é procurado no caminho salvo e depois no caminho relativo (dá para mover a
pasta do projeto junto com os samples). Se algum faltar, a janela **Samples not found** mostra quais;
você pode **localizar** cada arquivo, **procurar numa pasta** (encontra pelo nome, conferindo o
conteúdo) ou abrir assim mesmo — os ausentes ficam marcados. Arquivos encontrados com conteúdo
diferente do salvo também são avisados. Mudanças não salvas são confirmadas antes de abrir outro
projeto, começar um novo ou fechar o app.

## 9. Exportação em lote (Generator → Batch)

**Add current settings** coloca na fila uma cópia de **todas** as configurações atuais (samples,
ordem, modo, efeitos, exportação). Mude o que quiser e adicione outra tarefa; as tarefas já na fila
não mudam. **Start queue** exporta uma depois da outra em segundo plano (dá para continuar
trabalhando), com progresso por tarefa e geral, estado de cada uma (Waiting, Running, Done, Failed,
Cancelled, Skipped) e o erro de quem falhou. Uma tarefa que falha não para as outras. **Cancel** para
a tarefa atual sem deixar nada pela metade.

Nada é sobrescrito: se a pasta de destino já tiver arquivos, a tarefa vai para uma pasta numerada
nova ("Export (2)") ou é pulada, conforme escolhido. **Run again**, **Up/Down**, **Remove**,
**Open folder** e **Clear finished** gerenciam a fila, que é salva com as configurações e com o
projeto.

## 10. Presets

A janela **Presets** (Manage presets) reúne sequências, Natural, Robot, Legacy, Lab, cadeias de
efeitos, configurações de exportação e configurações completas. Ações disponíveis: Apply, New from current, Update
from current, editar descrição, duplicar, renomear, excluir (somente os seus), Restore
(nativo modificado), Restore all native, Import e Export. O formato é JSON versionado
(`*.vxpreset.json`). Campos desconhecidos são ignorados e campos ausentes recebem o padrão,
então presets de versões futuras ou antigas continuam abrindo.

## 11. Notificações

O Voxa GEN tem notificações próprias (não as do Windows). Elas aparecem num cartão flutuante
no **canto superior direito da tela**, mesmo com o app minimizado ou atrás de outra janela, e
não roubam o foco do programa que você estiver usando.

- Ao terminar uma exportação aparece **Export complete**, com a pasta de destino, o número de
  notas, o modo e o resultado da validação, além do botão **Open folder**.
- Erros, avisos e exportações sempre aparecem. As demais mensagens podem ser desligadas em
  Settings → Notifications.
- As notificações se empilham (a mais nova no topo, até quatro). Passar o mouse por cima pausa
  o tempo, e o × fecha na hora.

## 12. Appearance

- **Themes**: 7 temas iniciais (Voxa Dark, Voxa Light, Midnight Blue, Boyfriend Cyan, Girlfriend
  Pink, Lemon Light, High Contrast). **Save current as…** guarda o visual atual como tema seu.
- **Colours**: cor primária, secundária, de destaque, fundo, painéis, cartões, botões, texto e logo
  (seletor ou código hex). Os tons derivados (hover, bordas, texto apagado) acompanham.
- **Text & layout**: fonte da interface, tamanho do texto (85–135 %), arredondamento (0–150 %),
  densidade (Compact/Comfortable/Spacious), cartões sólidos ou com contorno, ícones desenhados à
  mão ou em linha fina/grossa.
- **Readability**: o contraste (WCAG) é conferido sempre; se uma combinação deixaria o texto
  ilegível, a cor do texto é ajustada automaticamente e o ajuste é mostrado.

Tudo é aplicado na hora, no app inteiro, pelo mesmo tema.

## 13. Idioma

**Settings → General → Language**: English, Português (Portugal), Português (Brasil), Português
(Brasil, com gírias), Español, 日本語, Pirate English e Meowgwenge (inglês de gato). A troca é imediata — nada reinicia e
nenhum trabalho é perdido. Explicações dos “?”, tooltips, notificações e mensagens de erro também
são traduzidos, e os valores (`{n}`, nomes, caminhos) são preservados. Em japonês a interface usa
fontes com suporte a japonês. Na primeira abertura o idioma do Windows é usado.

## 14. Settings

Idioma; transições animadas; sidebar compacta; sons da interface (geral,
volume master e, por evento, liga/desliga, volume, troca por arquivo próprio, preview e
reset); notificações; diretório padrão de exportação; volume e auto-render dos previews;
limpeza do cache de render; restaurar presets nativos.

Os sons da interface tocam num stream de áudio próprio e nunca entram nos previews nem nos
arquivos exportados. Para a associação padrão de cada som, veja
[assets/sounds/fnf/NOTICE.md](../assets/sounds/fnf/NOTICE.md).
