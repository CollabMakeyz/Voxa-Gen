from __future__ import annotations

import copy

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget

from ...i18n import tr

from ...core.audio.pipeline import NotePlan, NoteRenderer
from ...core.pitch.tuning import NOTE_NAMES, frequency_of, midi_of, note_name
from ...core.preview.player import PreviewPlayer
from ...core.workers import Task
from .common import Badge, Segmented, button, elastic, hbox, hint, label, set_tone, tool_button
from .transport import TransportBar
from .waveform import WaveformView

VARIANTS = [("original", "Original"), ("natural", "Natural"), ("robot", "Robot"), ("legacy", "Legacy"),
            ("lab", "Lab")]
FX_VARIANTS = [("dry", "Without effects"), ("fx", "With effects")]
VARIANT_LABEL = dict(VARIANTS + FX_VARIANTS)


class SamplePreview(QWidget):
    statusChanged = Signal(str)

    def __init__(self, ctx, show_selector: bool = True, compact: bool = False, effects_ab: bool = False):
        super().__init__()
        self.ctx = ctx
        self.effects_ab = effects_ab
        self.player = PreviewPlayer(self)
        ctx.register_player(self.player)
        self._cache: dict[tuple, np.ndarray] = {}
        self._info: dict[tuple, tuple] = {}
        self._task: Task | None = None
        self._pending = False
        self.sample_id = ""
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.sample = QComboBox()
        self.sample.setMinimumWidth(120)
        self.sample.currentIndexChanged.connect(lambda _: self.set_sample(self.sample.currentData() or ""))
        if show_selector:
            top.addWidget(label("Sample"))
            top.addWidget(self.sample)
        top.addWidget(label("Target"))
        self.note = QComboBox()
        self.note.addItems(NOTE_NAMES)
        self.octave = QSpinBox()
        self.octave.setRange(0, 8)
        self.note.setCurrentIndex(0)
        self.octave.setValue(4)
        self.auto_target = button("Use detected note", "wave")
        self.auto_target.setToolTip("Use the nearest note to the sample's detected pitch")
        self.auto_target.clicked.connect(self.use_detected_pitch)
        top.addWidget(self.note)
        top.addWidget(self.octave)
        top.addStretch(1)
        v.addLayout(top)

        row = QHBoxLayout()
        self.variant = Segmented(FX_VARIANTS if effects_ab else VARIANTS, "fx" if effects_ab else "natural")
        self.variant.changed.connect(lambda _: self.request_render())
        if effects_ab:
            self.variant.hide()
        else:
            v.addWidget(self.variant)
        row.addWidget(self.auto_target)
        row.addStretch(1)
        self.match = QCheckBox("Match loudness")
        self.match.setChecked(self.player.match_loudness)
        self.match.setToolTip('Plays A and B at the same loudness, so you judge the sound and not the volume. Previews only. Exports never change.')
        self.match.toggled.connect(self._match)
        row.addWidget(self.match)
        v.addLayout(row)
        row = QHBoxLayout()
        self.ab = button("A / B", "ab")
        self.ab.setCheckable(True)
        self.ab.setToolTip("Switch between A and B at the same position (shortcut: B)")
        sc = QShortcut(QKeySequence("B"), self)
        sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc.activated.connect(self.ab.toggle)
        self.ab.toggled.connect(self._ab)
        row.addWidget(self.ab)
        self.listening = Badge("—", "accent")
        self.listening.setProperty("i18n_text_skip", True)
        row.addWidget(self.listening)
        row.addStretch(1)
        v.addLayout(row)
        self.status = elastic(QLabel(""))
        self.status.setObjectName("StatusText")
        v.addWidget(self.status)

        self.wave = WaveformView("accent", 90 if compact else 120)
        self.wave.placeholder = "Select a sample to preview"
        self.wave.setMaximumHeight(200)
        self.wave.seekRequested.connect(self.player.seek)
        v.addWidget(self.wave)
        self.info = hint("")
        v.addWidget(self.info)
        self.transport = TransportBar(self.player, ctx)
        v.addWidget(self.transport)
        v.addStretch(1)

        self.player.positionChanged.connect(self.wave.set_position)
        self.player.variantChanged.connect(self._variant_changed)
        for w in (self.note, self.octave):
            (w.currentIndexChanged if isinstance(w, QComboBox) else w.valueChanged).connect(
                lambda *_: self.request_render())
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(350)
        self._debounce.timeout.connect(self.render)
        ctx.configChanged.connect(lambda _: self.request_render(auto=True))
        ctx.libraryChanged.connect(self.refresh_samples)
        self.refresh_samples()

    def refresh_samples(self) -> None:
        current = self.sample_id
        self.sample.blockSignals(True)
        self.sample.clear()
        for s in self.ctx.library.samples():
            if s.usable:
                self.sample.addItem(s.id, s.id)
        idx = self.sample.findData(current)
        self.sample.setCurrentIndex(idx if idx >= 0 else (0 if self.sample.count() else -1))
        self.sample.blockSignals(False)
        new = self.sample.currentData() or ""
        if new != self.sample_id:
            self.set_sample(new)

    def set_sample(self, sample_id: str, render: bool = True) -> None:
        self.sample_id = sample_id
        i = self.sample.findData(sample_id)
        if i >= 0 and i != self.sample.currentIndex():
            self.sample.blockSignals(True)
            self.sample.setCurrentIndex(i)
            self.sample.blockSignals(False)
        if render:
            self.request_render()

    def set_target_midi(self, midi: int) -> None:
        for w in (self.note, self.octave):
            w.blockSignals(True)
        self.note.setCurrentIndex(midi % 12)
        self.octave.setValue(midi // 12 - 1)
        for w in (self.note, self.octave):
            w.blockSignals(False)
        self.request_render()

    def use_detected_pitch(self) -> None:
        s = self.ctx.library.get(self.sample_id)
        if s and s.pitch and s.pitch.median_hz > 0:
            from ...core.pitch.tuning import hz_to_midi_float
            self.set_target_midi(int(round(hz_to_midi_float(s.pitch.median_hz, self.ctx.config.musical.a4_hz))))
        else:
            self.ctx.toast("No reliable pitch detected for this sample yet (use “Find the notes” in Samples).", "warn")

    def target_midi(self) -> int:
        return midi_of(self.note.currentIndex(), self.octave.value())

    def request_render(self, auto: bool = False) -> None:
        if auto and not self.ctx.settings.preview_auto_render:
            self._set_status(tr("Settings changed · press play to re-render"), "warn")
            self._pending = True
            return
        if not self.isVisible():
            self._pending = True
            return
        self._debounce.start()

    def showEvent(self, e):
        super().showEvent(e)
        if self._pending:
            self._pending = False
            self._debounce.start()

    def _key(self, variant: str) -> tuple | None:
        s = self.ctx.library.get(self.sample_id)
        if s is None:
            return None
        cfg = self.ctx.config
        from ...core.audio.engines import get_engine
        from ...models.serialization import to_dict
        if self.effects_ab:
            from ...core.effects.chain import chain_key
            fx = copy.deepcopy(cfg.effects)
            fx.enabled = True
            rk = get_engine(cfg.mode, cfg).render_key() + "|" + (chain_key(fx) if variant == "fx" else "")
        else:
            rk = "original" if variant == "original" else get_engine(variant, cfg).render_key()
        return (s.content_hash, variant, self.target_midi(), rk, str(to_dict(cfg.export)), str(to_dict(cfg.musical)))

    def render(self) -> None:
        variant = self.variant.value()
        if not self.sample_id:
            self.wave.clear()
            self.player.clear()
            return
        first = "dry" if self.effects_ab else "original"
        keys = {v: self._key(v) for v in (first, variant)}
        missing = [v for v, k in keys.items() if k not in self._cache]
        if not missing:
            self._show(keys)
            return
        if self._task is not None and self._task.running:
            self._task.cancel()
        cfg = copy.deepcopy(self.ctx.config)
        library = self.ctx.library
        midi = self.target_midi()
        m = cfg.musical
        hz = frequency_of(midi, m.a4_hz, m.temperament, m.temperament_root, m.custom_cents)
        plan = NotePlan(0, midi, note_name(midi), hz, self.sample_id)

        def job(progress, cancelled):
            out = {}
            for v in missing:
                if cancelled():
                    return None
                if self.effects_ab:
                    c2 = copy.deepcopy(cfg)
                    c2.effects.enabled = True
                    r = NoteRenderer(c2, library, mode=c2.mode, effects=(v == "fx"))
                else:
                    r = NoteRenderer(cfg, library, mode=None if v == "original" else v, original=(v == "original"),
                                     effects=False)
                rn = r.render(plan)
                if rn.error:
                    raise RuntimeError(rn.error)
                out[v] = (rn.audio, rn.warnings, rn.info)
            return out

        self._set_status(tr("Rendering {what}…", what=tr(VARIANT_LABEL[variant])), "")
        task = Task(job, "sample-preview", self)
        task.succeeded.connect(lambda res, k=keys: self._done(res, k))
        task.failed.connect(lambda exc: self._set_status(tr("Error: {error}", error=str(exc)), "error"))
        self._task = task.start()

    def _done(self, res, keys) -> None:
        if res is None:
            return
        for v, (audio, warnings, info) in res.items():
            self._cache[keys[v]] = audio
            self._info[keys[v]] = (warnings, info)
        if len(self._cache) > 24:
            for k in list(self._cache)[:-24]:
                self._cache.pop(k, None)
        self._show(keys)

    def _show(self, keys: dict) -> None:
        variant = self.variant.value()
        orig = self._cache[keys["dry" if self.effects_ab else "original"]]
        proc = self._cache[keys[variant]]
        sr = self.ctx.config.export.sample_rate
        playing = self.player.state == "playing"
        a_name = "A · Without effects" if self.effects_ab else "A · Original"
        b_name = f"B · {VARIANT_LABEL[variant]}"
        active = a_name if variant in ("original", "dry") else b_name
        self._last = (orig, proc, a_name, b_name)
        self.player.load({a_name: orig, b_name: proc}, sr, active=active, keep_position=True)
        self.ab.blockSignals(True)
        self.ab.setChecked(active.startswith("B"))
        self.ab.blockSignals(False)
        self._variant_changed(self.player.active)
        warnings, info = self._info.get(keys[variant], ([], {}))
        src = info.get("source_hz") if isinstance(info, dict) else None
        parts = [tr("{note} target", note=note_name(self.target_midi())), tr("{sec} s", sec=f"{len(proc) / sr:.2f}")]
        if src:
            parts.append(tr("source ≈ {hz} Hz", hz=f"{src:.1f}"))
        self.info.setText("  ·  ".join(parts) + ("   ⚠ " + tr(warnings[0]) if warnings else ""))
        self._set_status(tr("Ready · same pipeline as export"), "ok")
        if playing:
            self.player.play()

    def _ab(self, on: bool) -> None:
        names = self.player.variants()
        if len(names) < 2:
            return
        target = names[1] if on else names[0]
        self.player.set_variant(target)

    def _match(self, on: bool) -> None:
        self.player.match_loudness = on
        last = getattr(self, "_last", None)
        if last:
            orig, proc, a_name, b_name = last
            self.player.load({a_name: orig, b_name: proc}, self.ctx.config.export.sample_rate,
                             active=self.player.active or a_name, keep_position=True)

    def _variant_changed(self, name: str) -> None:
        if name:
            side, _, what = name.partition(" · ")
            self.listening.setText(tr("Now playing: {side} · {what}", side=side, what=tr(what)))
        else:
            self.listening.setText("—")
        self.listening.set_tone("processed" if name.startswith("B") else "accent")
        keys = self.player.variants()
        if len(keys) == 2 and self.player._variants:
            a, b = self.player._variants[keys[0]], self.player._variants[keys[1]]
            sr = self.player.sr
            if name.startswith("B"):
                self.wave.set_audio(b, sr)
                self.wave.set_overlay(a, "text_faint")
            else:
                self.wave.set_audio(a, sr)
                self.wave.set_overlay(b, "text_faint")

    def _set_status(self, text: str, tone: str) -> None:
        self.status.setText(text)
        set_tone(self.status, tone)
        self.statusChanged.emit(text)
