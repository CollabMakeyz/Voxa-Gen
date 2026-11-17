# Arquitetura

```
UI (PySide6)                               Core (sem dependência da UI*)
─────────────────────────────              ─────────────────────────────────────────
ui/pages/generator.py ──┐                  core/samples      SampleLibrary, naming, analyzer
  (abas Basic, Samples, │  AppContext      core/sequences    build_order, BF Classic
   Order, Exporting,    ├─ (estado,        core/pitch        tuning, detect
   Preview, Batch)      │   sinais,        core/audio        dsp, engines/, pipeline,
ui/pages/lab.py         │   persistência,                    generation
ui/pages/appearance.py  │   tema, idioma)  core/effects      registry (14 efeitos), chain, presets
ui/pages/settings.py ───┘                  core/export       riff, exporter, validate, batch
ui/pages/presets.py (janela)               core/projects     .vxproj: salvar, abrir, relocalizar
ui/widgets/*  (waveform, teclado,          core/presets      PresetManager (+ tipo "effects")
 transporte, editor de sequência,          core/history      undo/redo por snapshots
 previews, effects_editor, batch_panel,    core/workers*     Task (QThread + sinais)
 analyzer_panel, project_bar)              core/preview*     PreviewPlayer (QAudioSink)
ui/i18n_qt.py  tradução de widgets         core/notifications* UiSoundEngine
i18n/          tr(), idiomas, catálogos (assets/i18n/*.json)
models/  config (dataclasses), app_settings, serialization (compatível entre versões)
```

\* `workers`, `preview` e `notifications` usam Qt (threads e saída de áudio), mas não usam
widgets.

## Casca da interface

`ui/widgets/shell.py` implementa o layout do Figma ("Desktop - 1"): a sidebar tem 320 px em `#1e1e1e`,
com o logo (`assets/ui/logo.png`) e os botões de navegação de 300×35 px (`#2c2c2c`, raio 8, ícones
29×31). As páginas ficam dentro de um painel arredondado (`#3b3b3b`, raio 19, margem de 16 px) sobre um
fundo pontilhado. As cores estão em `ui/theme.py`, e o acento `#FFA600` vem do logo.

## Princípios

- **Algoritmos fora da UI.** Os engines implementam a interface `Engine` (`analyze`, `render`,
  `analysis_key`, `render_key`). Para criar um modo novo, basta escrever uma classe e
  registrá-la em `get_engine`.
- **Um pipeline só.** Preview e exportação usam `render_generation`.
- **Nada pesado na thread principal.** Toda análise, render, preview, detecção de pitch e
  exportação roda em `Task` (QThread), com progresso, cancelamento cooperativo e erros
  entregues à UI.
- **Memória limitada.** As análises ficam num LRU limitado em bytes e as fontes decodificadas
  também (LRU por hash de conteúdo). Na exportação, as notas processadas vão para arquivos
  `.npy` temporários e o WAV completo é escrito em streaming.
- **Transacional.** A exportação escreve numa pasta temporária, valida e só então move.
- **Compatível.** Configurações e presets usam `from_dict` tolerante (ignora campos
  desconhecidos e preenche os ausentes) e carregam número de versão.

## Persistência

- `%APPDATA%\VoxaGEN\settings.json`: todas as preferências e a configuração do Generator
  (escrita atômica e debounced). Um arquivo corrompido é renomeado para
  `settings.corrupt.json` e o app abre com os padrões.
- `%APPDATA%\VoxaGEN\presets\<tipo>\*.vxpreset.json`: presets do usuário e overrides dos
  nativos.
- `%APPDATA%\VoxaGEN\sounds\`: sons importados pelo usuário.
- `%LOCALAPPDATA%\VoxaGEN\cache\`: renders (`renders/*.npy`) e setas do tema.

As variáveis `VOXAGEN_DATA_DIR` e `VOXAGEN_CACHE_DIR` sobrescrevem esses caminhos (usadas nos
testes).


## Versão 1.0.0: o que entrou e onde

- **Efeitos** (`core/effects`). `EffectsSettings` (em `GeneratorConfig.effects`) guarda a cadeia, a chave
  liga/desliga (padrão: desligada) e a seed. O `NoteRenderer` aplica a cadeia depois do motor e da
  conversão de taxa/canais, **antes** do pós-processamento (fades, normalização), e só quando a chave está
  ligada. A cadeia entra na chave do cache de render, então preview, exportação e lote continuam
  idênticos e nada é reprocessado sem necessidade. A amostra A do A/B de efeitos é renderizada com
  `effects=False`.
- **Undo/redo** (`core/history.History`): guarda o estado anterior de cada mudança (LAB: ferramentas +
  efeitos). Mudanças rápidas com a mesma chave (um slider sendo arrastado) viram um passo só.
- **Projetos** (`core/projects`): JSON versionado `voxagen-project`. Os samples são resolvidos pelo caminho
  absoluto e depois pelo relativo; o hash detecta arquivos trocados. Abrir um projeto substitui os campos
  do `GeneratorConfig` **no lugar**, para que os widgets mantenham suas referências.
- **Lote** (`core/export/batch`): cada `BatchJob` tem uma cópia da configuração e a própria lista de
  samples; `run_batch` chama o `export_chromatic` transacional de sempre. Conflitos de destino viram
  pasta numerada ou "skipped", nunca sobrescrita.
- **Analisador** (`core/samples/analyzer`): medidas por arquivo + comparações entre samples; as
  mensagens ficam como modelo + valores e são traduzidas na hora de mostrar.
- **Idiomas** (`i18n`, `ui/i18n_qt`): o código escreve inglês. Cada widget é traduzido quando o Qt o
  "polishes" (evento `Polish`, filtro no `AppContext`), e todos são retraduzidos ao trocar de idioma;
  cada texto lembra sua fonte em inglês. Textos com valores usam `tr("… {n} …", n=…)`. Os catálogos
  são gerados por `tools/i18n_build.py` a partir de `tools/i18n/*.txt` (pt-BR, es, ja escritos à mão;
  pt-PT, gírias, pirata e gatês derivados por regras + ajustes). `tools/i18n_extract.py` lista as
  strings; o teste `test_every_visible_string_is_translated` falha se algum texto novo ficar sem
  tradução.
- **Aparência** (`ui/theme.py`): `build_tokens(base, cores)` deriva todos os tokens a partir das cores
  escolhidas; `fix_contrast` garante WCAG (texto 4,5:1, contornos 3:1); `Look` guarda fonte, escala do
  texto, arredondamento, densidade, estilo dos cartões e ícones. A folha de estilo é gerada uma vez e
  escalada (pt, raios, paddings), então todas as páginas mudam juntas.
