from __future__ import annotations

import copy
from collections import OrderedDict

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QProgressBar, QSpinBox, QVBoxLayout, QWidget

from ...core.audio.generation import render_generation
from ...core.audio.pipeline import config_fingerprint
from ...core.pitch.tuning import midi_of
from ...core.preview.player import PreviewPlayer
from ...core.sequences.order import MissingSampleError, OrderError, validate_sequence
from ...core.workers import Task
from ...i18n import tr
from .common import elastic, Badge, Segmented, button, hbox, hint, label, set_tone, tool_button
from .dialogs import MissingSamplesDialog
from .keyboard import ChromaticKeyboard
from .sample_preview import VARIANT_LABEL, VARIANTS
from .transport import TransportBar
from .waveform import WaveformView


class ChromPreview(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.player = PreviewPlayer(self)
        ctx.register_player(self.player)
        self._cache: OrderedDict[tuple, tuple] = OrderedDict()
        self._task: Task | None = None
        self.gen = None
        self._current_key = None
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        self.variant = Segmented(VARIANTS, ctx.config.mode, tooltips={
            "original": "Source samples mapped to the notes, without pitch processing"})
        self.variant.changed.connect(lambda _: self._on_variant())
        self.match = Badge("", "ok")
        v.addLayout(hbox(self.variant, None))

        self.b_render = button("Render preview", "refresh", "Primary")
        self.b_cancel = button("Cancel", "close")
        self.b_cancel.hide()
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.hide()
        self.status = elastic(label("", "StatusText"))
        v.addLayout(hbox(self.b_render, self.b_cancel, self.progress, self.match, None))
        v.addWidget(self.status)

        self.keyboard = ChromaticKeyboard()
        v.addWidget(self.keyboard)
        self.wave = WaveformView("accent", 120)
        self.wave.placeholder = "Render the preview to hear the chromatic"
        v.addWidget(self.wave, 1)
        self.now = label("", "CardTitle")
        self.now_detail = elastic(label("", "Hint"))
        v.addLayout(hbox(self.now, self.now_detail))
        self.transport = TransportBar(self.player, ctx, prev_next=True)
        v.addWidget(self.transport)
        self.range_from = QSpinBox()
        self.range_to = QSpinBox()
        for s in (self.range_from, self.range_to):
            s.setRange(1, 1)
            s.setFixedWidth(64)
        self.b_range = button("Play range", "play")
        self.b_range.setToolTip("Play consecutive notes from → to")
        self.b_full = button("Play all", "play")
        v.addLayout(hbox(label("Notes"), self.range_from, label("to"), self.range_to, self.b_range, self.b_full, None))

        self.b_render.clicked.connect(self.render)
        self.b_cancel.clicked.connect(self.cancel)
        self.keyboard.noteClicked.connect(self.play_note)
        self.wave.seekRequested.connect(self.player.seek)
        self.wave.markerClicked.connect(lambda i: self._show_note(i))
        self.transport.prevRequested.connect(lambda: self._step(-1))
        self.transport.nextRequested.connect(lambda: self._step(1))
        self.b_range.clicked.connect(self.play_range)
        self.b_full.clicked.connect(self.play_all)
        self.player.positionChanged.connect(self._follow)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(700)
        self._debounce.timeout.connect(lambda: self.render(auto=True))
        ctx.configChanged.connect(lambda _: self.on_config_changed())
        ctx.libraryChanged.connect(self.on_config_changed)
        self.on_config_changed()

    def _variant(self) -> str:
        return self.variant.value()

    def _key(self) -> tuple:
        cfg = self.ctx.config
        return (config_fingerprint(cfg, self.ctx.library), self._variant())

    def _on_variant(self) -> None:
        self._update_badge()
        self.on_config_changed()

    def _update_badge(self) -> None:
        mode = self.ctx.config.mode
        v = self._variant()
        if v == mode:
            self.match.setText(tr("Same pipeline as export"))
            self.match.set_tone("ok")
        elif v == "original":
            self.match.setText(tr("Unprocessed · export uses {mode}", mode=tr(VARIANT_LABEL[mode])))
            self.match.set_tone("")
        else:
            self.match.setText(tr("Comparison · export uses {mode}", mode=tr(VARIANT_LABEL[mode])))
            self.match.set_tone("warn")

    def on_config_changed(self) -> None:
        self._update_badge()
        m = self.ctx.config.musical
        start = midi_of(m.start_note, m.start_octave)
        if self.keyboard.start_midi != start or self.keyboard.count != m.semitones:
            self.keyboard.set_range(start, m.semitones)
        for s in (self.range_from, self.range_to):
            s.setRange(1, max(1, m.semitones))
        if self.range_to.value() == 1:
            self.range_to.setValue(min(12, m.semitones))
        key = self._key()
        if key in self._cache:
            if key != self._current_key:
                self._show(*self._cache[key], key)
            return
        self._mark_planned()
        if self.gen is not None or self._current_key is not None:
            self._set_status("Out of date — settings changed", "warn")
        if self.ctx.settings.preview_auto_render and self.isVisible() and self.gen is not None:
            self._debounce.start()

    def _mark_planned(self) -> None:
        cfg = self.ctx.config
        n = cfg.musical.semitones
        usable = set(self.ctx.library.usable_ids(set(cfg.disabled_samples)))
        states, tips = [], []
        if cfg.order.mode == "vocal" and cfg.order.sequence:
            st = validate_sequence(cfg.order.sequence, usable, cfg.order.remap)
            active = [s for s in st if s.state != "skipped"] or st
            for i in range(n):
                s = active[i % len(active)]
                ok = s.resolved is not None
                states.append("pending" if ok else "missing")
                tips.append(tr("sample {id}", id=s.resolved) if ok else tr("{file} missing", file=f"{s.token}.wav"))
        else:
            for i in range(n):
                states.append("pending" if usable else "missing")
                tips.append("" if usable else "no samples loaded")
        self.keyboard.set_states(states, tips)

    def render(self, auto: bool = False) -> None:
        key = self._key()
        if key in self._cache:
            self._show(*self._cache[key], key)
            return
        if not self.ctx.library.usable_ids():
            if not auto:
                self.ctx.toast("Load samples first (Generator → Source or Sample Manager).", "warn")
            return
        if self._task is not None and self._task.running:
            self._task.cancel()
        cfg = copy.deepcopy(self.ctx.config)
        variant = self._variant()
        library = self.ctx.library
        try:
            from ...core.audio.pipeline import plan_notes
            plan_notes(cfg, library)
        except MissingSampleError as exc:
            if auto:
                return self._set_status(str(exc), "error")
            dlg = MissingSamplesDialog(self, exc.missing, library.usable_ids())
            if not dlg.exec():
                return self._set_status("Preview cancelled: missing samples", "warn")
            self.ctx.config.order.remap.update(dlg.remap())
            self.ctx.touch("order")
            return self.render()
        except OrderError as exc:
            return self._set_status(str(exc), "error")

        def job(progress, cancelled):
            gen = render_generation(cfg, library, mode=None if variant == "original" else variant,
                                    original=variant == "original", progress=progress, cancel=cancelled, strict=False)
            return gen, gen.assemble()

        self.b_render.setEnabled(False)
        self.b_cancel.show()
        self.progress.show()
        self.progress.setRange(0, cfg.musical.semitones)
        self._set_status(tr("Rendering {what}…", what=tr(VARIANT_LABEL[variant])), "")
        t = Task(job, "chrom-preview", self)
        t.progress.connect(self._progress)
        t.succeeded.connect(lambda res, k=key: self._done(res, k))
        t.failed.connect(lambda exc: (self._finish(), self._set_status(tr("Error: {error}", error=str(exc)), "error"), self.ctx.sound("error")))
        t.cancelled.connect(lambda: (self._finish(), self._set_status(tr("Preview cancelled"), "warn"), self.ctx.sound("cancel")))
        self._task = t.start()

    def cancel(self) -> None:
        if self._task is not None:
            self._task.cancel()

    def _progress(self, stage, cur, total, lbl) -> None:
        self.progress.setValue(cur)
        self._set_status(tr("Note {n}/{total} · {what}", n=min(cur + 1, total), total=total, what=lbl), "")
        if 0 <= cur < self.keyboard.count:
            self.keyboard.set_current(cur)

    def _finish(self) -> None:
        self.b_render.setEnabled(True)
        self.b_cancel.hide()
        self.progress.hide()
        self.keyboard.set_current(-1)

    def _done(self, res, key) -> None:
        self._finish()
        self._cache[key] = res
        while len(self._cache) > 4:
            self._cache.popitem(last=False)
        self._show(*res, key)

    def _show(self, gen, audio, key) -> None:
        self.gen = gen
        self._current_key = key
        sr = gen.sample_rate
        self.player.load({VARIANT_LABEL[key[1]]: audio}, sr)
        self.wave.set_audio(audio, sr)
        labels = [f"{n.plan.name} · {n.plan.sample_id}" for n in gen.notes]
        states = ["error" if n.error else ("warn" if n.warnings else "ok") for n in gen.notes]
        self.wave.set_markers([p / sr for p in gen.positions], labels, states)
        tips = [(tr(n.error) or "; ".join(tr(w) for w in n.warnings) or tr("sample {id}", id=n.plan.sample_id))
                for n in gen.notes]
        self.keyboard.set_states(states, tips)
        errs = len(gen.errors)
        warn = sum(1 for n in gen.notes if n.warnings)
        msg = tr("{n} notes · {sec} s · rendered in {t} s", n=len(gen.notes), sec=f"{audio.shape[0] / sr:.1f}",
                 t=f"{gen.elapsed:.1f}")
        if errs:
            msg += " · " + tr("{n} failed", n=errs)
        elif warn:
            msg += " · " + tr("{n} with warnings", n=warn)
        self._set_status(msg, "error" if errs else ("warn" if warn else "ok"))
        self._show_note(0, seek=False)

    def _note_bounds(self, i: int) -> tuple[float, float]:
        sr = self.gen.sample_rate
        start = self.gen.positions[i] / sr
        return start, start + self.gen.notes[i].frames / sr

    def play_note(self, i: int) -> None:
        if self.gen is None or self._current_key != self._key():
            self.ctx.sound("preview_note")
            self.render()
            return
        if not (0 <= i < len(self.gen.notes)):
            return
        self.ctx.sound("preview_note")
        a, b = self._note_bounds(i)
        self._show_note(i, seek=False)
        self.player.play_range(a, b)

    def play_range(self) -> None:
        if self.gen is None:
            return self.render()
        i, j = sorted((self.range_from.value() - 1, self.range_to.value() - 1))
        j = min(j, len(self.gen.notes) - 1)
        a, _ = self._note_bounds(i)
        _, b = self._note_bounds(j)
        self.player.play_range(a, b)

    def play_all(self) -> None:
        if self.gen is None:
            return self.render()
        self.player.clear_range()
        self.player.stop()
        self.player.play()

    def _step(self, d: int) -> None:
        if self.gen is None:
            return
        i = self._index_at(self.player.position)
        self.play_note(max(0, min(len(self.gen.notes) - 1, i + d)))

    def _index_at(self, seconds: float) -> int:
        if self.gen is None:
            return -1
        sr = self.gen.sample_rate
        idx = 0
        for i, p in enumerate(self.gen.positions):
            if p / sr <= seconds + 1e-6:
                idx = i
        return idx

    def _follow(self, seconds: float) -> None:
        self.wave.set_position(seconds)
        if self.gen is None:
            return
        i = self._index_at(seconds)
        self.keyboard.set_current(i if self.player.state == "playing" else -1)
        self.wave.set_current_marker(i)
        self._show_note(i, seek=False)

    def _show_note(self, i: int, seek: bool = True) -> None:
        if self.gen is None or not (0 <= i < len(self.gen.notes)):
            self.now.setText("")
            self.now_detail.setText("")
            return
        n = self.gen.notes[i]
        self.now.setText(f"{n.plan.name}")
        detail = f"note {i + 1} / {len(self.gen.notes)} · sample {n.plan.sample_id} · {n.plan.target_hz:.2f} Hz"
        if n.error:
            detail += f" · ✕ {n.error}"
        elif n.warnings:
            detail += f" · ⚠ {n.warnings[0]}"
        self.now_detail.setText(detail)
        if seek:
            self.player.seek(self._note_bounds(i)[0])

    def _set_status(self, text: str, tone: str) -> None:
        self.status.setText(text)
        set_tone(self.status, tone)
