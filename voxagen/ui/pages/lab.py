from __future__ import annotations

import copy
import time

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGridLayout, QInputDialog, QProgressBar, QSpinBox, QSplitter,
    QStackedWidget, QVBoxLayout, QWidget,
)

from ...core.audio.dsp import active_rms, gain_to_db, peak
from ...core.audio.pipeline import NotePlan, NoteRenderer
from ...core.pitch.detect import median_f0
from ...core.pitch.tuning import NOTE_NAMES, cents_between, describe_hz, frequency_of, hz_to_midi_float, midi_of, note_name
from ...core.presets.manager import Preset, PresetError
from ...core.preview.player import PreviewPlayer
from ...core.history import History
from ...core.workers import Task
from ...i18n import tr
from ...models.config import NaturalParams
from ...models.serialization import from_dict, to_dict
from ..widgets.common import (
    Badge, Card, EmptyState, FormGrid, HelpButton, Segmented, button, confirm, hbox, hint, label, more_button, set_tone,
)
from ..widgets.effects_editor import EffectsEditor, snapshot
from ..widgets.natural_controls import NaturalControls
from ..widgets.transport import TransportBar
from ..widgets.waveform import SpectrogramView, WaveformView
from .base import Page


class LabPage(Page):
    page_id = "lab"
    title = "LAB"
    subtitle = "Experiment with processing tools and effects on a single sample, then reuse them"
    icon = "lab"
    tabs = ["Source & tools", "Effects", "Compare", "Profiles"]
    show_title = False

    def __init__(self, ctx):
        super().__init__(ctx)
        self._task: Task | None = None
        self._result = None
        self.player = PreviewPlayer(self)
        ctx.register_player(self.player)
        self.history = History()
        self._snap = snapshot(ctx)
        self.b_undo = button("Undo", "undo")
        self.b_undo.setToolTip("Undo the last change to the tools or effects (Ctrl+Z)")
        self.b_redo = button("Redo", "redo")
        self.b_redo.setToolTip("Redo (Ctrl+Y)")
        self.b_undo.clicked.connect(self.undo)
        self.b_redo.clicked.connect(self.redo)
        b_presets = button("Manage presets", "presets")
        b_presets.setToolTip("All presets: sequences, modes, LAB profiles, effect chains, export settings")
        b_presets.clicked.connect(lambda: ctx.navigateRequested.emit("presets"))
        self.header.addWidget(self.b_undo)
        self.header.addWidget(self.b_redo)
        self.header.addWidget(b_presets)
        for key, fn in (("Ctrl+Z", self.undo), ("Ctrl+Y", self.redo), ("Ctrl+Shift+Z", self.redo)):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(fn)


        src = Card("Source", "Choose one sample and the note to tune it to. Everything you change below is "
                             "applied to this sample so you can hear the effect.")
        self.sample = QComboBox()
        self.sample.setMinimumWidth(110)
        self.note = QComboBox()
        self.note.addItems(NOTE_NAMES)
        self.octave = QSpinBox()
        self.octave.setRange(0, 8)
        self.octave.setValue(4)
        b_det = button("Use detected note", "wave")
        b_det.setToolTip("Target = the note closest to the sample's detected pitch")
        b_det.clicked.connect(self.use_detected)
        g = FormGrid()
        g.row("Sample", hbox(self.sample, None), "The sample you are experimenting with.")
        g.row("Target note", hbox(self.note, self.octave, b_det, None),
              "The note the sample is tuned to. Try a note far from the original to hear the tools work harder.")
        src.add(g)
        self.b_render = button("Render", "refresh", "Primary")
        self.b_render.clicked.connect(self.render)
        self.b_cancel = button("Cancel", "close")
        self.b_cancel.clicked.connect(lambda: self._task and self._task.cancel())
        self.b_cancel.hide()
        self.auto = QCheckBox("Update automatically")
        self.auto.setChecked(True)
        self.auto.setToolTip("Re-render the result every time you change a setting")
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setMaximumWidth(120)
        self.busy.hide()
        self.status = label("", "StatusText")
        auto_help = HelpButton("Update automatically", 'Renders the sample again every time you change a tool. You always hear the current settings. On a slow computer, turn it off and press Render yourself.')
        src.add(hbox(self.b_render, self.b_cancel, self.auto, auto_help, self.busy, None))
        src.add(self.status)
        b_compare = button("Listen and compare", "ab")
        b_compare.clicked.connect(lambda: self._go_tab(2))
        b_use = button("Use in Generator", "check", "Primary")
        b_use.setToolTip("Export with these settings: switches the Generator to Lab mode")
        b_use.clicked.connect(self.use_in_generator)
        src.add(hbox(b_compare, None, b_use))

        tools = Card("Tools", "Each tool changes one thing about the sound. Switch a tool off to bypass it "
                               "completely. The “?” next to each one explains it.")
        self.controls = NaturalControls(ctx.config.lab, tool_switches=True)
        self.controls.changed.connect(self._params_changed)
        b_def = button("Restore defaults", "reset")
        b_def.clicked.connect(self.controls.restore_defaults)
        tools.add(hbox(None, b_def))
        tools.add(self.controls)
        self.add_tab(self.columns([src], [tools]))

        self.fx_editor = EffectsEditor(ctx, self)
        self.fx_editor.changed.connect(self._fx_changed)
        self.add_tab(self.columns([self.fx_editor.chain_card, self.fx_editor.presets_card],
                                  [self.fx_editor.settings_card, self.fx_editor.listen_card]))

        cmp = Card("Compare", 'A is the original sample, B the processed one. Switching keeps the position and the volume. All you hear is the difference in sound.')
        self.ab = Segmented([("A · Original", "A · Original"), ("B · Processed", "B · Processed")], "B · Processed")
        self.ab.changed.connect(self.player.set_variant)
        self.listening = Badge("Listening: B · Processed", "processed")
        self.view = Segmented([("wave", "Waveform"), ("spec", "Spectrum")], "wave")
        self.listening.setProperty("i18n_text_skip", True)
        self.match = QCheckBox("Match loudness")
        self.match.setChecked(self.player.match_loudness)
        self.match.setToolTip('Plays A and B at the same loudness, so you judge the sound and not the volume. Previews only. Exports never change.')
        self.match.toggled.connect(self._match)
        sc = QShortcut(QKeySequence("B"), self)
        sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc.activated.connect(lambda: self._toggle_ab())
        cmp.add(hbox(self.ab, self.listening, None, self.match, self.view))
        self.views = QStackedWidget()
        wv = QWidget()
        wl = QVBoxLayout(wv)
        wl.setContentsMargins(0, 0, 0, 0)
        self.wave_a = WaveformView("accent", 110)
        self.wave_a.placeholder = "Original"
        self.wave_b = WaveformView("processed", 110)
        self.wave_b.placeholder = "Processed"
        wl.addWidget(self.wave_a)
        wl.addWidget(self.wave_b)
        self.views.addWidget(wv)
        sv = QWidget()
        sl = QVBoxLayout(sv)
        sl.setContentsMargins(0, 0, 0, 0)
        self.spec_a = SpectrogramView()
        self.spec_b = SpectrogramView()
        sl.addWidget(self.spec_a)
        sl.addWidget(self.spec_b)
        self.views.addWidget(sv)
        self.view.changed.connect(lambda k: self.views.setCurrentIndex(0 if k == "wave" else 1))
        cmp.add(self.views)
        self.transport = TransportBar(self.player, ctx)
        cmp.add(self.transport)
        res = Card("Result", "Measured on the processed sound. Pitch error below 5 cents is inaudible.")
        self.metrics = QGridLayout()
        self.metrics.setHorizontalSpacing(18)
        self.metrics.setVerticalSpacing(6)
        self._metric_labels: dict[str, tuple] = {}
        for i, (key, name) in enumerate([("src", "Original pitch"), ("tgt", "Target"), ("out", "Result pitch"),
                                         ("err", "Pitch error"), ("dur", "Length before → after"),
                                         ("time", "Processing time"), ("voiced", "Voiced part"),
                                         ("level", "Loudness A → B")]):
            self.metrics.addWidget(hint(name), i, 0)
            v = label("—")
            self.metrics.addWidget(v, i, 1)
            self._metric_labels[key] = v
        res.add(self.metrics)
        self.notes = hint("")
        res.add(self.notes)
        self.add_tab(self.columns([cmp], [res]))

        prof = Card("Profiles", "Save your tool settings as a profile to reuse them. “Use in Generator” exports "
                                "with them (Lab mode).")
        self.profile = QComboBox()
        self.profile.setMinimumWidth(170)
        b_load = button("Load", "import")
        b_load.setToolTip("Replace the current tool settings with this profile")
        b_load.clicked.connect(self.load_profile)
        b_save_as = button("Save as new", "add")
        b_save_as.clicked.connect(self.save_profile_as)
        more = more_button([
            ("Save into this profile", "save", self.save_profile),
            ("Duplicate", "duplicate", self.duplicate_profile),
            ("Delete", "trash", self.delete_profile),
            ("Restore the original version", "reset", self.restore_profile),
            ("Import from a file…", "import", self.import_profile),
            ("Export to a file…", "export", self.export_profile),
        ])
        self.b_restore = more._actions["Restore the original version"]
        prof.add(hbox(label("Profile"), self.profile, b_load, b_save_as, more, None))
        self.add_tab(self.columns([prof]))
        self.profile.currentIndexChanged.connect(self._profile_selected)

        self.stack = QStackedWidget()
        self.stack.addWidget(EmptyState("lab", "No samples loaded",
                                        "Load samples in the Generator (Basic or Samples tab) to start experimenting.",
                                        "Go to Samples", lambda: ctx.navigateRequested.emit("samples")))
        self.stack.addWidget(self.tab_stack)
        self.root.addWidget(self.stack, 1)

        self.player.positionChanged.connect(self._pos)
        self.player.variantChanged.connect(self._variant)
        self.wave_a.seekRequested.connect(self.player.seek)
        self.wave_b.seekRequested.connect(self.player.seek)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(450)
        self._debounce.timeout.connect(self.render)
        self.sample.currentIndexChanged.connect(lambda _: self._source_changed())
        self.note.currentIndexChanged.connect(lambda _: self._source_changed())
        self.octave.valueChanged.connect(lambda _: self._source_changed())
        ctx.libraryChanged.connect(self.refresh_samples)
        ctx.presetsChanged.connect(lambda k: k == "lab" and self.refresh_profiles())
        ctx.configChanged.connect(lambda s: s in ("export", "effects") and self._mark_dirty())
        ctx.configChanged.connect(lambda s: s == "all" and self._external_reload())
        ctx.languageChanged.connect(lambda _: self._variant(self.player.active or ""))
        self.refresh_samples()
        self.refresh_profiles()

    def refresh_samples(self) -> None:
        cur = self.sample.currentData()
        self.sample.blockSignals(True)
        self.sample.clear()
        for s in self.ctx.library.samples():
            if s.usable:
                self.sample.addItem(s.id, s.id)
        i = self.sample.findData(cur)
        self.sample.setCurrentIndex(i if i >= 0 else 0)
        self.sample.blockSignals(False)
        self.stack.setCurrentIndex(1 if self.sample.count() else 0)

    def use_detected(self) -> None:
        s = self.ctx.library.get(self.sample.currentData() or "")
        if not (s and s.pitch and s.pitch.reliable):
            from ...core.pitch.detect import detect_pitch
            from ...core.audio.dsp import load_audio
            if s is None:
                return
            x, sr = load_audio(s.path)
            self.ctx.library.set_pitch(s.id, detect_pitch(x, sr, self.ctx.config.musical.a4_hz))
        p = s.pitch
        if not p.reliable:
            return self.ctx.toast(tr("Pitch of {id} is not reliable: {reason}", id=s.id, reason=tr(p.reason)), "warn")
        midi = int(round(hz_to_midi_float(p.median_hz, self.ctx.config.musical.a4_hz)))
        self.note.setCurrentIndex(midi % 12)
        self.octave.setValue(midi // 12 - 1)

    def _source_changed(self) -> None:
        self._mark_dirty()

    def _params_changed(self) -> None:
        key = getattr(self.controls, "last_key", "")
        self._record("Change LAB tool", f"tool:{key}" if key else "tool")
        self.ctx.touch("lab")
        self._mark_dirty()

    def _record(self, label_: str, merge: str = "") -> None:
        self.history.record(self._snap, label_, merge)
        self._snap = snapshot(self.ctx)
        self._sync_history()

    def _fx_changed(self, label_: str, merge: str) -> None:
        self._record(label_, merge)

    def _sync_history(self) -> None:
        self.b_undo.setEnabled(self.history.can_undo)
        self.b_redo.setEnabled(self.history.can_redo)
        self.b_undo.setToolTip(tr("Undo: {what} (Ctrl+Z)", what=tr(self.history.undo_label))
                               if self.history.can_undo else tr("Nothing to undo"))
        self.b_redo.setToolTip(tr("Redo: {what} (Ctrl+Y)", what=tr(self.history.redo_label))
                               if self.history.can_redo else tr("Nothing to redo"))
        for b in (self.b_undo, self.b_redo):
            b.setProperty("i18n_tip_skip", True)

    def _restore(self, state: dict) -> None:
        cfg = self.ctx.config
        lab = from_dict(NaturalParams, state["lab"])
        for k, v in to_dict(lab).items():
            setattr(cfg.lab, k, copy.deepcopy(v))
        from ...models.config import EffectsSettings
        fx = from_dict(EffectsSettings, state["effects"])
        cfg.effects.enabled, cfg.effects.chain = fx.enabled, fx.chain
        cfg.effects.preset_name, cfg.effects.seed = fx.preset_name, fx.seed
        cfg.lab_profile_name = state.get("lab_profile_name", cfg.lab_profile_name)
        self._snap = snapshot(self.ctx)
        self.controls.load(cfg.lab)
        self.fx_editor.reload()
        self.ctx.touch("lab")
        self.ctx.touch("effects")
        self._mark_dirty()
        self._sync_history()

    def undo(self) -> None:
        state = self.history.undo(snapshot(self.ctx))
        if state is not None:
            self._restore(state)
            self.ctx.sound("undo")

    def redo(self) -> None:
        state = self.history.redo(snapshot(self.ctx))
        if state is not None:
            self._restore(state)
            self.ctx.sound("undo")

    def _external_reload(self) -> None:
        self.controls.load(self.ctx.config.lab)
        self.fx_editor.reload()
        self.history.clear()
        self._snap = snapshot(self.ctx)
        self._sync_history()
        self._mark_dirty()

    def _match(self, on: bool) -> None:
        self.player.match_loudness = on
        if self._result is not None:
            self._done(self._result)

    def _toggle_ab(self) -> None:
        cur = self.ab.value()
        self.ab.set_value("A · Original" if cur.startswith("B") else "B · Processed")

    def _mark_dirty(self) -> None:
        self._set_status(tr("Settings changed"), "warn")
        if self.auto.isChecked() and self.isVisible():
            self._debounce.start()

    def _go_tab(self, i: int) -> None:
        self.set_tab(i)
        w = self.window()
        if hasattr(w, "content"):
            w.content.tabs.set_current(i, emit=False)

    def on_shown(self) -> None:
        if snapshot(self.ctx) != self._snap:
            self._snap = snapshot(self.ctx)
            self.controls.load(self.ctx.config.lab)
            self.fx_editor.reload()
        self._sync_history()
        if self._result is None and self.sample.count():
            self._debounce.start()

    def render(self) -> None:
        sid = self.sample.currentData()
        if not sid:
            return
        if self._task is not None and self._task.running:
            self._task.cancel()
        cfg = copy.deepcopy(self.ctx.config)
        lib = self.ctx.library
        midi = midi_of(self.note.currentIndex(), self.octave.value())
        m = cfg.musical
        hz = frequency_of(midi, m.a4_hz, m.temperament, m.temperament_root, m.custom_cents)
        plan = NotePlan(0, midi, note_name(midi), hz, sid)

        def job(progress, cancelled):
            orig = NoteRenderer(cfg, lib, original=True, use_disk_cache=False).render_raw(plan)
            t0 = time.perf_counter()
            proc = NoteRenderer(cfg, lib, mode="lab", effects=False).render_raw(plan)
            elapsed = time.perf_counter() - t0
            if cancelled():
                return None
            sr = cfg.export.sample_rate
            f_out = median_f0(proc.audio, sr)
            return {"orig": orig.audio, "proc": proc.audio, "sr": sr, "elapsed": elapsed, "f_out": f_out,
                    "hz": hz, "info": proc.info, "warnings": proc.warnings, "midi": midi}

        self.b_render.setEnabled(False)
        self.b_cancel.show()
        self.busy.show()
        self._set_status(tr("Rendering…"), "")
        t = Task(job, "lab", self)
        t.succeeded.connect(self._done)
        t.failed.connect(lambda exc: self._set_status(tr("Error: {error}", error=str(exc)), "error"))
        t.cancelled.connect(lambda: self._set_status(tr("Cancelled"), "warn"))
        t.finished.connect(self._finish)
        self._task = t.start()

    def _finish(self) -> None:
        self.b_render.setEnabled(True)
        self.b_cancel.hide()
        self.busy.hide()

    def _done(self, r) -> None:
        if r is None:
            return
        self._result = r
        sr = r["sr"]
        playing = self.player.state == "playing"
        self.player.load({"A · Original": r["orig"], "B · Processed": r["proc"]}, sr,
                         active=self.ab.value(), keep_position=True)
        self.wave_a.set_audio(r["orig"], sr, "A · original")
        self.wave_b.set_audio(r["proc"], sr, "B · processed")
        self.spec_a.set_audio(r["orig"], sr, "A · original")
        self.spec_b.set_audio(r["proc"], sr, "B · processed")
        info = r["info"] or {}
        src = info.get("source_hz") or 0.0
        mm = self._metric_labels
        if src:
            n, c = describe_hz(src, self.ctx.config.musical.a4_hz)
            mm["src"].setText(f"{src:.2f} Hz · {n} {c:+.0f} ct")
        else:
            mm["src"].setText(tr("not detected"))
        mm["tgt"].setText(f"{note_name(r['midi'])} · {r['hz']:.2f} Hz")
        if r["f_out"]:
            err = cents_between(r["f_out"], r["hz"])
            mm["out"].setText(f"{r['f_out']:.2f} Hz")
            mm["err"].setText(tr("{value} cents", value=f"{err:+.2f}"))
            pc = self.ctx.config.lab.tool_on("pitch_correction")
            set_tone(mm["err"], "ok" if abs(err) < 5 or not pc else "warn")
            mm["err"].setObjectName("StatusText")
        else:
            mm["out"].setText(tr("not measurable"))
            mm["err"].setText("—")
        mm["dur"].setText(f"{len(r['orig']) / sr:.3f} s → {len(r['proc']) / sr:.3f} s")
        mm["time"].setText(f"{r['elapsed'] * 1000:.0f} ms")
        mm["voiced"].setText(f"{info.get('voiced_ratio', 0):.0%}")
        la = gain_to_db(active_rms(r["orig"], sr))
        lb = gain_to_db(active_rms(r["proc"], sr))
        mm["level"].setText(f"{la:.1f} → {lb:.1f} dB RMS · peak {gain_to_db(peak(r['proc'])):.1f} dBFS")
        notes = [tr(w) for w in r["warnings"]]
        if not self.ctx.config.lab.tool_on("pitch_correction"):
            notes.insert(0, tr("Pitch Correction is off: the output keeps the source pitch."))
        if self.player.match_loudness:
            notes.append(tr("A/B playback is loudness-matched so level differences do not bias the comparison."))
        if self.ctx.config.effects.enabled and self.ctx.config.effects.chain:
            notes.append(tr("The effects chain is not part of this comparison; hear it in the Effects tab."))
        self.notes.setText("  ·  ".join(notes))
        self._set_status(tr("Up to date"), "ok")
        if playing:
            self.player.play()

    def _pos(self, s: float) -> None:
        for w in (self.wave_a, self.wave_b, self.spec_a, self.spec_b):
            w.set_position(s)

    def _variant(self, name: str) -> None:
        self.ab.set_value(name, emit=False)
        side, _, what = name.partition(" · ")
        self.listening.setText(tr("Now playing: {side} · {what}", side=side, what=tr(what)) if name else "—")
        self.listening.set_tone("processed" if name.startswith("B") else "accent")

    def _set_status(self, text: str, tone: str) -> None:
        self.status.setText(text)
        set_tone(self.status, tone)

    def refresh_profiles(self) -> None:
        cur = self.profile.currentData() or self.ctx.config.lab_profile_name
        self.profile.blockSignals(True)
        self.profile.clear()
        for p in self.ctx.presets.list("lab"):
            tag = tr(" · built-in, changed") if p.modified else (tr(" · built-in") if p.builtin else "")
            self.profile.addItem(tr(p.name) + tag, p.name)
        i = self.profile.findData(cur)
        self.profile.setCurrentIndex(max(0, i))
        self.profile.blockSignals(False)
        self.profile.setProperty("i18n_items_skip", True)
        self._profile_selected()

    def _profile_selected(self) -> None:
        p = self.ctx.presets.get("lab", self.profile.currentData() or "")
        self.b_restore.setEnabled(bool(p and p.modified))

    def _apply_params(self, params: NaturalParams, name: str) -> None:
        before = snapshot(self.ctx)
        for k, v in to_dict(params).items():
            setattr(self.ctx.config.lab, k, copy.deepcopy(v))
        self.ctx.config.lab_profile_name = name
        self.controls.load(self.ctx.config.lab)
        self.history.record(before, "Load LAB profile")
        self._snap = snapshot(self.ctx)
        self._sync_history()
        self.ctx.touch("lab")
        self._mark_dirty()

    def load_profile(self) -> None:
        p = self.ctx.presets.get("lab", self.profile.currentData() or "")
        if p:
            self._apply_params(from_dict(NaturalParams, p.data), p.name)
            self.ctx.toast(tr("Loaded profile “{name}”.", name=tr(p.name)), "ok")

    def save_profile(self) -> None:
        name = self.profile.currentData()
        p = self.ctx.presets.get("lab", name or "")
        if p is None:
            return self.save_profile_as()
        if p.builtin and not confirm(self, tr("Change built-in profile"),
                                     tr("Overwrite the built-in profile “{name}”? You can restore it later.", name=name)):
            return
        self.ctx.presets.save(Preset("lab", name, to_dict(self.ctx.config.lab), p.description))
        self.ctx.config.lab_profile_name = name
        self.ctx.presetsChanged.emit("lab")
        self.ctx.toast(tr("Saved “{name}”.", name=name), "ok")

    def save_profile_as(self) -> None:
        name, ok = QInputDialog.getText(self, tr("Save LAB profile"), tr("Profile name:"),
                                        text=self.ctx.presets.free_name("lab", tr("My profile")))
        if not ok or not name.strip():
            return
        name = name.strip()
        if self.ctx.presets.exists("lab", name):
            return self.ctx.toast(tr("A profile named “{name}” already exists.", name=name), "warn")
        self.ctx.presets.save(Preset("lab", name, to_dict(self.ctx.config.lab)))
        self.ctx.config.lab_profile_name = name
        self.ctx.presetsChanged.emit("lab")
        self.profile.setCurrentIndex(self.profile.findData(name))
        self.ctx.toast(tr("Saved “{name}”.", name=name), "ok")

    def duplicate_profile(self) -> None:
        name = self.profile.currentData()
        if name:
            p = self.ctx.presets.duplicate("lab", name)
            self.ctx.presetsChanged.emit("lab")
            self.profile.setCurrentIndex(self.profile.findData(p.name))

    def delete_profile(self) -> None:
        name = self.profile.currentData()
        p = self.ctx.presets.get("lab", name or "")
        if p is None:
            return
        if p.builtin:
            return self.ctx.toast("Built-in profiles cannot be deleted.", "warn")
        if confirm(self, tr("Delete profile"), tr("Delete the LAB profile “{name}”?", name=name), tr("Delete"),
                   danger=True):
            self.ctx.presets.delete("lab", name)
            self.ctx.presetsChanged.emit("lab")
            self.ctx.sound("seq_remove")

    def restore_profile(self) -> None:
        name = self.profile.currentData()
        self.ctx.presets.restore("lab", name)
        self.ctx.presetsChanged.emit("lab")
        self.ctx.toast(tr("Restored the original “{name}”.", name=tr(name)), "ok")

    def import_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Import LAB profile"), "", tr("Voxa GEN preset (*.json)"))
        if not path:
            return
        try:
            p = self.ctx.presets.import_from(path)
        except PresetError as exc:
            return self.ctx.toast(str(exc), "error")
        self.ctx.presetsChanged.emit(p.kind)
        if p.kind in ("lab", "natural"):
            self._apply_params(from_dict(NaturalParams, p.data), p.name)
        self.ctx.toast(tr("Imported “{name}”.", name=p.name), "ok")

    def export_profile(self) -> None:
        name = self.ctx.config.lab_profile_name or tr("LAB profile")
        path, _ = QFileDialog.getSaveFileName(self, tr("Export LAB profile"), f"{name}.vxpreset.json",
                                              tr("Voxa GEN preset (*.json)"))
        if path:
            import json
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(Preset("lab", name, to_dict(self.ctx.config.lab)).to_file(), fh, indent=2)
            self.ctx.toast("Profile exported.", "ok")

    def use_in_generator(self) -> None:
        self.ctx.config.mode = "lab"
        self.ctx.touch("mode_external")
        self.ctx.toast("Generator switched to Lab mode with the current LAB settings.", "ok")
        self.ctx.navigateRequested.emit("generator")
