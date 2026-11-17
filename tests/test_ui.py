import os
import time

import pytest
import soundfile as sf

from conftest import synth_vowel

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def pump(sec):
    loop = QEventLoop()
    QTimer.singleShot(int(sec * 1000), loop.quit)
    loop.exec()


def wait_for(cond, timeout=90):
    t0 = time.time()
    while not cond() and time.time() - t0 < timeout:
        pump(0.05)
    return cond()


@pytest.fixture
def window(qapp, tmp_path):
    from voxagen.ui.context import AppContext
    from voxagen.ui.main_window import MainWindow
    folder = tmp_path / "voice"
    folder.mkdir()
    for name, f0 in [("a", 220), ("e", 247), ("a2", 233), ("10", 200), ("2", 210)]:
        sf.write(folder / f"{name}.wav", synth_vowel(f0, 48000, 0.35), 48000)
    ctx = AppContext(qapp)
    ctx.set_language("en")
    ctx.settings.ui_sounds.enabled = False
    ctx.apply_theme("dark")
    win = MainWindow(ctx)
    win.resize(1400, 880)
    win.show()
    win.pages[0].set_folder(str(folder))
    ctx.config.musical.semitones = 6
    ctx.config.mode = "robot"
    win.pages[0].load_from_config()
    yield win, ctx, folder
    win.close()


def test_navigation_and_pages(window):
    win, ctx, _ = window
    assert [p.page_id for p in win.pages] == ["generator", "lab", "appearance", "settings"]
    for pid in ["lab", "appearance", "settings", "generator"]:
        win.navigate(pid)
        assert win.stack.currentWidget().page_id == pid
        assert win.nav[pid].isChecked()
    win.navigate("lab")
    win.navigate("samples")
    assert win.stack.currentWidget().page_id == "generator" and win.pages[0].current_tab == 1
    assert win.content.tabs.current == 1
    win.navigate("presets")
    assert win._presets_window is not None and win._presets_window.isVisible()
    win._presets_window.close()


def test_theme_toggle_persists(window, tmp_path):
    win, ctx, _ = window
    ctx.apply_theme("light")
    ctx.save_now()
    from voxagen.models.app_settings import SettingsStore
    loaded = SettingsStore(ctx.store.path).load()
    assert loaded.theme == "light" and loaded.appearance.current.base == "light"
    assert "#f3f2ef" in QApplication.instance().styleSheet() or ctx.settings.theme == "light"


def test_sample_identification(window):
    win, ctx, _ = window
    assert ctx.library.ids() == ["2", "10", "a", "a2", "e"]


def test_chrom_preview_renders_in_background(window):
    win, ctx, _ = window
    chrom = win.pages[0].chrom
    chrom.variant.set_value("robot")
    t0 = time.time()
    chrom.render()
    assert time.time() - t0 < 1.0
    assert wait_for(lambda: chrom.gen is not None)
    assert len(chrom.gen.notes) == 6 and not chrom.gen.errors
    assert all(s == "ok" for s in chrom.keyboard.states)
    old = chrom._key()
    ctx.config.export.gap_ms = 50
    ctx.touch("export")
    assert chrom._key() != old


def test_export_and_cancel(window, tmp_path):
    win, ctx, _ = window
    gen = win.pages[0]
    ctx.config.export.output_dir = str(tmp_path / "out")
    ctx.config.export.folder_name = "Run1"
    ctx.settings.confirm_on_cancel = False
    gen.load_from_config()
    gen.start_export()
    assert gen.is_exporting()
    assert wait_for(lambda: not gen.is_exporting(), 180)
    assert gen.export_stage.text() == "Export complete"
    assert (tmp_path / "out" / "Run1" / "chromatic.wav").exists()
    ctx.config.mode = "natural"
    ctx.config.musical.semitones = 24
    ctx.config.export.folder_name = "Run2"
    from voxagen.core.audio.pipeline import clear_memory_caches
    clear_memory_caches()
    gen.load_from_config()
    gen.start_export()
    gen.cancel_export()
    assert wait_for(lambda: not gen.is_exporting(), 180)
    assert gen.export_stage.text() == "Export cancelled"
    assert not (tmp_path / "out" / "Run2").exists()
    assert not [p for p in (tmp_path / "out").iterdir() if p.name.startswith(".voxagen-tmp")]


def test_sequence_editor_edits(window):
    win, ctx, _ = window
    ed = win.pages[0].sequence_editor
    ed._set_tokens([])
    ed.add_tokens(["a", "e2", "a2"])
    assert ctx.config.order.sequence == ["a", "e2", "a2"]
    from voxagen.ui.widgets.sequence_editor import ROLE_STATE
    states = [ed.chips.item(i).data(ROLE_STATE) for i in range(3)]
    assert states == ["ok", "missing", "ok"]
    ed.chips.clearSelection()
    ed.chips.item(0).setSelected(True)
    ed.duplicate_selected()
    assert ctx.config.order.sequence == ["a", "a", "e2", "a2"]
    ed.undo()
    assert ctx.config.order.sequence == ["a", "e2", "a2"]
    ed.redo()
    ed.chips.clearSelection()
    ed.chips.item(2).setSelected(True)
    ed.remove_selected()
    assert ctx.config.order.sequence == ["a", "a", "a2"]


def test_lab_renders_and_measures(window):
    win, ctx, _ = window
    win.navigate("lab")
    lab = win.pages[1]
    lab.render()
    assert wait_for(lambda: lab._result is not None)
    err = lab._metric_labels["err"].text()
    assert err.endswith("cents") and abs(float(err.split()[0])) < 5


def test_presets_apply_updates_generator(window):
    win, ctx, _ = window
    from voxagen.core.sequences.order import BF_CLASSIC_TOKENS
    win.navigate("presets")
    page = win._presets_window.page
    page.kinds.setCurrentRow(0)
    page.list.setCurrentRow(0)
    page.apply()
    assert ctx.config.order.mode == "vocal"
    assert tuple(ctx.config.order.sequence) == BF_CLASSIC_TOKENS
    assert win.pages[0].order_mode.value() == "vocal"


def test_lab_effects_chain_undo_redo_and_export_switch(window):
    win, ctx, _ = window
    win.navigate("lab")
    lab = win.pages[1]
    ed = lab.fx_editor
    assert ctx.config.effects.enabled is False
    ed.add_effect("tremolo")
    ed.add_effect("eq")
    assert [s.effect for s in ctx.config.effects.chain] == ["tremolo", "eq"]
    ed.list.setCurrentRow(1)
    ed.move(-1)
    assert [s.effect for s in ctx.config.effects.chain] == ["eq", "tremolo"]
    lab.undo()
    assert [s.effect for s in ctx.config.effects.chain] == ["tremolo", "eq"]
    lab.redo()
    assert [s.effect for s in ctx.config.effects.chain] == ["eq", "tremolo"]
    from PySide6.QtCore import Qt
    ed.list.item(1).setCheckState(Qt.CheckState.Unchecked)
    assert ctx.config.effects.chain[1].enabled is False
    lab.undo()
    assert ctx.config.effects.chain[1].enabled is True
    gen = win.pages[0]
    gen.fx_on.setChecked(True)
    assert ctx.config.effects.enabled
    ed.reload()
    assert ed.enabled.isChecked()
    ed.category.setCurrentIndex(ed.category.findData("Retro"))
    ed.preset.setCurrentIndex(ed.preset.findData("8-bit Console"))
    ed.load_preset()
    assert [s.effect for s in ctx.config.effects.chain] == ["bitcrusher", "eq"]
    lab.undo()
    assert [s.effect for s in ctx.config.effects.chain] == ["eq", "tremolo"]
    ctx.config.effects.enabled = False
    ctx.config.effects.chain = []


def test_effects_ab_preview_renders(window):
    win, ctx, _ = window
    win.navigate("lab")
    lab = win.pages[1]
    lab._go_tab(1)
    ed = lab.fx_editor
    ed.add_effect("ring_modulator")
    pv = ed.preview
    pv.render()
    assert wait_for(lambda: len(pv.player.variants()) == 2)
    a, b = pv.player.variants()
    assert a.startswith("A") and b.startswith("B")
    assert "B" in pv.listening.text()
    pv.ab.setChecked(False)
    assert pv.player.active.startswith("A")
    ctx.config.effects.chain = []


def test_batch_queue_runs_in_background(window, tmp_path):
    win, ctx, _ = window
    gen = win.pages[0]
    bp = gen.batch
    bp.jobs = []
    ctx.config.export.output_dir = str(tmp_path / "batch")
    for name in ("One", "Two"):
        ctx.config.export.folder_name = name
        bp.name.setText(name)
        bp.add_current()
    assert len(bp.jobs) == 2 and bp.table.rowCount() == 2
    bp.start()
    assert bp.running and ctx.busy
    gen.start_export()
    assert not gen.is_exporting()
    assert wait_for(lambda: not bp.running, 240)
    assert [j.status for j in bp.jobs] == ["done", "done"]
    assert (tmp_path / "batch" / "One" / "chromatic.wav").exists()
    assert bp.overall.value() == 1000
    bp.clear_finished()
    assert not bp.jobs


def test_project_save_and_open_with_missing_sample(window, tmp_path, monkeypatch):
    win, ctx, folder = window
    gen = win.pages[0]
    pc = gen.project
    ctx.config.musical.a4_hz = 432.0
    ctx.config.order.sequence = ["a", "e"]
    pc.path = tmp_path / "song.vxproj"
    assert pc.save() and pc.path.exists() and not pc.dirty
    ctx.config.musical.a4_hz = 440.0
    ctx.touch("musical")
    assert pc.dirty
    (folder / "e.wav").rename(tmp_path / "e_moved.wav")
    from voxagen.ui.widgets import project_bar
    seen = {}

    def fake_exec(dlg):
        seen["missing"] = [s.id for s in dlg.project.missing]
        return True
    monkeypatch.setattr(project_bar.MissingSamplesProjectDialog, "exec", fake_exec)
    monkeypatch.setattr(project_bar, "confirm", lambda *a, **k: True)
    pc.open(str(tmp_path / "song.vxproj"))
    assert seen["missing"] == ["e"]
    assert ctx.config.musical.a4_hz == 432.0 and ctx.config.order.sequence == ["a", "e"]
    assert ctx.library.get("e").status == "missing" and gen.a4.value() == 432.0
    assert not pc.dirty


def test_sample_check_finds_problems(window):
    win, ctx, folder = window
    import numpy as np
    sf.write(folder / "loud.wav", np.clip(np.sin(np.arange(24000) * 0.05) * 3, -1, 1), 48000, subtype="FLOAT")
    ctx.library.add_files([folder / "loud.wav"])
    ctx.libraryChanged.emit()
    gen = win.pages[0]
    gen.go_tab(gen.TAB_SAMPLES)
    gen.samples_switch.set_value("check")
    gen.analyzer.run()
    assert wait_for(lambda: gen.analyzer.report is not None)
    kinds = {(f.sample_id, f.kind) for f in gen.analyzer.report.findings}
    assert ("loud", "clipping") in kinds
    assert gen.analyzer.table.rowCount() == len(gen.analyzer.report.findings)


def test_appearance_custom_colours_and_readability(window):
    win, ctx, _ = window
    from voxagen.ui import theme
    win.navigate("appearance")
    ap = win.pages[2]
    ap._set_color("primary", "#ff4fa3")
    ap._apply_now()
    assert theme.current().accent == "#ff4fa3"
    assert "#ff4fa3" in QApplication.instance().styleSheet()
    ap._set_color("text", "#333333")
    ap._set_color("cards", "#2a2a2a")
    ap._apply_now()
    t = theme.current()
    assert theme.contrast(t.text, t.surface) >= 4.5
    assert "adjusted" in ap.check_text.text()
    ap.size.setValue(120)
    ap.density.set_value("compact")
    ap._apply_now()
    assert theme.look().font_scale == 1.2 and theme.look().density == "compact"
    ap.reset_layout()
    ap.themes.setCurrentRow(0)
    ap.apply_selected()
    assert ctx.settings.appearance.current.name == "Voxa Dark" and theme.current().accent == theme.DARK.accent


def test_language_switches_live_without_restart(window):
    win, ctx, _ = window
    from voxagen import i18n
    from voxagen.ui import theme
    gen = win.pages[0]
    try:
        ctx.set_language("pt_BR")
        assert win.nav["generator"].text().strip() == "Gerar"
        assert gen.b_export.text() == "Exportar cromática"
        assert win.content.tabs.labels[0] == "BÁSICO"
        lab = win.pages[1]
        assert lab.fx_editor.b_add.text() == "Adicionar efeito"
        gen._refresh_source()
        assert "samples em uso" in gen.source_summary.text()
        ctx.set_language("ja")
        assert theme.look().cjk and win.nav["settings"].text().strip() == "設定"
        assert gen.b_export.text() == "クロマチックを書き出す"
        win.navigate("presets")
        assert win._presets_window.page.kinds.item(0).text() == "シーケンス"
        win._presets_window.close()
        ctx.set_language("en")
        assert gen.b_export.text() == "Export chromatic" and win.nav["generator"].text().strip() == "Generate"
        assert not theme.look().cjk
        assert ctx.settings.language == "en"
    finally:
        i18n.set_language("en")
