from __future__ import annotations

import copy
import dataclasses
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog, QHeaderView, QInputDialog, QListWidget, QListWidgetItem, QPlainTextEdit, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...core.presets.manager import KINDS, Preset, PresetError
from ...i18n import tr
from ...models.config import GeneratorConfig
from ...models.serialization import from_dict, to_dict
from ..widgets.common import Badge, Card, button, confirm, hbox, hint, label, more_button, tool_button
from .base import Page


def assign_inplace(target, source) -> None:
    for f in dataclasses.fields(target):
        new = getattr(source, f.name)
        old = getattr(target, f.name)
        if dataclasses.is_dataclass(old) and dataclasses.is_dataclass(new):
            assign_inplace(old, new)
        else:
            setattr(target, f.name, copy.deepcopy(new))


def current_data(ctx, kind: str) -> dict:
    cfg = ctx.config
    if kind == "sequence":
        return {"tokens": list(cfg.order.sequence)}
    if kind == "effects":
        from ...core.effects.presets import preset_data
        return preset_data(cfg.effects, "Experimental")
    if kind in ("natural", "robot", "legacy", "lab", "export"):
        d = to_dict(getattr(cfg, kind))
        if kind == "export":
            d["output_dir"] = ""
        return d
    d = to_dict(cfg)
    d["sample_folder"], d["sample_paths"], d["disabled_samples"] = "", [], []
    d["export"]["output_dir"] = ""
    return d


class PresetsPage(Page):
    page_id = "presets"
    title = "Presets"
    subtitle = "Save, share and restore sequences, mode settings, LAB profiles, effect chains and export settings"
    icon = "presets"

    def __init__(self, ctx):
        super().__init__(ctx)
        b_import = button("Import…", "import")
        b_import.clicked.connect(self.import_preset)
        more_top = more_button([
            ("Restore all built-in presets", "reset", self.restore_all),
            ("Open the presets folder", "folder",
             lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ctx.presets.root)))),
        ])
        self.header.addLayout(hbox(b_import, more_top))

        self.kinds = QListWidget()
        self.kinds.setMinimumWidth(240)
        for k, name in KINDS.items():
            it = QListWidgetItem(tr(name))
            it.setData(Qt.ItemDataRole.UserRole, k)
            self.kinds.addItem(it)
        self.list = QListWidget()

        detail = Card("Details", "What this preset contains. “Apply” loads it into the Generator; nothing is "
                                 "exported until you press Export.")
        self.name = label("", "SubTitle")
        self.badge = Badge("")
        detail.add(hbox(self.name, self.badge, None))
        self.desc = QPlainTextEdit()
        self.desc.setPlaceholderText("Description")
        self.desc.setMaximumHeight(64)
        detail.add(self.desc)
        self.content = QTableWidget(0, 2)
        self.content.setHorizontalHeaderLabels(["Setting", "Value"])
        self.content.verticalHeader().hide()
        self.content.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.content.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.content.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.seq_text = QPlainTextEdit()
        self.seq_text.setReadOnly(True)
        detail.add(self.seq_text)
        detail.add(self.content, )
        self.b_apply = button("Apply", "check", "Primary")
        self.b_apply.setToolTip("Load this preset into the current configuration")
        self.b_new = button("Save current as new", "add")
        self.b_new.setToolTip("Create a preset of this type from your current settings")
        self.more = more_button([
            ("Update with current settings", "save", self.update_from_current),
            ("Save description", "edit", self.save_description),
            ("Duplicate", "duplicate", self.duplicate),
            ("Rename…", "edit", self.rename),
            ("Delete", "trash", self.delete),
            ("Restore the original version", "reset", self.restore),
            ("Export to a file…", "export", self.export),
        ])
        a = self.more._actions
        self.b_update, self.b_save_desc, self.b_dup = a["Update with current settings"], a["Save description"], a["Duplicate"]
        self.b_rename, self.b_delete = a["Rename…"], a["Delete"]
        self.b_restore, self.b_export = a["Restore the original version"], a["Export to a file…"]
        detail.add(hbox(self.b_apply, self.b_new, self.more, None))
        self.note = hint("")
        detail.add(self.note)

        kinds_card = Card("Type", "Presets are grouped by what they change.")
        kinds_card.add(self.kinds)
        list_card = Card("Presets", "Built-in presets come with Voxa GEN; yours are listed after them.")
        list_card.add(self.list)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setHandleWidth(16)
        split.setChildrenCollapsible(False)
        split.addWidget(kinds_card)
        split.addWidget(list_card)
        split.addWidget(detail)
        split.setStretchFactor(2, 1)
        split.setSizes([230, 280, 600])
        self.root.addWidget(split, 1)

        self.kinds.currentRowChanged.connect(lambda _: self.refresh_list())
        self.list.currentRowChanged.connect(lambda _: self.show_preset())
        self.b_apply.clicked.connect(self.apply)
        self.b_new.clicked.connect(self.new_from_current)
        ctx.presetsChanged.connect(lambda _: self.refresh_list())
        ctx.languageChanged.connect(self._language)
        self.kinds.setCurrentRow(0)

    def kind(self) -> str:
        it = self.kinds.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else "sequence"

    def preset(self) -> Preset | None:
        it = self.list.currentItem()
        return self.ctx.presets.get(self.kind(), it.data(Qt.ItemDataRole.UserRole)) if it else None

    def _language(self, _code: str) -> None:
        for i in range(self.kinds.count()):
            it = self.kinds.item(i)
            it.setText(tr(KINDS[it.data(Qt.ItemDataRole.UserRole)]))
        self.refresh_list()

    def refresh_list(self, select: str | None = None) -> None:
        cur = select or (self.list.currentItem().data(Qt.ItemDataRole.UserRole) if self.list.currentItem() else None)
        self.list.blockSignals(True)
        self.list.clear()
        for p in self.ctx.presets.list(self.kind()):
            tag = tr("  · built-in, changed") if p.modified else (tr("  · built-in") if p.builtin else "")
            it = QListWidgetItem(tr(p.name) + tag)
            it.setData(Qt.ItemDataRole.UserRole, p.name)
            self.list.addItem(it)
        self.list.blockSignals(False)
        row = next((i for i in range(self.list.count()) if self.list.item(i).data(Qt.ItemDataRole.UserRole) == cur), 0)
        self.list.setCurrentRow(row if self.list.count() else -1)
        self.show_preset()

    def show_preset(self) -> None:
        p = self.preset()
        has = p is not None
        for b in (self.b_apply, self.b_update, self.b_dup, self.b_export, self.b_save_desc):
            b.setEnabled(has)
        self.b_rename.setEnabled(has and not p.builtin)
        self.b_delete.setEnabled(has and not p.builtin)
        self.b_restore.setEnabled(has and p.modified)
        if not has:
            self.name.setText(tr("No preset"))
            self.badge.setText("")
            self.content.setRowCount(0)
            self.seq_text.clear()
            return
        self.name.setText(tr(p.name))
        self.badge.setText(tr("Built-in, changed") if p.modified else (tr("Built-in") if p.builtin else tr("Yours")))
        for w in (self.name, self.badge, self.note):
            w.setProperty("i18n_text_skip", True)
        self.badge.set_tone("warn" if p.modified else ("accent" if p.builtin else "processed"))
        self.desc.setPlainText(tr(p.description) if p.builtin and not p.modified else p.description)
        is_seq = p.kind == "sequence"
        self.seq_text.setVisible(is_seq)
        self.content.setVisible(not is_seq)
        if is_seq:
            toks = p.tokens()
            self.seq_text.setPlainText(" ".join(toks))
            self.note.setText(tr("{n} elements · {u} unique: {list}", n=len(toks), u=len(set(toks)),
                                 list=", ".join(sorted(set(toks)))))
        else:
            rows = list(_flatten(p.data))
            self.content.setRowCount(len(rows))
            for r, (k, v) in enumerate(rows):
                self.content.setItem(r, 0, QTableWidgetItem(k))
                self.content.setItem(r, 1, QTableWidgetItem(str(v)))
            self.note.setText(tr("Apply loads these settings into the Generator. Built-in presets can be edited; "
                                 "Restore brings back the original."))

    def apply(self) -> None:
        p = self.preset()
        if p is None:
            return
        cfg = self.ctx.config
        k = p.kind
        if k == "sequence":
            cfg.order.sequence = p.tokens()
            cfg.order.sequence_name = p.name
            cfg.order.mode = "vocal"
        elif k == "effects":
            from ...core.effects.presets import chain_from_data
            cfg.effects.chain = chain_from_data(p.data)
            cfg.effects.seed = int(p.data.get("seed", cfg.effects.seed))
            cfg.effects.preset_name = p.name
        elif k == "processing":
            new = from_dict(GeneratorConfig, p.data)
            keep = (cfg.sample_folder, list(cfg.sample_paths), list(cfg.disabled_samples), cfg.export.output_dir)
            assign_inplace(cfg, new)
            cfg.sample_folder, cfg.sample_paths, cfg.disabled_samples, cfg.export.output_dir = keep
        else:
            target = getattr(cfg, k)
            keep_dir = cfg.export.output_dir
            assign_inplace(target, p.typed())
            if k == "export":
                cfg.export.output_dir = p.data.get("output_dir") or keep_dir
            if k == "lab":
                cfg.lab_profile_name = p.name
            if k in ("natural", "robot", "legacy"):
                cfg.mode = k
        self.ctx.touch("all")
        self.ctx.sound("confirm")
        msg = tr("Applied “{name}”.", name=tr(p.name))
        if k == "effects" and not cfg.effects.enabled:
            msg += " " + tr("Turn on “Use effects” in the LAB or the Exporting tab to export with it.")
        self.ctx.toast(msg, "ok")

    def new_from_current(self) -> None:
        k = self.kind()
        name, ok = QInputDialog.getText(self, tr("New preset"), tr("Name for the new preset ({kind}):",
                                                                   kind=tr(KINDS[k])),
                                        text=self.ctx.presets.free_name(k, tr("My preset")))
        if not ok or not name.strip():
            return
        if self.ctx.presets.exists(k, name.strip()):
            return self.ctx.toast("A preset with that name already exists.", "warn")
        try:
            self.ctx.presets.save(Preset(k, name.strip(), current_data(self.ctx, k)))
        except PresetError as exc:
            return self.ctx.toast(str(exc), "error")
        self.ctx.presetsChanged.emit(k)
        self.refresh_list(name.strip())
        self.ctx.toast(tr("Created “{name}”.", name=name.strip()), "ok")

    def update_from_current(self) -> None:
        p = self.preset()
        if p is None:
            return
        if not confirm(self, tr("Update preset"), tr("Overwrite “{name}” with the current settings?", name=tr(p.name))):
            return
        try:
            self.ctx.presets.save(Preset(p.kind, p.name, current_data(self.ctx, p.kind), p.description))
        except PresetError as exc:
            return self.ctx.toast(str(exc), "error")
        self.ctx.presetsChanged.emit(p.kind)
        self.ctx.toast(tr("Updated “{name}”.", name=tr(p.name)), "ok")

    def save_description(self) -> None:
        p = self.preset()
        if p is None:
            return
        p.description = self.desc.toPlainText().strip()
        self.ctx.presets.save(Preset(p.kind, p.name, p.data, p.description))
        self.ctx.presetsChanged.emit(p.kind)

    def duplicate(self) -> None:
        p = self.preset()
        if p:
            q = self.ctx.presets.duplicate(p.kind, p.name)
            self.ctx.presetsChanged.emit(p.kind)
            self.refresh_list(q.name)

    def rename(self) -> None:
        p = self.preset()
        if p is None:
            return
        name, ok = QInputDialog.getText(self, "Rename preset", "New name:", text=p.name)
        if ok and name.strip() and name.strip() != p.name:
            try:
                self.ctx.presets.rename(p.kind, p.name, name.strip())
            except PresetError as exc:
                return self.ctx.toast(str(exc), "warn")
            self.ctx.presetsChanged.emit(p.kind)
            self.refresh_list(name.strip())

    def delete(self) -> None:
        p = self.preset()
        if p and confirm(self, tr("Delete preset"), tr("Delete “{name}”? This cannot be undone.", name=p.name),
                         tr("Delete"), danger=True):
            self.ctx.presets.delete(p.kind, p.name)
            self.ctx.presetsChanged.emit(p.kind)
            self.ctx.sound("seq_remove")

    def restore(self) -> None:
        p = self.preset()
        if p and p.modified:
            self.ctx.presets.restore(p.kind, p.name)
            self.ctx.presetsChanged.emit(p.kind)
            self.ctx.toast(tr("Restored the original “{name}”.", name=tr(p.name)), "ok")

    def restore_all(self) -> None:
        if confirm(self, "Restore built-in presets", "Undo all changes made to built-in presets? Your own presets are kept."):
            n = self.ctx.presets.restore_all()
            for k in KINDS:
                self.ctx.presetsChanged.emit(k)
            self.ctx.toast(tr("{n} built-in preset(s) restored.", n=n), "ok")

    def export(self) -> None:
        p = self.preset()
        if p is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("Export preset"), f"{p.name}.vxpreset.json",
                                              "Voxa GEN preset (*.json)")
        if path:
            try:
                self.ctx.presets.export_to(p.kind, p.name, path)
                self.ctx.toast("Preset exported.", "ok")
            except (OSError, PresetError) as exc:
                self.ctx.toast(tr("Export failed: {error}", error=str(exc)), "error")

    def import_preset(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Import presets", "", "Voxa GEN preset (*.json)")
        done = []
        for path in paths:
            try:
                p = self.ctx.presets.import_from(path)
                done.append(p)
                self.ctx.presetsChanged.emit(p.kind)
            except PresetError as exc:
                self.ctx.toast(f"{os.path.basename(path)}: {exc}", "error")
        if done:
            kinds = list(KINDS)
            self.kinds.setCurrentRow(kinds.index(done[-1].kind))
            self.refresh_list(done[-1].name)
            self.ctx.toast(tr("Imported {n} preset(s).", n=len(done)), "ok")


def _flatten(d, prefix=""):
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and v and all(isinstance(x, (dict, int, float, str, bool, list)) for x in v.values()) \
                and k not in ("tools_enabled", "remap"):
            yield from _flatten(v, key + ".")
        else:
            yield key, v


class PresetsDialog(QWidget):

    def __init__(self, ctx, parent=None):
        from PySide6.QtCore import Qt as _Qt
        super().__init__(parent, _Qt.WindowType.Window)
        self.setWindowTitle("Presets")
        self.resize(1100, 680)
        self.setObjectName("PresetsWindow")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.page = PresetsPage(ctx)
        lay.addWidget(self.page)

    def showEvent(self, e):
        super().showEvent(e)
        self.page.on_shown()
