from __future__ import annotations

import copy
import json

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QLineEdit, QListWidget,
    QListWidgetItem, QMenu, QToolButton, QVBoxLayout, QWidget,
)

from ...core.effects.chain import MAX_SLOTS, new_slot
from ...core.effects.presets import CATEGORIES, chain_from_data, preset_data
from ...core.effects.registry import EFFECT_ORDER, EFFECTS, get_effect
from ...core.presets.manager import Preset, PresetError
from ...i18n import tr
from ...models.serialization import to_dict
from .. import icons
from .common import (
    Card, FormGrid, HelpButton, ParamControl, button, confirm, divider, hbox, hint, label, more_button, set_tone,
)
from .sample_preview import SamplePreview

ALL = "__all__"


class SavePresetDialog(QDialog):
    def __init__(self, parent, name: str, category: str):
        super().__init__(parent)
        self.setWindowTitle("Save effect preset")
        v = QVBoxLayout(self)
        g = FormGrid()
        self.name = QLineEdit(name)
        g.row("Name", self.name)
        self.category = QComboBox()
        for c in CATEGORIES:
            self.category.addItem(c, c)
        self.category.setCurrentIndex(max(0, self.category.findData(category)))
        g.row("Category", self.category, "Where the preset is listed. You can filter presets by category.")
        v.addLayout(g)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self) -> tuple[str, str]:
        return self.name.text().strip(), self.category.currentData()


class EffectsEditor(QObject):
    changed = Signal(str, str)

    def __init__(self, ctx, parent_widget: QWidget):
        super().__init__(parent_widget)
        self.ctx = ctx
        self.host = parent_widget
        self._loading = False
        self.chain_card = self._chain_card()
        self.settings_card = self._settings_card()
        self.presets_card = self._presets_card()
        self.listen_card = self._listen_card()
        ctx.presetsChanged.connect(lambda k: k == "effects" and self.refresh_presets())
        ctx.languageChanged.connect(lambda _: (self.reload(), self.refresh_presets()))
        self.refresh_presets()
        self.reload()

    @property
    def fx(self):
        return self.ctx.config.effects

    def _chain_card(self) -> Card:
        c = Card("Effect chain", "Effects run from top to bottom on every note. Untick an effect to bypass it. "
                                 "Effects are optional and never change your sample files.")
        self.enabled = QCheckBox("Use effects in previews and exports")
        self.enabled.toggled.connect(self._set_enabled)
        en_help = HelpButton(
            "Use effects", "When this is on, the chain below runs after the export mode (Natural, Robot, Legacy or Lab) in the chromatic preview, the export and the batch queue. When it's off, exports sound exactly as they would without effects. The A/B player below plays the chain either way.", "Default: off. Effects are never applied unless you turn this on.")
        c.add(hbox(self.enabled, en_help, None))
        self.state = label("", "StatusText")
        c.add(self.state)
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setMinimumHeight(220)
        self.list.currentRowChanged.connect(lambda _: self._show_selected())
        self.list.itemChanged.connect(self._item_changed)
        self.list.model().rowsMoved.connect(self._rows_moved)
        c.add(self.list)
        self.b_add = QToolButton()
        self.b_add.setObjectName("MoreButton")
        self.b_add.setText("Add effect")
        self.b_add.setIcon(icons.icon("add", size=16))
        self.b_add.setProperty("icon_name", "add")
        self.b_add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.b_add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.b_add)
        for eid in EFFECT_ORDER:
            e = EFFECTS[eid]
            a = menu.addAction(e.name)
            a.setToolTip(e.summary)
            a.triggered.connect(lambda _=False, k=eid: self.add_effect(k))
        menu.setToolTipsVisible(True)
        self.b_add.setMenu(menu)
        self.b_up = button("Up", "up")
        self.b_up.setToolTip("Move the selected effect earlier in the chain (Ctrl+Up)")
        self.b_down = button("Down", "down")
        self.b_down.setToolTip("Move the selected effect later in the chain (Ctrl+Down)")
        self.b_dup = button("Duplicate", "duplicate")
        self.b_remove = button("Remove", "trash")
        self.b_remove.setToolTip("Remove the selected effect (Delete)")
        self.b_up.clicked.connect(lambda: self.move(-1))
        self.b_down.clicked.connect(lambda: self.move(1))
        self.b_dup.clicked.connect(self.duplicate)
        self.b_remove.clicked.connect(self.remove)
        c.add(hbox(self.b_add, None, self.b_dup, self.b_remove))
        c.add(hbox(self.b_up, self.b_down, None))
        for key, fn in (("Ctrl+Up", lambda: self.move(-1)), ("Ctrl+Down", lambda: self.move(1)),
                        ("Delete", self.remove)):
            sc = QShortcut(QKeySequence(key), self.list)
            sc.setContext(Qt.ShortcutContext.WidgetShortcut)
            sc.activated.connect(fn)
        c.add(hint("Order matters: distortion before an EQ is tamed by it; after it, the EQ shapes what the "
                   "distortion receives."))
        return c

    def reload(self) -> None:
        self._loading = True
        row = self.list.currentRow()
        self.enabled.setChecked(self.fx.enabled)
        self.list.clear()
        for i, s in enumerate(self.fx.chain):
            e = get_effect(s.effect)
            name = tr(e.name) if e else s.effect
            it = QListWidgetItem(f"{i + 1}.  {name}")
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
            it.setCheckState(Qt.CheckState.Checked if s.enabled else Qt.CheckState.Unchecked)
            it.setToolTip(tr(e.summary) if e else tr("Unknown effect"))
            it.setData(Qt.ItemDataRole.UserRole, i)
            self.list.addItem(it)
        self.list.setProperty("i18n_skip", True)
        if self.fx.chain:
            self.list.setCurrentRow(min(max(row, 0), len(self.fx.chain) - 1))
        self._loading = False
        self._sync_state()
        self._show_selected()

    def _sync_state(self) -> None:
        n = len(self.fx.chain)
        active = sum(1 for s in self.fx.chain if s.enabled)
        if not self.fx.enabled:
            self.state.setText(tr("Off: exports are not changed by effects."))
            set_tone(self.state, "")
        elif not active:
            self.state.setText(tr("On, but no effect is active."))
            set_tone(self.state, "warn")
        else:
            self.state.setText(tr("On: {n} of {total} effects run in previews and exports.", n=active, total=n))
            set_tone(self.state, "ok")
        sel = self.list.currentRow()
        has = 0 <= sel < n
        self.b_up.setEnabled(has and sel > 0)
        self.b_down.setEnabled(has and sel < n - 1)
        self.b_dup.setEnabled(has and n < MAX_SLOTS)
        self.b_remove.setEnabled(has)
        self.b_add.setEnabled(n < MAX_SLOTS)

    def _emit(self, label_: str, merge: str = "") -> None:
        self.ctx.touch("effects")
        self._sync_state()
        self.changed.emit(label_, merge)

    def _set_enabled(self, on: bool) -> None:
        if self._loading:
            return
        self.before()
        self.fx.enabled = on
        self._emit("Use effects")

    def before(self) -> None:
        self.aboutToChange.emit()

    aboutToChange = Signal()

    def add_effect(self, eid: str) -> None:
        if len(self.fx.chain) >= MAX_SLOTS:
            return self.ctx.toast(tr("The chain is full ({n} effects).", n=MAX_SLOTS), "warn")
        self.before()
        row = self.list.currentRow()
        pos = row + 1 if 0 <= row < len(self.fx.chain) else len(self.fx.chain)
        self.fx.chain.insert(pos, new_slot(eid))
        if not self.fx.enabled and len(self.fx.chain) == 1:
            self.ctx.toast("Effect added. Turn on “Use effects in previews and exports” to export with it.", "info")
        self.ctx.sound("seq_add")
        self.reload()
        self.list.setCurrentRow(pos)
        self._emit("Add effect")

    def remove(self) -> None:
        row = self.list.currentRow()
        if not 0 <= row < len(self.fx.chain):
            return
        self.before()
        del self.fx.chain[row]
        self.ctx.sound("seq_remove")
        self.reload()
        self._emit("Remove effect")

    def duplicate(self) -> None:
        row = self.list.currentRow()
        if not 0 <= row < len(self.fx.chain) or len(self.fx.chain) >= MAX_SLOTS:
            return
        self.before()
        self.fx.chain.insert(row + 1, copy.deepcopy(self.fx.chain[row]))
        self.reload()
        self.list.setCurrentRow(row + 1)
        self._emit("Duplicate effect")

    def move(self, delta: int) -> None:
        row = self.list.currentRow()
        new = row + delta
        if not (0 <= row < len(self.fx.chain) and 0 <= new < len(self.fx.chain)):
            return
        self.before()
        ch = self.fx.chain
        ch[row], ch[new] = ch[new], ch[row]
        self.reload()
        self.list.setCurrentRow(new)
        self.ctx.sound("drag_snap")
        self._emit("Reorder effects")

    def _rows_moved(self, *_):
        if self._loading:
            return
        order = [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]
        if order == list(range(len(order))):
            return
        self.before()
        self.fx.chain = [self.fx.chain[i] for i in order]
        cur = self.list.currentRow()
        self.reload()
        self.list.setCurrentRow(cur)
        self.ctx.sound("drag_snap")
        self._emit("Reorder effects")

    def _item_changed(self, it: QListWidgetItem) -> None:
        if self._loading:
            return
        i = it.data(Qt.ItemDataRole.UserRole)
        if i is None or not 0 <= i < len(self.fx.chain):
            return
        on = it.checkState() == Qt.CheckState.Checked
        if self.fx.chain[i].enabled != on:
            self.before()
            self.fx.chain[i].enabled = on
            self._emit("Bypass effect")

    def _settings_card(self) -> Card:
        c = Card("Effect settings", "The controls of the effect selected in the chain. Every control has a “?”.")
        self.form_host = QWidget()
        self.form = QVBoxLayout(self.form_host)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setSpacing(6)
        c.add(self.form_host)
        return c

    def _clear_form(self) -> None:
        while self.form.count():
            it = self.form.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
            elif it.layout() is not None:
                _delete_layout(it.layout())

    def _show_selected(self) -> None:
        self._clear_form()
        self._sync_state()
        row = self.list.currentRow()
        if not 0 <= row < len(self.fx.chain):
            self.form.addWidget(hint("Add an effect with “Add effect”, then select it to change its settings."))
            return
        slot = self.fx.chain[row]
        e = get_effect(slot.effect)
        if e is None:
            self.form.addWidget(hint(tr("This effect ('{id}') is not available in this version.", id=slot.effect)))
            return
        title = label(e.name, "SubTitle")
        self.form.addLayout(hbox(title, HelpButton(e.name, e.help), None))
        self.form.addWidget(hint(e.summary))
        if e.cost == "heavy":
            self.form.addWidget(hint("Uses voice analysis: rendering takes longer (results are cached)."))
        values = e.resolve(slot.params)
        for p in e.params:
            if p.is_choice:
                combo = QComboBox()
                for k, text in p.choices:
                    combo.addItem(text, k)
                combo.setCurrentIndex(max(0, combo.findData(values[p.key])))
                combo.currentIndexChanged.connect(
                    lambda _=0, cb=combo, key=p.key, r=row: self._set_param(r, key, cb.currentData(), ""))
                self.form.addLayout(hbox(label(p.label), HelpButton(p.label, p.help), None, combo))
            else:
                pc = ParamControl(p.label, p.help, p.lo, p.hi, float(values[p.key]), float(p.default), p.decimals,
                                  p.unit, p.scale)
                pc.valueChanged.connect(lambda v, key=p.key, r=row: self._set_param(r, key, v, f"{r}:{key}"))
                self.form.addWidget(pc)
        if e.has_mix:
            self.form.addWidget(divider())
            mix = ParamControl("Wet / Dry", "Blend between the untouched input (0 %) and the effect (100 %). "
                                            "Lower values keep more of the original voice.",
                               0.0, 1.0, float(slot.mix), e.default_mix, 0, " %", 100)
            mix.valueChanged.connect(lambda v, r=row: self._set_mix(r, v))
            self.form.addWidget(mix)
        b_reset = button("Reset this effect", "reset")
        b_reset.clicked.connect(lambda _=False, r=row: self._reset_effect(r))
        self.form.addLayout(hbox(None, b_reset))
        self.form.addStretch(1)

    def _set_param(self, row: int, key: str, value, merge: str) -> None:
        if not 0 <= row < len(self.fx.chain):
            return
        self.before()
        self.fx.chain[row].params[key] = value
        self._emit("Change effect setting", merge)

    def _set_mix(self, row: int, value: float) -> None:
        if not 0 <= row < len(self.fx.chain):
            return
        self.before()
        self.fx.chain[row].mix = float(value)
        self._emit("Change wet/dry", f"{row}:mix")

    def _reset_effect(self, row: int) -> None:
        if not 0 <= row < len(self.fx.chain):
            return
        self.before()
        enabled = self.fx.chain[row].enabled
        self.fx.chain[row] = new_slot(self.fx.chain[row].effect)
        self.fx.chain[row].enabled = enabled
        self._show_selected()
        self._emit("Reset effect")

    def _presets_card(self) -> Card:
        c = Card("Effect presets", "Ready-made chains by category. Load one, change it, and save it as your own. "
                                   "Built-in presets can be changed and restored.")
        self.category = QComboBox()
        self.category.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.category.setMinimumContentsLength(12)
        self.category.addItem("All categories", ALL)
        for cat in CATEGORIES:
            self.category.addItem(cat, cat)
        self.category.currentIndexChanged.connect(lambda _: self.refresh_presets())
        self.preset = QComboBox()
        self.preset.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.preset.setMinimumContentsLength(16)
        self.preset.setProperty("i18n_items_skip", True)
        self.preset.currentIndexChanged.connect(lambda _: self._preset_selected())
        b_load = button("Load", "import")
        b_load.setToolTip("Replace the chain with this preset (you can undo it)")
        b_load.clicked.connect(self.load_preset)
        b_save_as = button("Save as new", "add")
        b_save_as.clicked.connect(self.save_preset_as)
        self.preset_more = more_button([
            ("Save into this preset", "save", self.save_preset),
            ("Duplicate", "duplicate", self.duplicate_preset),
            ("Rename…", "edit", self.rename_preset),
            ("Delete", "trash", self.delete_preset),
            ("Restore the original version", "reset", self.restore_preset),
            ("Import from a file…", "import", self.import_preset),
            ("Export to a file…", "export", self.export_preset),
        ])
        g = FormGrid()
        g.row("Category", self.category)
        g.row("Preset", self.preset)
        c.add(g)
        self.preset_desc = hint("")
        c.add(self.preset_desc)
        c.add(hbox(b_load, b_save_as, self.preset_more, None))
        return c

    def refresh_presets(self) -> None:
        cat = self.category.currentData() or ALL
        cur = self.preset.currentData() or self.fx.preset_name
        self.preset.blockSignals(True)
        self.preset.clear()
        for p in self.ctx.presets.list("effects"):
            if cat != ALL and p.category != cat:
                continue
            tag = tr(" · built-in, changed") if p.modified else (tr(" · built-in") if p.builtin else "")
            self.preset.addItem(f"{tr(p.name)}  ({tr(p.category)}){tag}", p.name)
        i = self.preset.findData(cur)
        self.preset.setCurrentIndex(max(0, i))
        self.preset.blockSignals(False)
        self._preset_selected()

    def _current_preset(self):
        return self.ctx.presets.get("effects", self.preset.currentData() or "")

    def _preset_selected(self) -> None:
        p = self._current_preset()
        if p is None:
            self.preset_desc.setText("")
            return
        names = " → ".join(tr(EFFECTS[s["effect"]].name) for s in p.data.get("chain", []) if s.get("effect") in EFFECTS)
        self.preset_desc.setText((tr(p.description) + "\n" if p.description else "") + names)
        self.preset_desc.setProperty("i18n_text_skip", True)
        acts = self.preset_more._actions
        acts["Restore the original version"].setEnabled(p.modified)
        acts["Delete"].setEnabled(not p.builtin)
        acts["Rename…"].setEnabled(not p.builtin)

    def load_preset(self) -> None:
        p = self._current_preset()
        if p is None:
            return
        self.before()
        self.fx.chain = chain_from_data(p.data)
        self.fx.seed = int(p.data.get("seed", self.fx.seed))
        self.fx.preset_name = p.name
        self.reload()
        self._emit("Load effect preset")
        hint_ = "" if self.fx.enabled else tr(" Turn on “Use effects” to export with it.")
        self.ctx.toast(tr("Loaded “{name}”.", name=tr(p.name)) + hint_, "ok")

    def _ask_save(self, name: str, category: str):
        dlg = SavePresetDialog(self.host, name, category)
        if not dlg.exec():
            return None
        return dlg.values()

    def save_preset_as(self) -> None:
        if not self.fx.chain:
            return self.ctx.toast("Add at least one effect before saving a preset.", "warn")
        p = self._current_preset()
        res = self._ask_save(self.ctx.presets.free_name("effects", tr("My effects")),
                             p.category if p else "Experimental")
        if not res or not res[0]:
            return
        name, cat = res
        if self.ctx.presets.exists("effects", name):
            return self.ctx.toast(tr("A preset named “{name}” already exists.", name=name), "warn")
        self.ctx.presets.save(Preset("effects", name, preset_data(self.fx, cat)))
        self.fx.preset_name = name
        self.ctx.presetsChanged.emit("effects")
        self.preset.setCurrentIndex(max(0, self.preset.findData(name)))
        self.ctx.toast(tr("Saved “{name}”.", name=name), "ok")

    def save_preset(self) -> None:
        p = self._current_preset()
        if p is None:
            return self.save_preset_as()
        if not self.fx.chain:
            return self.ctx.toast("Add at least one effect before saving a preset.", "warn")
        if p.builtin and not confirm(self.host, tr("Change built-in preset"),
                                     tr("Overwrite the built-in preset “{name}”? You can restore it later.",
                                        name=tr(p.name))):
            return
        self.ctx.presets.save(Preset("effects", p.name, preset_data(self.fx, p.category), p.description))
        self.fx.preset_name = p.name
        self.ctx.presetsChanged.emit("effects")
        self.ctx.toast(tr("Saved “{name}”.", name=tr(p.name)), "ok")

    def duplicate_preset(self) -> None:
        p = self._current_preset()
        if p:
            q = self.ctx.presets.duplicate("effects", p.name)
            self.ctx.presetsChanged.emit("effects")
            self.preset.setCurrentIndex(max(0, self.preset.findData(q.name)))

    def rename_preset(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        p = self._current_preset()
        if p is None or p.builtin:
            return
        name, ok = QInputDialog.getText(self.host, tr("Rename preset"), tr("New name:"), text=p.name)
        if ok and name.strip() and name.strip() != p.name:
            try:
                self.ctx.presets.rename("effects", p.name, name.strip())
            except PresetError as exc:
                return self.ctx.toast(str(exc), "warn")
            self.ctx.presetsChanged.emit("effects")
            self.preset.setCurrentIndex(max(0, self.preset.findData(name.strip())))

    def delete_preset(self) -> None:
        p = self._current_preset()
        if p is None or p.builtin:
            return
        if confirm(self.host, tr("Delete preset"), tr("Delete the effect preset “{name}”?", name=p.name),
                   tr("Delete"), danger=True):
            self.ctx.presets.delete("effects", p.name)
            self.ctx.presetsChanged.emit("effects")
            self.ctx.sound("seq_remove")

    def restore_preset(self) -> None:
        p = self._current_preset()
        if p and p.modified:
            self.ctx.presets.restore("effects", p.name)
            self.ctx.presetsChanged.emit("effects")
            self.ctx.toast(tr("Restored the original “{name}”.", name=tr(p.name)), "ok")

    def import_preset(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self.host, tr("Import effect preset"), "",
                                              tr("Voxa GEN preset (*.json)"))
        if not path:
            return
        try:
            p = self.ctx.presets.import_from(path)
        except PresetError as exc:
            return self.ctx.toast(str(exc), "error")
        self.ctx.presetsChanged.emit(p.kind)
        if p.kind != "effects":
            return self.ctx.toast(tr("Imported “{name}”, but it is not an effect preset.", name=p.name), "warn")
        self.category.setCurrentIndex(0)
        self.preset.setCurrentIndex(max(0, self.preset.findData(p.name)))
        self.ctx.toast(tr("Imported “{name}”.", name=p.name), "ok")

    def export_preset(self) -> None:
        name = self.fx.preset_name or tr("My effects")
        path, _ = QFileDialog.getSaveFileName(self.host, tr("Export effect preset"), f"{name}.vxpreset.json",
                                              tr("Voxa GEN preset (*.json)"))
        if path:
            p = self._current_preset()
            cat = p.category if p else "Experimental"
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(Preset("effects", name, preset_data(self.fx, cat)).to_file(), fh, indent=2,
                          ensure_ascii=False)
            self.ctx.toast("Preset exported.", "ok")

    def _listen_card(self) -> Card:
        c = Card("Listen: before / after", "A plays the sample through the current export mode without effects, "
                                           "B with the chain. Switch with A / B (or the B key): the position stays "
                                           "the same and the loudness is matched.")
        self.preview = SamplePreview(self.ctx, effects_ab=True)
        c.add(self.preview)
        return c


def _delete_layout(lay) -> None:
    while lay.count():
        it = lay.takeAt(0)
        if it.widget() is not None:
            it.widget().deleteLater()
        elif it.layout() is not None:
            _delete_layout(it.layout())


def snapshot(ctx) -> dict:
    return {"lab": to_dict(ctx.config.lab), "effects": to_dict(ctx.config.effects),
            "lab_profile_name": ctx.config.lab_profile_name}
