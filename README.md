# Voxa GEN

Voxa GEN is a Windows tool for generating chromatic scales from voice samples. It takes a sample and turns it into a full chromatic scale, exporting a WAV file with slice markers for FL Studio Slicex, along with separate WAV files for each note.

It has three independent processing chains: **Natural**, **Robot**, and **Legacy**. There's also a **LAB** where you can experiment with 14 optional effects and compare the results using A/B playback.

The **Audio Preview** and **Chrom Preview** use the same audio pipeline as the export process, so what you hear in the previews is what gets exported.

Other features include `.vxproj` project files, batch export, sample checking, full visual customization, and live language switching across 8 languages.

**Version 1.0.0, public release.**

© 2026 Rambyte Team. Free software under the [GPL-3.0-or-later](LICENSE) license. Third-party assets and their credits are listed in [docs/LICENSES.md](docs/LICENSES.md).

## Installation (from source)

Requirements: Windows 10 or 11 (64-bit), Python 3.12 or newer. Tested with Python 3.14.7.

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` pins `setuptools<81` because `pyworld` 0.3.5 still imports `pkg_resources`.

If a prebuilt wheel isn't available for your Python version, `pyworld` will be compiled during installation. This requires the *Microsoft C++ Build Tools*.

## Running Voxa GEN

```powershell
.venv\Scripts\python.exe run.py
```

You can also start it with:

```powershell
python -m voxagen
```

To run a quick check without opening the interface:

```powershell
python run.py --selftest report.json
```

## Tests

Run the test suite with:

```powershell
.venv\Scripts\python.exe -m pytest tests -q
```

The tests cover:

- **Audio processing:** Order System, tuning accuracy (less than 5 cents of error), formants, duration, stereo and mono, normalization, fades, resampling, clipping, WAV integrity, and slice markers.
- **Effects:** Each effect is checked against the audio signal. For example, tremolo changes volume without affecting pitch, vibrato changes pitch, and the frequency shifter moves frequencies by a measured amount in Hz.
- **Editing and presets:** Effect chains, effect presets, undo/redo, and conflict handling.
- **Projects and export:** Project files, batch export, the sample analyzer, and cancellation.
- **Settings:** Presets and persistent settings.
- **Localization and UI:** Translation coverage, placeholders, and the interface running offscreen. This includes navigation, effects, batch export, projects, appearance settings, and live language switching.

### Visual test monitor

The test monitor shows live progress, the test currently running, and any failures. It also has a **Verify** button for running the translation checks and the app self-test.

It uses the theme selected under Appearance.

```powershell
.venv\Scripts\python.exe tools\monitor\test_monitor.py
```

### Export benchmark

The benchmark measures export time and checks whether the resulting audio is bit-for-bit identical.

Save a baseline before changing the code:

```powershell
python tools/bench_export.py save <folder>
```

After making your changes, compare the results:

```powershell
python tools/bench_export.py compare <folder>
```

### Updating translations

After changing UI text, run:

```powershell
python tools/i18n_extract.py --check
```

This lists any strings that still need translations. Add the translations under `tools/i18n/`, then rebuild the language files:

```powershell
python tools/i18n_build.py
```

## Building for Windows

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

The build script creates:

- `dist\VoxaGEN\VoxaGEN.exe`, a standalone folder build that doesn't require Python to be installed.
- `dist\VoxaGEN-<version>-win64.zip`, a ZIP package of the build.

Before creating the ZIP, the script runs the tests, packages the application, and runs `--selftest` on the packaged executable.

## Documentation

- [User Guide](docs/USER_GUIDE.md): samples and sample checking, Order System, sequences, processing modes, LAB and effects, previews and A/B comparison, export, projects, batch processing, presets, appearance, languages, and interface sounds.
- [Algorithms](docs/ALGORITHMS.md): Natural, Robot, and Legacy processing, pitch detection, temperaments, and export.
- [Architecture](docs/ARCHITECTURE.md): project structure and data flow.
- [Licenses and Credits](docs/LICENSES.md): GPL-3.0, dependencies, and third-party assets.

## Project structure

```text
voxagen/
  models/             Versioned configuration dataclasses and persistence
  core/
    samples/          Sample library, identifiers, and natural sorting
    sequences/        Order System (Sequential, Shuffle, Random, Vocal, BF Classic)
    pitch/             Tuning, temperaments, and pitch detection with confidence
    audio/             DSP, processing engines (Natural, Robot, Legacy), shared pipeline
    export/            RIFF writer with cue/labl markers, transactional exporter, validation
    presets/           Versioned JSON presets (built-in and user-created)
    effects/            14 LAB effects, effect chain (wet/dry, bypass, order), category presets
    projects/           .vxproj files (save, open, and relink samples)
    history.py          Undo/redo
    preview/            Preview player (QAudioSink) with A/B comparison
    notifications/      Interface sounds (separate audio stream)
  i18n/                tr() and language support

  ui/                  Theme, icons, widgets, and pages

assets/                Sounds (FNF chartingSounds), logo, icons, fonts, and language catalogs
tools/                 Translation extraction and generation
tests/                 Automated tests
docs/                  Documentation
packaging/             PyInstaller spec and build script
```