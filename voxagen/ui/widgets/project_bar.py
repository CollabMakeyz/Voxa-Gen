from __future__ import annotations

import copy
import os
from dataclasses import fields
from pathlib import Path

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMenu,
    QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout,
)

from ...core.export.batch import jobs_from_data, jobs_to_data
from ...core.projects import PROJECT_EXT, LoadedProject, ProjectError, find_in_folder, load_project, save_project
from ...i18n import tr
from ...models.config import GeneratorConfig
from ...paths import user_data_dir
from .. import icons
from .common import button, confirm, hbox, hint, label


class MissingSamplesProjectDialog(QDialog):

    def __init__(self, parent, project: LoadedProject):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Samples not found")
        self.setMinimumWidth(640)
        v = QVBoxLayout(self)
        v.addWidget(label("Some samples of this project are not where they were saved.", "SubTitle"))
        v.addWidget(hint('Locate each file, or search a folder and its subfolders for all of them at once. Files are found by name; if several share the name, the one with the same content wins. You can also open the project without them: they stay listed as missing.'))
        self.table = QTableWidget(0, 3)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        v.addWidget(self.table)
        b_locate = button("Locate selected…", "file")
        b_locate.clicked.connect(self.locate)
        b_search = button("Search a folder…", "search")
        b_search.clicked.connect(self.search)
        v.addLayout(hbox(b_locate, b_search, None))
        self.status = hint("")
        v.addWidget(self.status)
        bb = QDialogButtonBox()
        self.b_ok = bb.addButton(tr("Open project"), QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton(tr("Cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.refresh()

    def refresh(self) -> None:
        samples = [s for s in self.project.samples if not s.resolved or s.changed]
        self.table.setHorizontalHeaderLabels([tr("Sample"), tr("State"), tr("File")])
        self.table.setRowCount(len(samples))
        for r, s in enumerate(samples):
            state = tr("Found (content changed)") if s.resolved and s.changed else (
                tr("Found") if s.resolved else tr("Missing"))
            for c, text in enumerate((s.id, state, s.resolved or s.path)):
                it = QTableWidgetItem(text)
                it.setData(Qt.ItemDataRole.UserRole, s.id)
                self.table.setItem(r, c, it)
        miss = len(self.project.missing)
        self.status.setText(tr("{n} still missing.", n=miss) if miss else tr("Every sample was found."))

    def _selected_id(self) -> str:
        rows = self.table.selectionModel().selectedRows()
        return self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole) if rows else ""

    def locate(self) -> None:
        sid = self._selected_id()
        s = next((x for x in self.project.samples if x.id == sid), None)
        if s is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("Locate “{id}”", id=sid), str(Path(s.path).parent),
                                              tr("WAV audio (*.wav)"))
        if path:
            s.resolved, s.changed = path, False
            self.refresh()

    def search(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("Search a folder for the missing samples"))
        if not folder:
            return
        found = find_in_folder(self.project.missing, folder)
        for s in self.project.samples:
            if s.id in found:
                s.resolved, s.changed = found[s.id], False
        self.refresh()


class ProjectController(QObject):

    def __init__(self, ctx, host, batch_panel=None):
        super().__init__(host)
        self.ctx = ctx
        self.host = host
        self.batch = batch_panel
        self.path: Path | None = None
        self.created = ""
        self.dirty = False
        self._quiet = False
        self.name_label = QLabel()
        self.name_label.setObjectName("Hint")
        self.name_label.setProperty("i18n_text_skip", True)
        self.b_new = button("New", "add")
        self.b_new.setToolTip("Start a new, empty project (samples and settings are reset)")
        self.b_open = QToolButton()
        self.b_open.setObjectName("MoreButton")
        self.b_open.setText("Open")
        self.b_open.setIcon(icons.icon("folder", size=16))
        self.b_open.setProperty("icon_name", "folder")
        self.b_open.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.b_open.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.b_open.setToolTip("Open a project (.vxproj). The arrow lists recent projects.")
        self.b_open.clicked.connect(self.open_dialog)
        self.recent_menu = QMenu(self.b_open)
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        self.b_open.setMenu(self.recent_menu)
        self.b_save = button("Save", "save")
        self.b_save.setToolTip("Save the project (Ctrl+S)")
        self.b_save.clicked.connect(self.save)
        self.b_save_as = button("Save as…", "save")
        self.b_save_as.clicked.connect(self.save_as)
        self.b_new.clicked.connect(self.new)
        ctx.configChanged.connect(self._changed)
        ctx.libraryChanged.connect(lambda: self._changed("samples"))
        ctx.languageChanged.connect(lambda _: self._update_label())
        self._update_label()

    def widgets(self) -> QHBoxLayout:
        icon_l = QLabel()
        icon_l.setPixmap(icons.icon("project", size=18).pixmap(18, 18))
        return hbox(icon_l, self.name_label, None, self.b_new, self.b_open, self.b_save, self.b_save_as)

    def _changed(self, section: str = "") -> None:
        if self._quiet:
            return
        if not self.dirty:
            self.dirty = True
            self._update_label()

    def _update_label(self) -> None:
        name = self.path.stem if self.path else tr("Untitled project")
        self.name_label.setText(name + ("  •  " + tr("unsaved changes") if self.dirty and self.path else ""))
        self.name_label.setToolTip(str(self.path) if self.path else tr("Not saved as a project yet"))

    def _remember(self, path: Path) -> None:
        rec = self.ctx.settings.recent_projects
        p = str(path)
        if p in rec:
            rec.remove(p)
        rec.insert(0, p)
        del rec[10:]
        self.ctx.save_soon()

    def _fill_recent(self) -> None:
        self.recent_menu.clear()
        rec = [p for p in self.ctx.settings.recent_projects if os.path.isfile(p)]
        if not rec:
            a = self.recent_menu.addAction(tr("No recent projects"))
            a.setEnabled(False)
        for p in rec:
            a = self.recent_menu.addAction(Path(p).stem)
            a.setToolTip(p)
            a.triggered.connect(lambda _=False, path=p: self.open(path))

    def confirm_discard(self) -> bool:
        if not (self.dirty and self.path):
            return True
        return confirm(self.host, tr("Unsaved changes"),
                       tr("“{name}” has unsaved changes. Continue without saving them?", name=self.path.stem),
                       tr("Continue without saving"), danger=True)

    def _default_dir(self) -> str:
        if self.path:
            return str(self.path.parent)
        d = user_data_dir() / "projects"
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    def save(self) -> bool:
        if self.path is None:
            return self.save_as()
        try:
            batch = jobs_to_data(self.batch.jobs) if self.batch is not None else []
            save_project(self.path, self.ctx.config, self.ctx.library, batch=batch, created=self.created)
        except OSError as exc:
            self.ctx.toast(tr("Could not save the project: {error}", error=str(exc)), "error")
            return False
        self.dirty = False
        self._remember(self.path)
        self._update_label()
        self.ctx.sound("confirm")
        self.ctx.toast(tr("Project saved: {name}", name=self.path.name), "ok")
        return True

    def save_as(self) -> bool:
        start = os.path.join(self._default_dir(), (self.path.stem if self.path else "My chromatic") + PROJECT_EXT)
        path, _ = QFileDialog.getSaveFileName(self.host, tr("Save project"), start,
                                              tr("Voxa GEN project (*{ext})", ext=PROJECT_EXT))
        if not path:
            return False
        self.path = Path(path).with_suffix(PROJECT_EXT)
        return self.save()

    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self.host, tr("Open project"), self._default_dir(),
                                              tr("Voxa GEN project (*{ext})", ext=PROJECT_EXT))
        if path:
            self.open(path)

    def open(self, path: str) -> None:
        if self.ctx.busy:
            return self.ctx.toast("Wait for the current export to finish.", "warn")
        if not self.confirm_discard():
            return
        try:
            lp = load_project(path)
        except ProjectError as exc:
            return self.ctx.toast(str(exc), "error")
        if lp.missing or lp.changed:
            dlg = MissingSamplesProjectDialog(self.host, lp)
            if not dlg.exec():
                return
        self._apply(lp.config, lp)
        self.path = Path(path)
        self.dirty = False
        self._remember(self.path)
        self._update_label()
        msg = tr("{n} samples", n=len(lp.samples))
        if lp.missing:
            msg += " · " + tr("{n} missing", n=len(lp.missing))
        if lp.newer_format:
            msg += " · " + tr("made with a newer Voxa GEN: unknown settings were ignored")
        self.ctx.notify("Project opened", f"{lp.name}\n{msg}", "warn" if lp.missing else "ok")

    def new(self) -> None:
        if self.ctx.busy:
            return self.ctx.toast("Wait for the current export to finish.", "warn")
        if not self.confirm_discard():
            return
        if not self.path and len(self.ctx.library) and not confirm(
                self.host, tr("New project"), tr("Start over with no samples and default settings?"), tr("Start over")):
            return
        cfg = GeneratorConfig()
        cfg.order.seed = self.ctx.config.order.seed
        self._apply(cfg, None)
        self.path = None
        self.dirty = False
        self._update_label()

    def _apply(self, cfg: GeneratorConfig, lp: LoadedProject | None) -> None:
        self._quiet = True
        try:
            self.ctx.stop_players()
            target = self.ctx.config
            for f in fields(GeneratorConfig):
                setattr(target, f.name, copy.deepcopy(getattr(cfg, f.name)))
            if lp is not None:
                lp.apply_to(self.ctx.library)
                target.sample_paths = [self.ctx.library.get(s.id).path for s in lp.samples]
                if self.batch is not None:
                    self.batch.set_jobs(jobs_from_data(lp.batch))
            else:
                self.ctx.library.clear()
            self.ctx.libraryChanged.emit()
            self.ctx.touch("all")
        finally:
            self._quiet = False
