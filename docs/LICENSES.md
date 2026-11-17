# Licença e créditos

**Voxa GEN 1.0.0** · © 2026 Rambyte Team

O Voxa GEN é software livre, distribuído sob a **GNU General Public License, versão 3 ou
posterior** (GPL-3.0-or-later). O texto completo está em [LICENSE](../LICENSE). Você pode usar,
compartilhar e modificar o programa, desde que quem receber o programa também receba o
código-fonte e os mesmos direitos. O programa vem **sem nenhuma garantia**.

O motivo da GPL: o modo Legacy e a detecção de pitch usam o Praat (via Parselmouth), que é
GPL-3.0. Um executável que o inclui é uma obra combinada e precisa seguir a mesma licença.

## Código-fonte

Cada versão pública sai junto com o código-fonte correspondente. Quem distribuir o executável
também precisa disponibilizar o código-fonte daquela versão (GPL-3.0, seção 6).

## Dependências incluídas no executável

| Componente | Uso | Licença |
| --- | --- | --- |
| Python | runtime | PSF License |
| PySide6 / Qt 6 | interface, threads, saída de áudio | LGPL-3.0 (bibliotecas dinâmicas não modificadas, substituíveis na pasta do programa) |
| NumPy | arrays e DSP | BSD-3-Clause |
| SciPy | filtros, STFT, interpolação | BSD-3-Clause |
| soundfile / libsndfile | leitura de áudio (WAV, OGG, MP3) | BSD-3-Clause / LGPL-2.1+ |
| python-soxr / libsoxr | reamostragem | LGPL-2.1+ |
| praat-parselmouth / Praat | detecção de pitch, modo Legacy | GPL-3.0-or-later |
| pyworld / WORLD | análise e síntese vocal (Natural, Robot) | MIT / Modified BSD |
| setuptools (`pkg_resources`) | exigido pelo pyworld 0.3.5 | MIT |
| PyInstaller | empacotamento | GPL-2.0 com exceção para o bootloader |

O **Chromatic Scale Generator Deluxe** (GPL-3.0-or-later) serviu só como referência de
comportamento. Nenhum código dele foi copiado; o modo Legacy é uma implementação própria,
descrita em [ALGORITHMS.md](ALGORITHMS.md). O ChromaKit não foi usado.

## Assets de terceiros (créditos)

Estes arquivos **não** estão sob a GPL. Eles continuam pertencendo aos seus autores e vêm
com o Voxa GEN com crédito.

- **Sons da interface** (`assets/sounds/fnf/`): *chartingSounds* do Friday Night Funkin',
  © The Funkin' Crew Inc. "Friday Night Funkin'" é marca da The Funkin' Crew Inc. A Funkin'
  Crew permite publicamente o uso desses sons em projetos open source, com crédito. Detalhes em
  [assets/sounds/fnf/NOTICE.md](../assets/sounds/fnf/NOTICE.md). Todo som pode ser desligado ou
  trocado em Configurações → Sons.
- **VCR OSD Mono** (`assets/fonts/VCR_OSD_MONO_1.001.ttf`), de Riciery Leal. Usada com crédito,
  como permitido pelo autor.
- **Inter 4.1** (`assets/fonts/Inter-*.ttf`), de Rasmus Andersson. SIL Open Font License 1.1,
  em `assets/fonts/Inter-LICENSE.txt`.

## Arte do Voxa GEN

O logo, o ícone do app (`assets/ui/app_icon.png` e `assets/icons/voxagen.ico`), os ícones da navegação (`assets/ui/`, incluindo `nav_appearance.png`) e os ícones de
traço (`voxagen/ui/icons.py`) foram feitos pelo Rambyte Team para o Voxa GEN e seguem a licença
do projeto.
