# Voxa GEN 1.1 — implementation plan

Guiding rule: everything serves the chromatic. No DAW features.

## What already exists (kept)

| Area | Where | Reused for |
|---|---|---|
| Shared render pipeline (preview == export), disk render cache | `core/audio/pipeline.py`, `generation.py` | Effects run inside `NoteRenderer`, so preview, export and batch use the same chain |
| Engines Natural / Robot / Legacy / Lab | `core/audio/engines/` | Unchanged; effects are a separate, opt-in stage after the engine |
| Transactional export + validation | `core/export/exporter.py` | Batch export calls it once per job |
| Presets (builtin + user override, versioned JSON) | `core/presets/manager.py` | New kind `effects` with categories |
| Sequence editor undo/redo | `ui/widgets/sequence_editor.py` | Kept |
| Background tasks with cancel | `core/workers.py` | Analyzer, batch, effect previews |
| A/B preview player (same position) | `core/preview/player.py` | Volume matching added |
| Theme tokens + generated QSS | `ui/theme.py` | Appearance builds a custom token set + scales |
| "?" help popups | `ui/widgets/common.py` | Every new control gets one; all text goes through `tr()` |

## Architecture changes

1. `GeneratorConfig.effects` (`EffectsSettings`: `enabled=False`, `chain`, `preset_name`).
   The chain only runs when the user turns it on. It is part of the render cache key.
2. `core/effects/` — 14 real DSP effects + chain processor (wet/dry, bypass, order, seed).
3. `core/history.py` — snapshot undo/redo used by the effects chain and the Lab settings.
4. `core/projects/` — `.vxproj` files (config, sample references with hashes, presets used,
   batch queue); missing-file detection and relocation.
5. `core/export/batch.py` — queue of independent jobs, each with its own config snapshot and
   sample list; per-job + overall progress, cancel, errors, never overwrites silently.
6. `core/samples/analyzer.py` — problems that hurt a chromatic, with suggested fixes.
7. `voxagen/i18n/` — `tr()` with placeholders, 8 catalogs, live switching (widget retranslation).
8. `AppSettings.appearance` — custom themes (colors, font, text size, radius, density, icon
   style, logo color) with contrast validation; applied through the one stylesheet.

## Navigation

Generator (tabs: Basic · Samples · Order · Exporting · Preview · Batch; project bar) ·
LAB (Source & tools · Effects · Compare · Profiles) · Appearance · Settings.
Sample Manager becomes the Samples tab (with the analyzer). The Presets page becomes a
"Manage presets" window opened from the Generator and the LAB.

## Stages (each tested before the next)

1. Effects core + presets + history — unit tests on every effect's actual signal change.
2. Projects, batch, analyzer — unit tests.
3. i18n core + catalogs — placeholder/coverage tests.
4. Appearance core — contrast validation tests.
5. UI integration — offscreen UI tests and screenshots on the real Windows platform.
6. Docs, package, self-test.

## Status

All six stages are implemented and tested (see `tests/test_effects.py`, `tests/test_projects_batch.py`,
`tests/test_i18n.py` and the new cases in `tests/test_ui.py`). The packaged self-test also runs every
effect and loads every language.
