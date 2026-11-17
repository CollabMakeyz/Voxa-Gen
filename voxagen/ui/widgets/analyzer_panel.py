from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QProgressBar, QTableWidget, QTableWidgetItem, QWidget,
)

from ...core.samples.analyzer import AnalysisReport, analyze_library
from ...core.workers import Task
from ...i18n import tr
from .. import icons, theme
from .common import Card, HelpButton, button, elastic, hbox, hint, label, set_tone

SEVERITY_TEXT = {"error": "Problem", "warn": "Check", "info": "Note"}
SEVERITY_ICON = {"error": "error", "warn": "warning", "info": "info"}


class AnalyzerPanel(QWidget):
    sampleActivated = Signal(str)

    def __init__(self, ctx):
        super().__init__()
        from PySide6.QtWidgets import QVBoxLayout
        self.ctx = ctx
        self._task: Task | None = None
        self.report: AnalysisReport | None = None
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(16)
        c = Card("Check samples", 'Looks for whatever would make a chromatic sound wrong: missing or unreadable files, silence, clipping, notes much louder or quieter than the rest, very different lengths. Files are only read, never changed.')
        self.b_run = button("Check all samples", "analyze", "Primary")
        self.b_run.clicked.connect(self.run)
        self.b_cancel = button("Cancel", "close")
        self.b_cancel.hide()
        self.b_cancel.clicked.connect(lambda: self._task and self._task.cancel())
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(200)
        self.progress.hide()
        help_ = HelpButton("Sample check", "Each finding says what is wrong and how to fix it. “Problem” will "
                                           "break or silence notes; “Check” will probably sound uneven; “Note” is "
                                           "information only. Double-click a finding to select that sample.",
                           "Run it again after you change or replace files.")
        c.add(hbox(self.b_run, self.b_cancel, self.progress, None, help_))
        self.summary = elastic(label("", "StatusText"))
        c.add(self.summary)
        self.table = QTableWidget(0, 4)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setWordWrap(True)
        self.table.setMinimumHeight(260)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(self._activate)
        c.add(self.table)
        v.addWidget(c, 1)

        st = Card("Technical details", "Measured per sample: peak level, loudness of the sung part, silence "
                                       "before and after, length and format.")
        self.stats = QTableWidget(0, 8)
        self.stats.verticalHeader().hide()
        self.stats.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stats.setShowGrid(False)
        self.stats.setSortingEnabled(True)
        self.stats.setMinimumHeight(180)
        self.stats.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.stats.horizontalHeader().setStretchLastSection(True)
        st.add(self.stats)
        v.addWidget(st, 1)
        ctx.libraryChanged.connect(self._stale)
        ctx.languageChanged.connect(lambda _: self.show_report())
        self.show_report()

    def _stale(self) -> None:
        if self.report is not None:
            self.summary.setText(tr("Samples changed since the last check. Run it again."))
            set_tone(self.summary, "warn")

    def run(self) -> None:
        if self._task is not None and self._task.running:
            return
        lib = self.ctx.library
        if not len(lib):
            return self.ctx.toast("No samples loaded.", "warn")
        disabled = set(self.ctx.config.disabled_samples)

        def job(progress, cancelled):
            return analyze_library(lib, disabled, progress, cancelled)

        self.b_run.setEnabled(False)
        self.b_cancel.show()
        self.progress.show()
        self.progress.setRange(0, len(lib))
        self.progress.setValue(0)
        t = Task(job, "analyze", self)
        t.progress.connect(lambda _s, cur, total, _l: self.progress.setValue(cur))
        t.succeeded.connect(self._done)
        t.failed.connect(lambda exc: self.ctx.toast(tr("Check failed: {error}", error=str(exc)), "error"))
        t.cancelled.connect(lambda: self.ctx.toast("Check cancelled.", "info"))
        t.finished.connect(self._finished)
        self._task = t.start()

    def _finished(self) -> None:
        self.b_run.setEnabled(True)
        self.b_cancel.hide()
        self.progress.hide()

    def _done(self, rep: AnalysisReport) -> None:
        self.report = rep
        self.show_report()
        e, w = rep.count("error"), rep.count("warn")
        self.ctx.sound("confirm" if not e else "error")

    def show_report(self) -> None:
        rep = self.report
        self.table.setHorizontalHeaderLabels([tr("Level"), tr("Sample"), tr("What is wrong"), tr("How to fix it")])
        self.stats.setHorizontalHeaderLabels([tr("Sample"), tr("Peak"), tr("Loudness"), tr("Silence before"),
                                              tr("Silence after"), tr("Length"), tr("Format"), tr("Clipped")])
        if rep is None:
            self.summary.setText(tr("Not checked yet. Run a check before exporting to catch problems early."))
            set_tone(self.summary, "")
            self.table.setRowCount(0)
            self.stats.setRowCount(0)
            return
        e, w, i = rep.count("error"), rep.count("warn"), rep.count("info")
        if not rep.findings:
            self.summary.setText(tr("No problems found in {n} samples.", n=len(rep.stats)))
            set_tone(self.summary, "ok")
        else:
            self.summary.setText(tr("{e} problems · {w} to check · {i} notes", e=e, w=w, i=i))
            set_tone(self.summary, "error" if e else ("warn" if w else "ok"))
        t = theme.current()
        self.table.setRowCount(len(rep.findings))
        for r, f in enumerate(rep.findings):
            sev = QTableWidgetItem(tr(SEVERITY_TEXT[f.severity]))
            sev.setIcon(icons.icon(SEVERITY_ICON[f.severity], color={"error": t.error, "warn": t.warn}.get(f.severity, t.text_muted)))
            sid = QTableWidgetItem(f.sample_id or tr("All samples"))
            sid.setData(Qt.ItemDataRole.UserRole, f.sample_id)
            for c, it in enumerate((sev, sid, QTableWidgetItem(f.message), QTableWidgetItem(f.fix))):
                it.setToolTip(it.text())
                self.table.setItem(r, c, it)
        self.table.resizeRowsToContents()
        self.stats.setSortingEnabled(False)
        self.stats.setRowCount(len(rep.stats))
        for r, st in enumerate(rep.stats.values()):
            vals = [st.id, f"{st.peak_db:.1f} dBFS", f"{st.rms_db:.1f} dB" if st.rms_db > -119 else "—",
                    f"{st.lead_ms:.0f} ms", f"{st.tail_ms:.0f} ms", f"{st.duration:.2f} s",
                    f"{st.sample_rate} Hz · {tr(st.format)} · {st.channels} ch", str(st.clipped)]
            for c, text in enumerate(vals):
                self.stats.setItem(r, c, QTableWidgetItem(text))
        self.stats.setSortingEnabled(True)

    def _activate(self, it) -> None:
        sid = self.table.item(it.row(), 1).data(Qt.ItemDataRole.UserRole)
        if sid:
            self.sampleActivated.emit(sid)
