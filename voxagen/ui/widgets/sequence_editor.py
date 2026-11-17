from __future__ import annotations

import copy
import json

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QCompleter, QFileDialog, QInputDialog, QLineEdit, QListView,
    QListWidget, QListWidgetItem, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from ...core.audio.generation import render_generation
from ...core.presets.manager import Preset, PresetError
from ...core.preview.player import PreviewPlayer
from ...core.samples.naming import is_valid_token, normalize_token, parse_sequence_text
from ...core.sequences.order import BF_CLASSIC_NAME, validate_sequence
from ...core.workers import Task
from ...i18n import tr
from .. import theme
from .common import elastic, more_button, Badge, Segmented, button, hbox, hint, label, set_tone, tool_button
from .dialogs import MissingSamplesDialog
from .transport import TransportBar

ROLE_STATE = Qt.ItemDataRole.UserRole + 1
ROLE_INDEX = Qt.ItemDataRole.UserRole + 2


class ChipDelegate(QStyledItemDelegate):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner

    def sizeHint(self, option, index):
        f = QFont(option.font)
        f.setBold(True)
        w = QFontMetrics(f).horizontalAdvance(index.data() or "") + 34
        return QSize(max(44, w), 36)

    def paint(self, p: QPainter, option, index):
        t = theme.current()
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(option.rect).adjusted(2, 3, -2, -3)
        state = index.data(ROLE_STATE) or "ok"
        border = {"ok": t.border_strong, "remapped": t.warn, "skipped": t.text_faint,
                  "missing": t.error, "invalid": t.error}.get(state, t.border_strong)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        playing = index.row() == self.owner.playing_row
        bg = theme.qcolor(t.accent_soft) if playing else theme.qcolor(t.raised if selected else t.surface_alt)
        p.setBrush(bg)
        p.setPen(QPen(theme.qcolor(t.accent if (selected or playing) else border), 1.4 if selected or playing else 1))
        p.drawRoundedRect(r, 5, 5)
        f = QFont(option.font)
        f.setPointSizeF(theme.fs(7))
        p.setFont(f)
        p.setPen(theme.qcolor(t.text_faint))
        p.drawText(r.adjusted(5, 2, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, str(index.row() + 1))
        f.setPointSizeF(option.font.pointSizeF())
        f.setBold(True)
        if state == "skipped":
            f.setStrikeOut(True)
        p.setFont(f)
        p.setPen(theme.qcolor(t.error if state in ("missing", "invalid") else t.text))
        p.drawText(r.adjusted(4, 6, -2, 0), Qt.AlignmentFlag.AlignCenter, index.data() or "")
        p.restore()


class ChipList(QListWidget):
    reordered = Signal()

    def __init__(self, sortable: bool = True):
        super().__init__()
        self.playing_row = -1
        self.setViewMode(QListView.ViewMode.ListMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setSpacing(1)
        self.setUniformItemSizes(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        if sortable:
            self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
            self.setDefaultDropAction(Qt.DropAction.MoveAction)
            self.model().rowsMoved.connect(lambda *_: self.reordered.emit())
        self.setItemDelegate(ChipDelegate(self))
        self.setMinimumHeight(96)

    def startDrag(self, actions):
        w = self.parent()
        while w is not None and not isinstance(w, SequenceEditor):
            w = w.parent()
        if w is not None:
            w.ctx.sound("drag_start")
        super().startDrag(actions)

    def dropEvent(self, e):
        super().dropEvent(e)
        self.reordered.emit()


class SequenceEditor(QWidget):
    changed = Signal()

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self._undo: list[list[str]] = []
        self._redo: list[list[str]] = []
        self._task = None
        self._positions: list[tuple[float, int]] = []
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        self.preset = QComboBox()
        self.preset.setMinimumWidth(150)
        self.b_load = button("Load", "import")
        self.b_load.setToolTip("Replace the current sequence with the selected preset")
        self.b_save_as = button("Save as new", "add")
        self.b_save_as.setToolTip("Save the current sequence as a new preset")
        self.more = more_button([
            ("Save into this preset", "save", self.save_preset),
            ("Duplicate this preset", "duplicate", self.duplicate_preset),
            ("Restore the original version", "reset", self.restore_preset),
            ("Import from a file…", "import", self.import_file),
            ("Export to a file…", "export", self.export_file),
            ("Clear the sequence", "trash", self.clear),
        ])
        self.b_save = self.more._actions["Save into this preset"]
        self.b_restore = self.more._actions["Restore the original version"]
        v.addLayout(hbox(label("Preset"), self.preset, self.b_load, self.b_save_as, self.more, None))

        self.input = QLineEdit()
        self.input.setPlaceholderText("Type sample names, e.g.  a e2 o  — Enter adds them")
        self.input.installEventFilter(self)
        self.b_add = button("Add", "add")
        self.b_insert = button("Insert", "add")
        self.b_insert.setToolTip("Insert after the selected element")
        self.b_undo = button("Undo", "undo")
        self.b_undo.setToolTip("Undo the last change (Ctrl+Z)")
        self.b_redo = button("Redo", "redo")
        self.b_redo.setToolTip("Redo (Ctrl+Y)")
        v.addLayout(hbox(self.input, self.b_add, self.b_insert))
        self.seq_help = hint("Click a name to select it, drag to move it, double-click to rename it. "
                             "Red outline = that file is missing.")
        v.addWidget(self.seq_help)

        self.chips = ChipList()
        self.chips.setToolTip("Drag to reorder · Double-click to edit · Del removes · Ctrl+D duplicates")
        v.addWidget(self.chips, 1)
        self.b_remove = button("Remove", "remove")
        self.b_dup_el = button("Duplicate", "duplicate")
        self.b_edit = button("Edit", "edit")
        self.b_play_el = button("Play element", "play")
        self.summary = QWidget()
        self.summary_label = elastic(hint(""))
        self.b_fix = button("Fix missing…", "warning")
        self.b_fix.hide()
        v.addLayout(hbox(self.b_remove, self.b_dup_el, self.b_edit, self.b_play_el, None, self.b_undo, self.b_redo))
        v.addLayout(hbox(None, self.b_fix))
        v.addWidget(self.summary_label)
        self.element_info = hint("")
        v.addWidget(self.element_info)

        v.addWidget(label("Available samples — click to add", "Hint"))
        self.palette = ChipList(sortable=False)
        self.palette.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.palette.setMinimumHeight(44)
        self.palette.setMaximumHeight(84)
        v.addWidget(self.palette)

        self.player = PreviewPlayer(self)
        ctx.register_player(self.player)
        self.prev_kind = Segmented([("original", "Original samples"), ("processed", "Processed (current mode)")],
                                   "original")
        self.b_play_seq = button("Play sequence", "play", "Primary")
        self.prev_status = elastic(label("", "StatusText"))
        self.preview_box = QWidget()
        pv = QVBoxLayout(self.preview_box)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(8)
        pv.addLayout(hbox(self.prev_kind, self.b_play_seq, None))
        pv.addWidget(self.prev_status)
        self.transport = TransportBar(self.player, ctx)
        pv.addWidget(self.transport)
        v.addWidget(self.preview_box)

        self.preset.currentIndexChanged.connect(self._preset_selected)
        self.b_load.clicked.connect(self.load_selected_preset)
        self.b_save_as.clicked.connect(self.save_preset_as)
        self.input.returnPressed.connect(self.add_from_input)
        self.b_add.clicked.connect(self.add_from_input)
        self.b_insert.clicked.connect(lambda: self.add_from_input(insert=True))
        self.b_undo.clicked.connect(self.undo)
        self.b_redo.clicked.connect(self.redo)
        self.b_remove.clicked.connect(self.remove_selected)
        self.b_dup_el.clicked.connect(self.duplicate_selected)
        self.b_edit.clicked.connect(self.edit_selected)
        self.b_play_el.clicked.connect(self.play_selected)
        self.b_fix.clicked.connect(self.fix_missing)
        self.chips.reordered.connect(self._on_reordered)
        self.chips.itemDoubleClicked.connect(lambda _: self.edit_selected())
        self.chips.itemSelectionChanged.connect(self._on_select)
        self.palette.itemClicked.connect(lambda it: self.add_tokens([it.text()]))
        self.b_play_seq.clicked.connect(self.play_sequence)
        self.player.positionChanged.connect(self._follow)
        for keys, fn in (("Delete", self.remove_selected), ("Ctrl+D", self.duplicate_selected),
                         ("F2", self.edit_selected), ("Ctrl+Z", self.undo), ("Ctrl+Y", self.redo),
                         ("Ctrl+Shift+Z", self.redo)):
            sc = QShortcut(QKeySequence(keys), self.chips)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(fn)
        ctx.libraryChanged.connect(self.refresh)
        ctx.presetsChanged.connect(lambda kind: kind == "sequence" and self.refresh_presets())
        self.refresh_presets()
        self.refresh()

    @property
    def tokens(self) -> list[str]:
        return self.ctx.config.order.sequence

    def _set_tokens(self, tokens: list[str], record: bool = True) -> None:
        if record:
            self._undo.append(list(self.tokens))
            self._undo = self._undo[-200:]
            self._redo.clear()
        self.ctx.config.order.sequence = list(tokens)
        self.refresh()
        self.changed.emit()
        self.ctx.touch("order")

    def refresh(self) -> None:
        available = set(self.ctx.library.usable_ids())
        remap = self.ctx.config.order.remap
        statuses = validate_sequence(self.tokens, available, remap)
        sel = {i.row() for i in self.chips.selectedIndexes()}
        self.chips.blockSignals(True)
        self.chips.clear()
        for st in statuses:
            it = QListWidgetItem(st.token)
            it.setData(ROLE_STATE, st.state)
            s = self.ctx.library.get(st.resolved) if st.resolved else None
            tip = f"#{st.position + 1} · {st.token}"
            if st.state == "ok" and s:
                tip += f"\n{s.path}\n{s.duration:.2f} s"
            elif st.state == "remapped":
                tip += "\n" + tr("mapped to {file}", file=f"{st.resolved}.wav")
            elif st.state == "skipped":
                tip += "\nskipped (explicit)"
            else:
                tip += "\n" + tr("{file} is missing", file=f"{st.token}.wav")
            it.setToolTip(tip)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsDragEnabled)
            self.chips.addItem(it)
        for r in sel:
            if r < self.chips.count():
                self.chips.item(r).setSelected(True)
        self.chips.blockSignals(False)
        self.palette.clear()
        for sid in self.ctx.library.usable_ids():
            it = QListWidgetItem(sid)
            it.setData(ROLE_STATE, "ok")
            s = self.ctx.library.get(sid)
            it.setToolTip(f"{s.name} · {s.duration:.2f} s")
            self.palette.addItem(it)
        self.input.setCompleter(QCompleter(self.ctx.library.ids(), self.input))
        n = len(self.tokens)
        missing = sorted({st.token for st in statuses if st.state in ("missing", "invalid")})
        remapped = sum(st.state == "remapped" for st in statuses)
        skipped = sum(st.state == "skipped" for st in statuses)
        txt = tr("{n} elements · {u} unique", n=n, u=len(set(self.tokens)))
        if missing:
            txt += " · " + tr("missing: {files}", files=", ".join(m + ".wav" for m in missing[:6]) +
                               ("…" if len(missing) > 6 else ""))
            set_tone(self.summary_label, "error")
        else:
            txt += tr(" · all samples found") if n else ""
            set_tone(self.summary_label, "")
        if remapped or skipped:
            txt += " · " + tr("{m} mapped, {s} skipped", m=remapped, s=skipped)
        self.summary_label.setText(txt)
        self.summary_label.setObjectName("StatusText")
        self.b_fix.setVisible(bool(missing))
        self.b_undo.setEnabled(bool(self._undo))
        self.b_redo.setEnabled(bool(self._redo))
        self._on_select()

    def add_tokens(self, toks: list[str], insert: bool = False) -> None:
        toks = [normalize_token(t) for t in toks if t.strip()]
        bad = [t for t in toks if not is_valid_token(t)]
        if bad:
            self.ctx.toast(tr("Invalid name(s): {names}", names=", ".join(bad)), "warn")
            toks = [t for t in toks if is_valid_token(t)]
        if not toks:
            return
        seq = list(self.tokens)
        rows = sorted(i.row() for i in self.chips.selectedIndexes())
        at = rows[-1] + 1 if insert and rows else len(seq)
        seq[at:at] = toks
        self._set_tokens(seq)
        self.ctx.sound("seq_add")
        for r in range(at, at + len(toks)):
            if r < self.chips.count():
                self.chips.item(r).setSelected(True)
        self.chips.scrollToItem(self.chips.item(min(at + len(toks) - 1, self.chips.count() - 1)))

    def add_from_input(self, insert: bool = False) -> None:
        toks = parse_sequence_text(self.input.text())
        if toks:
            self.add_tokens(toks, insert=insert)
            self.input.clear()

    def remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.chips.selectedIndexes()}, reverse=True)
        if not rows:
            return
        seq = list(self.tokens)
        for r in rows:
            del seq[r]
        self._set_tokens(seq)
        self.ctx.sound("seq_remove")

    def duplicate_selected(self) -> None:
        rows = sorted({i.row() for i in self.chips.selectedIndexes()})
        if not rows:
            return
        seq = list(self.tokens)
        block = [seq[r] for r in rows]
        seq[rows[-1] + 1:rows[-1] + 1] = block
        self._set_tokens(seq)
        self.ctx.sound("seq_add")

    def edit_selected(self) -> None:
        rows = sorted({i.row() for i in self.chips.selectedIndexes()})
        if len(rows) != 1:
            return
        r = rows[0]
        text, ok = QInputDialog.getText(self, tr("Edit element"), tr("Sample name for element {n}:", n=r + 1),
                                        QLineEdit.EchoMode.Normal, self.tokens[r])
        if ok:
            t = normalize_token(text)
            if not is_valid_token(t):
                self.ctx.toast(tr("'{name}' is not a valid sample name.", name=text), "warn")
                return
            seq = list(self.tokens)
            seq[r] = t
            self._set_tokens(seq)
            self.ctx.sound("confirm")

    def clear(self) -> None:
        if self.tokens:
            self._set_tokens([])
            self.ctx.sound("seq_remove")

    def undo(self) -> None:
        if self._undo:
            self._redo.append(list(self.tokens))
            self._set_tokens(self._undo.pop(), record=False)
            self.ctx.sound("undo")

    def redo(self) -> None:
        if self._redo:
            self._undo.append(list(self.tokens))
            self._set_tokens(self._redo.pop(), record=False)
            self.ctx.sound("undo")

    def _on_reordered(self) -> None:
        new = [self.chips.item(i).text() for i in range(self.chips.count())]
        if new != self.tokens:
            self._set_tokens(new)
            self.ctx.sound("drag_snap")

    def _on_select(self) -> None:
        rows = sorted({i.row() for i in self.chips.selectedIndexes()})
        has = bool(rows)
        for b in (self.b_remove, self.b_dup_el):
            b.setEnabled(has)
        self.b_edit.setEnabled(len(rows) == 1)
        self.b_play_el.setEnabled(len(rows) == 1)
        self.b_insert.setEnabled(has)
        if len(rows) == 1 and rows[0] < len(self.tokens):
            tok = self.tokens[rows[0]]
            st = validate_sequence([tok], set(self.ctx.library.usable_ids()), self.ctx.config.order.remap)[0]
            s = self.ctx.library.get(st.resolved) if st.resolved else None
            if s:
                pitch = f" · {s.pitch.note} {s.pitch.cents:+.0f} ct" if s.pitch and s.pitch.reliable else ""
                self.element_info.setText(tr("Element {n}: {tok} → {file}", n=rows[0] + 1, tok=tok, file=s.name) +
                                          f" · {s.duration:.2f} s · {s.sample_rate} Hz{pitch}")
            else:
                self.element_info.setText(tr("Element {n}: {tok} → {file} not loaded", n=rows[0] + 1, tok=tok,
                                             file=f"{tok}.wav"))
            self.ctx.sound("select")
        else:
            self.element_info.setText(tr("{n} elements selected", n=len(rows)) if rows else "")

    def eventFilter(self, obj, ev):
        if obj is self.input and ev.type() == QEvent.Type.KeyPress and ev.text().strip():
            self.ctx.sound("keyboard")
        return False

    def fix_missing(self) -> bool:
        statuses = validate_sequence(self.tokens, set(self.ctx.library.usable_ids()), self.ctx.config.order.remap)
        missing: dict[str, list[int]] = {}
        for st in statuses:
            if st.state in ("missing", "invalid"):
                missing.setdefault(st.token, []).append(st.position)
        if not missing:
            return True
        dlg = MissingSamplesDialog(self, missing, self.ctx.library.usable_ids())
        if dlg.exec():
            self.ctx.config.order.remap.update(dlg.remap())
            self.refresh()
            self.ctx.touch("order")
            self.ctx.sound("confirm")
            return True
        self.ctx.sound("cancel")
        return False

    def refresh_presets(self) -> None:
        cur = self.preset.currentData() or self.ctx.config.order.sequence_name or BF_CLASSIC_NAME
        self.preset.blockSignals(True)
        self.preset.clear()
        for p in self.ctx.presets.list("sequence"):
            tag = tr(" · built-in") if p.builtin and not p.modified else (tr(" · built-in, changed") if p.modified else "")
            self.preset.addItem(f"{tr(p.name)}{tag}", p.name)
        i = self.preset.findData(cur)
        self.preset.setCurrentIndex(max(0, i))
        self.preset.blockSignals(False)
        self._preset_selected()

    def _preset_selected(self) -> None:
        p = self.ctx.presets.get("sequence", self.preset.currentData() or "")
        self.b_restore.setEnabled(bool(p and p.modified))
        self.b_save.setEnabled(p is not None)

    def load_selected_preset(self) -> None:
        p = self.ctx.presets.get("sequence", self.preset.currentData() or "")
        if p is None:
            return
        self.ctx.config.order.sequence_name = p.name
        self._set_tokens(p.tokens())
        self.ctx.sound("confirm")
        self.ctx.toast(tr("Loaded “{name}” ({n} elements).", name=tr(p.name), n=len(p.tokens())), "ok")

    def save_preset(self) -> None:
        name = self.preset.currentData()
        p = self.ctx.presets.get("sequence", name or "")
        if p is None:
            return self.save_preset_as()
        if p.builtin:
            from .common import confirm
            if not confirm(self, tr("Change built-in preset"),
                           tr("Save your changes over the built-in preset “{name}”? You can restore the original later.",
                              name=tr(name))):
                return
        try:
            self.ctx.presets.save(Preset("sequence", p.name, {"tokens": list(self.tokens)}, p.description))
        except PresetError as exc:
            return self.ctx.toast(str(exc), "error")
        self.ctx.presetsChanged.emit("sequence")
        self.ctx.toast(tr("Saved “{name}”.", name=tr(name)), "ok")

    def save_preset_as(self) -> None:
        name, ok = QInputDialog.getText(self, "Save sequence", "Preset name:",
                                        text=self.ctx.presets.free_name("sequence", "My sequence"))
        if not ok or not name.strip():
            return
        if self.ctx.presets.exists("sequence", name.strip()):
            return self.ctx.toast(tr("A preset named “{name}” already exists.", name=name), "warn")
        try:
            self.ctx.presets.save(Preset("sequence", name.strip(), {"tokens": list(self.tokens)}))
        except PresetError as exc:
            return self.ctx.toast(str(exc), "error")
        self.ctx.config.order.sequence_name = name.strip()
        self.ctx.presetsChanged.emit("sequence")
        self.preset.setCurrentIndex(self.preset.findData(name.strip()))
        self.ctx.toast(tr("Saved “{name}”.", name=name), "ok")

    def duplicate_preset(self) -> None:
        name = self.preset.currentData()
        if not name:
            return
        p = self.ctx.presets.duplicate("sequence", name)
        self.ctx.presetsChanged.emit("sequence")
        self.preset.setCurrentIndex(self.preset.findData(p.name))
        self.ctx.toast(tr("Created “{name}”.", name=p.name), "ok")

    def restore_preset(self) -> None:
        name = self.preset.currentData()
        self.ctx.presets.restore("sequence", name)
        self.ctx.presetsChanged.emit("sequence")
        self.ctx.toast(tr("Restored the original “{name}”.", name=tr(name)), "ok")

    def import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import sequence", "", "Sequence (*.json *.txt);;All files (*)")
        if not path:
            return
        try:
            if path.lower().endswith(".txt"):
                with open(path, encoding="utf-8") as fh:
                    toks = parse_sequence_text(fh.read())
                if not toks:
                    raise ValueError("The file contains no elements.")
                self._set_tokens(toks)
            else:
                p = self.ctx.presets.import_from(path)
                if p.kind != "sequence":
                    raise ValueError(f"This file is a “{p.kind}” preset, not a sequence. It was added to Presets.")
                self.ctx.presetsChanged.emit("sequence")
                self.preset.setCurrentIndex(self.preset.findData(p.name))
                self._set_tokens(p.tokens())
            self.ctx.toast("Sequence imported.", "ok")
        except Exception as exc:
            self.ctx.toast(tr("Import failed: {error}", error=tr(str(exc))), "error")

    def export_file(self) -> None:
        if not self.tokens:
            return self.ctx.toast("The sequence is empty.", "warn")
        path, flt = QFileDialog.getSaveFileName(self, "Export sequence", "sequence.vxpreset.json",
                                                "Voxa GEN preset (*.json);;Plain text (*.txt)")
        if not path:
            return
        try:
            if path.lower().endswith(".txt"):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(" ".join(self.tokens) + "\n")
            else:
                name = self.preset.currentData() or "Sequence"
                data = Preset("sequence", name, {"tokens": list(self.tokens)}).to_file()
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2)
            self.ctx.toast("Sequence exported.", "ok")
        except OSError as exc:
            self.ctx.toast(tr("Export failed: {error}", error=str(exc)), "error")

    def play_selected(self) -> None:
        rows = sorted({i.row() for i in self.chips.selectedIndexes()})
        if len(rows) != 1:
            return
        tok = self.tokens[rows[0]]
        st = validate_sequence([tok], set(self.ctx.library.usable_ids()), self.ctx.config.order.remap)[0]
        s = self.ctx.library.get(st.resolved) if st.resolved else None
        if s is None:
            return self.ctx.toast(tr("{file} is not loaded.", file=f"{tok}.wav"), "warn")
        from ...core.audio.dsp import load_audio
        try:
            x, sr = load_audio(s.path)
        except Exception as exc:
            return self.ctx.toast(tr("Cannot read {file}: {error}", file=s.name, error=str(exc)), "error")
        self._positions = []
        self.player.load({"Original": x}, sr)
        self.player.play()

    def play_sequence(self) -> None:
        if not self.tokens:
            return self.ctx.toast("The sequence is empty.", "warn")
        if not self.fix_missing():
            return
        cfg = copy.deepcopy(self.ctx.config)
        cfg.order.mode = "vocal"
        resolved_rows = [st.position for st in validate_sequence(cfg.order.sequence, set(self.ctx.library.usable_ids()),
                                                                   cfg.order.remap) if st.resolved]
        cfg.musical.semitones = len(resolved_rows)
        original = self.prev_kind.value() == "original"
        library = self.ctx.library
        if self._task is not None and self._task.running:
            self._task.cancel()

        def job(progress, cancelled):
            gen = render_generation(cfg, library, original=original, progress=progress, cancel=cancelled, strict=False)
            return gen, gen.assemble()

        self.prev_status.setText("Rendering sequence…")
        set_tone(self.prev_status, "")
        t = Task(job, "sequence-preview", self)
        t.progress.connect(lambda st, c, n, lbl: self.prev_status.setText(tr("Rendering {c}/{n} · {what}", c=c, n=n, what=lbl)))
        t.succeeded.connect(lambda res: self._play_rendered(res, resolved_rows))
        t.failed.connect(lambda exc: (self.prev_status.setText(tr("Error: {error}", error=str(exc))), set_tone(self.prev_status, "error")))
        self._task = t.start()

    def _play_rendered(self, res, rows) -> None:
        gen, audio = res
        sr = gen.sample_rate
        self._positions = [(p / sr, rows[i]) for i, p in enumerate(gen.positions) if i < len(rows)]
        self.player.load({"Sequence": audio}, sr)
        errs = len(gen.errors)
        self.prev_status.setText(tr("{n} elements · {sec} s", n=len(gen.notes), sec=f"{audio.shape[0] / sr:.1f}") +
                                 (" · " + tr("{n} failed", n=errs) if errs else ""))
        set_tone(self.prev_status, "error" if errs else "ok")
        self.player.play()

    def _follow(self, seconds: float) -> None:
        row = -1
        if self.player.state != "stopped" and self._positions:
            for start, r in self._positions:
                if seconds >= start:
                    row = r
                else:
                    break
        if row != self.chips.playing_row:
            self.chips.playing_row = row
            self.chips.viewport().update()
