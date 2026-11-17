from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHeaderView, QLineEdit, QProgressBar, QTableWidget, QTableWidgetItem,
)

from ...core.export.batch import (
    BatchJob, jobs_from_data, jobs_to_data, make_job, overall_progress, run_batch,
)
from ...core.workers import Task
from ...i18n import tr
from .common import Card, FormGrid, HelpButton, button, confirm, elastic, hbox, hint, label, set_tone

STATUS_TEXT = {"pending": "Waiting", "running": "Running", "done": "Done", "failed": "Failed",
               "cancelled": "Cancelled", "skipped": "Skipped"}
STATUS_TONE = {"done": "ok", "failed": "error", "cancelled": "warn", "skipped": "warn", "running": "accent"}
COLS = ["Job", "Settings", "Destination", "Status", "Progress"]


class BatchPanel(QObject):

    def __init__(self, ctx, host):
        super().__init__(host)
        self.ctx = ctx
        self.host = host
        self.jobs: list[BatchJob] = jobs_from_data(ctx.settings.batch_queue)
        self._task: Task | None = None
        self.queue_card = self._queue_card()
        self.add_card = self._add_card()
        ctx.languageChanged.connect(lambda _: self.refresh())
        self.refresh()

    def _add_card(self) -> Card:
        c = Card("Add to the queue", 'A job is a snapshot of ALL the current Generator settings: samples, order, mode, effects, export. Change something, add another job, and export several versions in one go.')
        g = FormGrid()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Job name (optional)")
        g.row("Name", self.name, "Shown in the queue. Leave it empty to use the export folder name.")
        self.conflict = QComboBox()
        self.conflict.addItem("Use a new numbered folder", "new_folder")
        self.conflict.addItem("Skip the job", "skip")
        g.row("If the folder already has files", self.conflict,
              "Batch jobs never overwrite files. A new numbered folder (for example “Export (2)”) keeps both; "
              "Skip leaves the existing export alone and marks the job as skipped.",
              "Recommended: a new numbered folder.")
        c.add(g)
        b_add = button("Add current settings", "add", "Primary")
        b_add.clicked.connect(self.add_current)
        c.add(hbox(None, b_add))
        return c

    def _queue_card(self) -> Card:
        c = Card("Batch queue", "Jobs run one after another in the background; you can keep working. A job that "
                                "fails does not stop the others.")
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(240)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._selection)
        self.table.itemDoubleClicked.connect(lambda _: self.open_selected())
        c.add(self.table)
        self.detail = elastic(hint(""))
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        c.add(self.detail)
        self.b_up = button("Up", "up")
        self.b_down = button("Down", "down")
        self.b_remove = button("Remove", "trash")
        self.b_retry = button("Run again", "restart")
        self.b_retry.setToolTip("Put a finished, failed or cancelled job back in the queue")
        self.b_open = button("Open folder", "folder")
        self.b_clear = button("Clear finished", "close")
        self.b_up.clicked.connect(lambda: self.move(-1))
        self.b_down.clicked.connect(lambda: self.move(1))
        self.b_remove.clicked.connect(self.remove)
        self.b_retry.clicked.connect(self.retry)
        self.b_open.clicked.connect(self.open_selected)
        self.b_clear.clicked.connect(self.clear_finished)
        c.add(hbox(self.b_up, self.b_down, self.b_remove, self.b_retry, self.b_open, None, self.b_clear))
        self.overall = QProgressBar()
        self.overall.setRange(0, 1000)
        self.summary = label("", "StatusText")
        self.b_start = button("Start queue", "play", "Primary")
        self.b_start.clicked.connect(self.start)
        self.b_cancel = button("Cancel", "close", "Danger")
        self.b_cancel.clicked.connect(self.cancel)
        self.b_cancel.hide()
        help_ = HelpButton("Batch export", 'Exports every waiting job in order, each with its own saved settings. You see progress per job and for the whole queue. Cancel stops the current job (nothing half-written is kept) and leaves the rest waiting.')
        c.add(hbox(self.b_start, self.b_cancel, self.summary, None, help_))
        c.add(self.overall)
        return c

    def save(self) -> None:
        self.ctx.settings.batch_queue = jobs_to_data(self.jobs)
        self.ctx.save_soon()

    def set_jobs(self, jobs: list[BatchJob]) -> None:
        if self.running:
            return
        self.jobs = jobs
        self.save()
        self.refresh()

    def add_current(self) -> None:
        if not self.ctx.library.usable_ids(set(self.ctx.config.disabled_samples)):
            return self.ctx.toast("No usable samples are loaded.", "error")
        job = make_job(self.name.text().strip(), self.ctx.config, self.ctx.library,
                       self.ctx.settings.default_output_dir, self.conflict.currentData())
        self.jobs.append(job)
        self.name.clear()
        self.save()
        self.refresh()
        self.table.selectRow(len(self.jobs) - 1)
        self.ctx.sound("seq_add")
        self.ctx.toast(tr("“{name}” added to the queue ({n} jobs).", name=job.name, n=len(self.jobs)), "ok")

    def _sel(self) -> int:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return rows[0].row() if rows else -1

    def move(self, d: int) -> None:
        i = self._sel()
        j = i + d
        if self.running or not (0 <= i < len(self.jobs) and 0 <= j < len(self.jobs)):
            return
        self.jobs[i], self.jobs[j] = self.jobs[j], self.jobs[i]
        self.save()
        self.refresh()
        self.table.selectRow(j)

    def remove(self) -> None:
        i = self._sel()
        if 0 <= i < len(self.jobs) and not self.running:
            del self.jobs[i]
            self.save()
            self.refresh()
            self.ctx.sound("seq_remove")

    def retry(self) -> None:
        i = self._sel()
        if 0 <= i < len(self.jobs) and self.jobs[i].finished:
            self.jobs[i].reset()
            self.save()
            self.refresh()
            self.table.selectRow(i)

    def clear_finished(self) -> None:
        if self.running:
            return
        self.jobs = [j for j in self.jobs if j.status in ("pending", "running")]
        self.save()
        self.refresh()

    def open_selected(self) -> None:
        i = self._sel()
        if 0 <= i < len(self.jobs) and self.jobs[i].result_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.jobs[i].result_folder))

    @property
    def running(self) -> bool:
        return self._task is not None and self._task.running

    def start(self) -> None:
        if self.running:
            return
        if self.ctx.busy:
            return self.ctx.toast("Wait for the current export to finish.", "warn")
        pending = [j for j in self.jobs if j.status == "pending"]
        if not pending:
            return self.ctx.toast("No waiting jobs in the queue. Add one, or use “Run again”.", "warn")
        jobs = list(self.jobs)

        def job(progress, cancelled):
            def on_event(i, j):
                progress("job", i, len(jobs), j.status)
            return run_batch(jobs, on_event, cancelled)

        self.ctx.set_busy(True)
        self.ctx.sound("export_start")
        t = Task(job, "batch", self.host)
        t.progress.connect(lambda *_: self.refresh(live=True))
        t.succeeded.connect(self._finished)
        t.cancelled.connect(self._finished)
        t.failed.connect(lambda exc: self.ctx.notify("Batch export failed", str(exc), "error"))
        t.finished.connect(self._done)
        self._task = t.start()
        self.refresh()

    def cancel(self) -> None:
        if self.running:
            if self.ctx.settings.confirm_on_cancel and not confirm(
                    self.host, tr("Cancel batch"), tr("Stop the queue? The current job is cancelled and nothing "
                                                      "half-written is kept.")):
                return
            self._task.cancel()
            self.b_cancel.setEnabled(False)

    def _finished(self, *_):
        for j in self.jobs:
            if j.status == "running":
                j.status = "cancelled"
        done = sum(j.status == "done" for j in self.jobs)
        failed = sum(j.status == "failed" for j in self.jobs)
        other = sum(j.status in ("cancelled", "skipped") for j in self.jobs)
        msg = tr("{done} done · {failed} failed · {other} cancelled or skipped", done=done, failed=failed, other=other)
        tone = "error" if failed else ("warn" if other else "ok")
        from .notifier import Action
        last = next((j.result_folder for j in reversed(self.jobs) if j.status == "done"), "")
        actions = [Action(tr("Open folder"), lambda f=last: QDesktopServices.openUrl(QUrl.fromLocalFile(f)),
                          primary=True)] if last else []
        self.ctx.sound("export_done" if not failed else "error")
        self.ctx.notify("Batch export finished", msg, tone, actions)

    def _done(self) -> None:
        self.ctx.set_busy(False)
        self.save()
        self.refresh()

    def refresh(self, live: bool = False) -> None:
        sel = self._sel()
        self.table.setRowCount(len(self.jobs))
        for r, j in enumerate(self.jobs):
            cells = [j.name, _summary(j), j.result_folder or j.destination,
                     tr(STATUS_TEXT.get(j.status, j.status)), f"{int(round(j.progress * 100))} %"]
            for c, text in enumerate(cells):
                it = self.table.item(r, c)
                if it is None:
                    it = QTableWidgetItem()
                    self.table.setItem(r, c, it)
                it.setText(text)
                if c == 3:
                    from .. import theme
                    tone = STATUS_TONE.get(j.status, "")
                    t = theme.current()
                    it.setForeground(theme.qcolor({"ok": t.ok, "error": t.error, "warn": t.warn,
                                                   "accent": t.accent}.get(tone, t.text_muted)))
                it.setToolTip(j.error or text)
        self.table.setHorizontalHeaderLabels([tr(c) for c in COLS])
        self.overall.setValue(int(overall_progress(self.jobs) * 1000))
        n = len(self.jobs)
        waiting = sum(j.status == "pending" for j in self.jobs)
        if self.running:
            cur = next((j for j in self.jobs if j.status == "running"), None)
            self.summary.setText(tr("Running “{name}” · {n} waiting", name=cur.name if cur else "…", n=waiting))
            set_tone(self.summary, "")
        else:
            self.summary.setText(tr("{n} jobs · {w} waiting", n=n, w=waiting) if n else tr("The queue is empty."))
            set_tone(self.summary, "")
        self.b_start.setVisible(not self.running)
        self.b_cancel.setVisible(self.running)
        self.b_cancel.setEnabled(True)
        if 0 <= sel < n and not live:
            self.table.selectRow(sel)
        self._selection()

    def _selection(self) -> None:
        i = self._sel()
        has = 0 <= i < len(self.jobs)
        busy = self.running
        self.b_up.setEnabled(has and not busy and i > 0)
        self.b_down.setEnabled(has and not busy and i < len(self.jobs) - 1)
        self.b_remove.setEnabled(has and not busy)
        self.b_retry.setEnabled(has and not busy and self.jobs[i].finished)
        self.b_open.setEnabled(has and bool(self.jobs[i].result_folder))
        self.b_clear.setEnabled(not busy and any(j.finished for j in self.jobs))
        if has:
            j = self.jobs[i]
            lines = [tr("{n} samples · destination: {dest}", n=len(j.samples), dest=j.destination)]
            if j.error:
                lines.append(tr("Error: {error}", error=j.error))
            if j.warnings:
                lines.append("⚠ " + tr(j.warnings[0]))
            self.detail.setText("\n".join(lines))
        else:
            self.detail.setText(tr("Select a job to see its details. Double-click a finished job to open its folder."))
        self.detail.setProperty("i18n_text_skip", True)


ORDER_TEXT = {"sequential": "In order", "shuffle": "Shuffle", "random": "Random", "vocal": "Vocal sequence"}


def _summary(job: BatchJob) -> str:
    cfg = job.typed_config()
    mode = tr(cfg.mode.title())
    if cfg.effects.enabled and any(s.enabled for s in cfg.effects.chain):
        mode += tr(" + effects")
    return f"{mode} · " + tr("{n} notes", n=cfg.musical.semitones) + " · " + tr(ORDER_TEXT.get(cfg.order.mode,
                                                                                           cfg.order.mode))
