from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHeaderView, QLineEdit, QProgressBar, QSplitter,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...core.audio.dsp import load_audio
from ...core.pitch.detect import detect_pitch
from ...core.samples.naming import classify, natural_key
from ...core.workers import Task
from ...i18n import tr
from .. import theme
from ..widgets.common import Card, DropZone, EmptyState, button, confirm, hbox, hint, label, set_tone, tool_button
from ..widgets.sample_preview import SamplePreview
from .base import Page

COLUMNS = ["Use", "ID", "File", "Duration", "Rate", "Bit depth", "Ch", "Pitch", "Confidence", "Status"]
FILTERS = [("all", "All samples"), ("numbered", "Numbered (1, 2, 3…)"), ("lettered", "Letters (a, e, i…)"),
           ("variation", "Variations (a2, e3…)"), ("other", "Other names"), ("missing", "Missing files"),
           ("duplicates", "Duplicates"), ("errors", "Unreadable"), ("disabled", "Not in use"),
           ("uncertain", "Uncertain pitch")]


class _SortItem(QTableWidgetItem):
    def __init__(self, text: str, key):
        super().__init__(text)
        self.key = key

    def __lt__(self, other):
        try:
            return self.key < other.key
        except TypeError:
            return str(self.key) < str(other.key)


class SampleManagerPage(Page):
    page_id = "samples"
    title = "Sample Manager"
    subtitle = "Every sample, its format, its note and a preview. Your files are never changed."
    icon = "samples"

    def __init__(self, ctx):
        super().__init__(ctx)
        self._task: Task | None = None
        b_files = button("Add files", "add")
        b_files.clicked.connect(self.add_files)
        b_folder = button("Add folder", "folder")
        b_folder.clicked.connect(self.add_folder)
        b_reload = button("Rescan", "refresh")
        b_reload.setToolTip("Read every file again from disk (finds changed, new and missing files)")
        b_reload.clicked.connect(self.reload)
        self.header.addLayout(hbox(b_files, b_folder, b_reload))

        self.filter = QComboBox()
        for k, t in FILTERS:
            self.filter.addItem(t, k)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.search.setClearButtonEnabled(True)
        self.b_detect = button("Find the notes", "wave")
        self.b_detect.setToolTip("Detect which note each sample is sung on (selected samples, or all of them)")
        self.b_cancel = button("Cancel", "close")
        self.b_cancel.hide()
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(140)
        self.progress.hide()
        self.b_replace = button("Replace…", "file")
        self.b_replace.setToolTip("Point this identifier at another file (the identifier is kept)")
        self.b_remove = button("Remove from session", "remove")
        self.b_remove.setToolTip("Removes from Voxa GEN only; the file is not deleted")
        self.b_toggle = button("Use / don't use", "check")
        self.b_toggle.setToolTip("Include or leave out the selected samples when the chromatic is generated")

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setShowGrid(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(26)

        list_card = Card("Samples", "Tick “Use” to include a sample in the chromatic. “Find the notes” detects the "
                                    "pitch of each sample; “uncertain” means it could not be measured reliably.")
        list_card.add(hbox(self.filter, self.search, None, self.b_detect, self.b_cancel, self.progress))
        list_card.add(self.table)
        list_card.add(hbox(self.b_toggle, self.b_replace, self.b_remove, None))
        list_card.add(self._summary_label())
        drop = DropZone("Drop WAV files or folders to add them to the session")
        drop.dropped.connect(self.add_paths)
        drop.clicked.connect(self.add_files)
        list_card.add(drop)

        detail = Card("Selected sample", "Details of the sample you clicked, and how it sounds before and after "
                                         "processing.")
        self.detail_info = hint("Select a sample to see its details.")
        self.detail_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail.add(self.detail_info)
        detail.add(label("Listen", "SubTitle"))
        self.preview = SamplePreview(ctx, show_selector=False)
        detail.add(self.preview)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setHandleWidth(16)
        split.setChildrenCollapsible(False)
        split.addWidget(list_card)
        split.addWidget(detail)
        split.setStretchFactor(0, 6)
        split.setStretchFactor(1, 5)

        self.stack = QStackedWidget()
        self.stack.addWidget(EmptyState("samples", "No samples yet",
                                        "Add a folder of WAV files. Names like 1.wav, a.wav or e2.wav are recognised "
                                        "automatically; any other name works too.", "Add folder", self.add_folder))
        self.stack.addWidget(split)
        self.root.addWidget(self.stack, 1)

        self.filter.currentIndexChanged.connect(lambda _: self.refresh())
        self.search.textChanged.connect(lambda _: self.refresh())
        self.table.itemSelectionChanged.connect(self._selection)
        self.table.itemChanged.connect(self._item_changed)
        self.b_detect.clicked.connect(self.detect_pitch)
        self.b_cancel.clicked.connect(lambda: self._task and self._task.cancel())
        self.b_replace.clicked.connect(self.replace)
        self.b_remove.clicked.connect(self.remove)
        self.b_toggle.clicked.connect(self.toggle_use)
        ctx.libraryChanged.connect(self.refresh)
        self.refresh()

    def _summary_label(self):
        self.summary = label("", "StatusText")
        return self.summary

    def _visible(self, s) -> bool:
        f = self.filter.currentData()
        disabled = set(self.ctx.config.disabled_samples)
        q = self.search.text().strip().lower()
        if q and q not in s.id and q not in s.path.lower():
            return False
        return {
            "all": True,
            "missing": s.status == "missing",
            "duplicates": bool(s.duplicate_of),
            "errors": s.status == "error",
            "disabled": s.id in disabled,
            "uncertain": s.pitch is not None and not s.pitch.reliable,
        }.get(f, classify(s.id) == f)

    def refresh(self) -> None:
        lib = self.ctx.library
        self.stack.setCurrentIndex(1 if len(lib) else 0)
        selected = self.selected_ids()
        disabled = set(self.ctx.config.disabled_samples)
        t = theme.current()
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for s in lib.samples():
            if not self._visible(s):
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            use = _SortItem("", s.id not in disabled)
            use.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            use.setCheckState(Qt.CheckState.Checked if s.id not in disabled else Qt.CheckState.Unchecked)
            use.setData(Qt.ItemDataRole.UserRole, s.id)
            self.table.setItem(r, 0, use)
            p = s.pitch
            if p is None:
                pitch, conf = tr("not analysed"), "—"
            elif p.reliable:
                pitch, conf = f"{p.note} {p.cents:+.0f} ct · {p.median_hz:.1f} Hz", f"{p.confidence:.0%}"
            else:
                pitch, conf = tr("uncertain — {reason}", reason=tr(p.reason)), f"{p.confidence:.0%}"
            status = {"ok": tr("OK"), "missing": tr("Missing file"), "error": tr(s.error or "Error")}[s.status]
            if s.duplicate_of:
                status += " · " + tr("duplicate of {id}", id=s.duplicate_of)
            if s.id in disabled:
                status += " · " + tr("not in use")
            cells = [
                _SortItem(s.id, natural_key(s.id)), _SortItem(s.name, s.name.lower()),
                _SortItem(f"{s.duration:.3f} s" if s.duration else "—", s.duration),
                _SortItem(f"{s.sample_rate} Hz" if s.sample_rate else "—", s.sample_rate),
                _SortItem(s.bit_depth_label if s.sample_rate else "—", s.subtype),
                _SortItem(str(s.channels) if s.channels else "—", s.channels),
                _SortItem(pitch, p.median_hz if p else -1), _SortItem(conf, p.confidence if p else -1),
                _SortItem(status, status),
            ]
            for c, it in enumerate(cells, start=1):
                it.setData(Qt.ItemDataRole.UserRole, s.id)
                if c == 7 and p is not None and not p.reliable:
                    it.setForeground(QColor(t.warn))
                if c == 9 and s.status != "ok":
                    it.setForeground(QColor(t.error))
                elif c == 9 and s.duplicate_of:
                    it.setForeground(QColor(t.warn))
                if c == 2:
                    it.setToolTip(s.path)
                self.table.setItem(r, c, it)
        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)
        for r in range(self.table.rowCount()):
            if self.table.item(r, 1).data(Qt.ItemDataRole.UserRole) in selected:
                self.table.selectRow(r)
        n = len(lib)
        miss, dup = len(lib.missing()), len(lib.duplicates())
        err = sum(1 for s in lib.samples() if s.status == "error")
        self.summary.setText(tr("{shown} shown · {n} total · {miss} missing · {dup} duplicate · {err} unreadable",
                                shown=self.table.rowCount(), n=n, miss=miss, dup=dup, err=err))
        self.table.setHorizontalHeaderLabels([tr(c) for c in COLUMNS])
        set_tone(self.summary, "error" if miss or err else ("warn" if dup else ""))
        self._selection()

    def selected_ids(self) -> list[str]:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.table.item(r, 1).data(Qt.ItemDataRole.UserRole) for r in rows if self.table.item(r, 1)]

    def _selection(self) -> None:
        ids = self.selected_ids()
        one = len(ids) == 1
        self.b_replace.setEnabled(one)
        self.b_remove.setEnabled(bool(ids))
        self.b_toggle.setEnabled(bool(ids))
        if not one:
            self.detail_info.setText(tr("{n} samples selected.", n=len(ids)) if ids else
                                     tr("Select a sample to see its details."))
            return
        s = self.ctx.library.get(ids[0])
        if s is None:
            return
        lines = [f"<b>{s.id}</b> · {s.name}", s.path]
        if s.status == "ok":
            lines.append(f"{s.duration:.3f} s · {s.sample_rate} Hz · {tr(s.bit_depth_label)} · "
                         + (tr("mono") if s.channels == 1 else tr("{n} channels", n=s.channels))
                         + " · " + tr("{n} frames", n=s.frames))
        else:
            lines.append(f"<span style='color:{theme.current().error}'>{tr(s.error)}</span>")
        if s.pitch:
            p = s.pitch
            if p.reliable:
                lines.append(tr("Pitch {note} ({hz} Hz) · voiced {v} · spread {sp} ct · confidence {c}",
                                note=f"{p.note} {p.cents:+.1f} ct", hz=f"{p.median_hz:.2f}", v=f"{p.voiced_ratio:.0%}",
                                sp=f"{p.spread_cents:.0f}", c=f"{p.confidence:.0%}"))
            else:
                lines.append(tr("Pitch not reliable: {reason}", reason=tr(p.reason)))
        if s.duplicate_of:
            lines.append(tr("Identical content to {id}", id=f"<b>{s.duplicate_of}</b>"))
        self.detail_info.setText("<br>".join(lines))
        self.detail_info.setProperty("i18n_text_skip", True)
        if s.usable:
            self.preview.set_sample(s.id, render=False)
            if s.pitch and s.pitch.reliable:
                self.preview.use_detected_pitch()
            else:
                self.preview.request_render()
        self.ctx.sound("select")

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        self._set_use([sid], item.checkState() == Qt.CheckState.Checked)

    def _set_use(self, ids: list[str], use: bool) -> None:
        disabled = set(self.ctx.config.disabled_samples)
        disabled = disabled - set(ids) if use else disabled | set(ids)
        self.ctx.config.disabled_samples = sorted(disabled, key=natural_key)
        self.ctx.touch("samples")
        self.ctx.libraryChanged.emit()

    def toggle_use(self) -> None:
        ids = self.selected_ids()
        disabled = set(self.ctx.config.disabled_samples)
        self._set_use(ids, any(i in disabled for i in ids))

    def add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, tr("Add WAV files"), self.ctx.config.sample_folder,
                                                tr("WAV audio (*.wav)"))
        if files:
            self.add_paths(files)

    def add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Add folder"), self.ctx.config.sample_folder or os.path.expanduser("~"))
        if d:
            if not len(self.ctx.library):
                self.ctx.config.sample_folder = d
            self.add_paths([d])

    def add_paths(self, paths) -> None:
        res = self.ctx.library.add_files(paths)
        self.ctx.remember_samples()
        self.ctx.libraryChanged.emit()
        msg = tr("{n} sample(s) added", n=len(res.added))
        if res.skipped:
            msg += " · " + tr("{n} non-WAV file(s) ignored", n=len(res.skipped))
        if res.conflicts:
            msg += " · " + tr("name conflict: {names} (already loaded from another folder)",
                              names=", ".join(sorted({c[1] for c in res.conflicts})))
        self.ctx.toast(msg, "warn" if res.conflicts else "ok")

    def reload(self) -> None:
        changed = self.ctx.library.reload()
        self.ctx.libraryChanged.emit()
        self.ctx.toast(tr("Reloaded · {c} changed · {a} new · {m} missing", c=len(changed), a=0,
                          m=len(self.ctx.library.missing())), "ok")

    def replace(self) -> None:
        ids = self.selected_ids()
        if len(ids) != 1:
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("Replace “{id}”", id=ids[0]),
                                              os.path.dirname(self.ctx.library.get(ids[0]).path), tr("WAV audio (*.wav)"))
        if not path:
            return
        info = self.ctx.library.replace(ids[0], path)
        self.ctx.remember_samples()
        self.ctx.libraryChanged.emit()
        self.ctx.toast(tr("“{id}” now uses {file}", id=ids[0], file=os.path.basename(path)) +
                       ("" if info.usable else f" ({tr(info.error)})"), "ok" if info.usable else "error")

    def remove(self) -> None:
        ids = self.selected_ids()
        if not ids:
            return
        if not confirm(self, tr("Remove from session"), tr("Remove {n} sample(s) from this session? The files on "
                                                           "disk are not touched.", n=len(ids))):
            return
        for sid in ids:
            self.ctx.library.remove(sid)
        self.ctx.remember_samples()
        self.ctx.libraryChanged.emit()
        self.ctx.sound("seq_remove")

    def detect_pitch(self) -> None:
        ids = self.selected_ids() or [s.id for s in self.ctx.library.samples() if s.usable]
        samples = [(s.id, s.path) for s in (self.ctx.library.get(i) for i in ids) if s and s.usable]
        if not samples:
            return
        a4 = self.ctx.config.musical.a4_hz

        def job(progress, cancelled):
            out = {}
            for i, (sid, path) in enumerate(samples):
                if cancelled():
                    break
                progress("pitch", i, len(samples), sid)
                x, sr = load_audio(path)
                out[sid] = detect_pitch(x, sr, a4)
            return out

        self.progress.setRange(0, len(samples))
        self.progress.show()
        self.b_cancel.show()
        self.b_detect.setEnabled(False)
        t = Task(job, "pitch", self)
        t.progress.connect(lambda st, c, n, lbl: self.progress.setValue(c))
        t.succeeded.connect(self._pitch_done)
        t.failed.connect(lambda exc: self.ctx.toast(tr("Pitch detection failed: {error}", error=str(exc)), "error"))
        t.cancelled.connect(lambda: self.ctx.toast("Pitch detection cancelled.", "warn"))
        t.finished.connect(lambda: (self.progress.hide(), self.b_cancel.hide(), self.b_detect.setEnabled(True)))
        self._task = t.start()

    def _pitch_done(self, out: dict) -> None:
        for sid, info in out.items():
            self.ctx.library.set_pitch(sid, info)
        unreliable = sum(1 for p in out.values() if not p.reliable)
        self.refresh()
        self.ctx.toast(tr("Pitch analysed for {n} sample(s)", n=len(out)) +
                       (" · " + tr("{n} without enough confidence", n=unreliable) if unreliable else ""),
                       "warn" if unreliable else "ok")


class SampleManagerView(SampleManagerPage):
    show_title = False

    def __init__(self, ctx):
        super().__init__(ctx)
        self.root.setContentsMargins(0, 0, 0, 0)

    def select(self, sample_id: str) -> None:
        self.filter.setCurrentIndex(0)
        self.search.clear()
        for r in range(self.table.rowCount()):
            if self.table.item(r, 1).data(Qt.ItemDataRole.UserRole) == sample_id:
                self.table.selectRow(r)
                self.table.scrollToItem(self.table.item(r, 1))
                return
