# Voxa GEN

Gerador de chromatic scales para Windows: transforma samples de voz em uma escala cromática
completa (WAV com marcadores de slice para o FL Studio Slicex + WAVs individuais), com três
cadeias de processamento independentes (**Natural**, **Robot**, **Legacy**), um **LAB** para
experimentação com 14 efeitos opcionais e comparação A/B, **Audio Preview** e **Chrom Preview** que
usam exatamente o mesmo pipeline da exportação, projetos (`.vxproj`), exportação em lote, verificação
de samples, personalização visual completa e 8 idiomas com troca ao vivo.

**Versão 1.0.0 — public release.** © 2026 Rambyte Team. Software livre sob a
[GPL-3.0-or-later](LICENSE); créditos e assets de terceiros em [docs/LICENSES.md](docs/LICENSES.md).

## Instalação (código-fonte)

Requisitos: Windows 10/11 64-bit, Python 3.12+ (testado em 3.14.7).

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` fixa `setuptools<81` porque o `pyworld` 0.3.5 ainda importa `pkg_resources`.
O `pyworld` é compilado na instalação quando não há wheel para a sua versão do Python
(exige o *Microsoft C++ Build Tools*).

## Executar

```powershell
.venv\Scripts\python.exe run.py
```

Ou `python -m voxagen`. Teste rápido sem interface: `python run.py --selftest relatorio.json`.

## Testes

```powershell
.venv\Scripts\python.exe -m pytest tests -q
```

Order System, afinação (erro < 5 cents), formantes, duração, stereo/mono, normalização, fades,
resampling, clipping, integridade dos WAVs, marcadores, conflitos, cancelamento, presets,
configurações persistentes; cada efeito medido no sinal (tremolo muda só o volume, vibrato só a
altura, frequency shifter desloca em Hz, etc.); cadeia, presets de efeitos e undo/redo; projetos,
lote e analisador; traduções (cobertura e placeholders) e interface offscreen (navegação, efeitos,
lote, projeto, aparência, troca de idioma ao vivo).

Monitor visual (progresso ao vivo, teste em andamento, falhas e um botão **Verificar** para depois:
traduções + self-test do app), com o tema que você escolheu em Aparência:

```powershell
.venv\Scripts\python.exe tools\monitor\test_monitor.py
```

Benchmark de exportação (mede o tempo e confere se o áudio sai idêntico bit a bit):
`python tools/bench_export.py save <pasta>` antes de mudar o código, `compare <pasta>` depois.

Depois de mudar textos da interface: `python tools/i18n_extract.py --check` lista o que falta
traduzir; acrescente as traduções em `tools/i18n/` e rode `python tools/i18n_build.py`.

## Build para Windows

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

Gera `dist\VoxaGEN\VoxaGEN.exe` (pasta autocontida, sem Python instalado) e
`dist\VoxaGEN-<versão>-win64.zip`. O script roda os testes, empacota, executa o
`--selftest` no executável empacotado e só então cria o zip.

## Documentação

- [Guia de uso](docs/USER_GUIDE.md) — samples e verificação, Order System, sequências, modos, LAB e
  efeitos, previews e A/B, exportação, projetos, lote, presets, aparência, idiomas, sons.
- [Algoritmos](docs/ALGORITHMS.md) — Natural, Robot, Legacy, detecção de pitch, exportação.
- [Arquitetura](docs/ARCHITECTURE.md) — estrutura do projeto e fluxo de dados.
- [Licença e créditos](docs/LICENSES.md) — GPL-3.0, dependências e assets de terceiros.

## Estrutura

```
voxagen/
  models/            configurações (dataclasses versionadas) e persistência
  core/samples/      biblioteca de samples, identificadores, ordenação natural
  core/sequences/    Order System (Sequential/Shuffle/Random/Vocal, BF Classic)
  core/pitch/        afinação, temperamentos, detecção de pitch com confiança
  core/audio/        DSP, engines (natural/robot/legacy), pipeline compartilhado
  core/export/       writer RIFF com cue/labl, exportador transacional, validação
  core/presets/      presets JSON versionados (nativos + do usuário)
  core/effects/      14 efeitos do LAB, cadeia (wet/dry, bypass, ordem) e presets por categoria
  core/projects/     arquivos de projeto .vxproj (salvar, abrir, relocalizar samples)
  core/history.py    undo/redo
  i18n/              tr() e idiomas (catálogos em assets/i18n, fontes em tools/i18n)
  core/preview/      player de preview (QAudioSink) com A/B
  core/notifications/ sons da interface (stream de áudio separado)
  ui/                tema, ícones, widgets e páginas
assets/              sons (FNF chartingSounds), logo, ícones, fontes e catálogos de idioma (assets/i18n)
tools/               extração e geração das traduções
tests/               testes automatizados
docs/                documentação
packaging/           PyInstaller spec e script de build
```
