from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QGridLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout,
)

from ...i18n import tr
from .common import hint, label

SKIP = "__skip__"


class MissingSamplesDialog(QDialog):

    def __init__(self, parent, missing: dict[str, list[int]], available: list[str]):
        super().__init__(parent)
        self.setWindowTitle("Missing samples")
        self.setMinimumWidth(460)
        v = QVBoxLayout(self)
        v.addWidget(label("Some sequence elements have no matching file.", "CardTitle"))
        v.addWidget(hint("Choose what to do with each one. Mapping is explicit and saved with the "
                         "configuration; skipping removes that element from the order."))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self.combos: dict[str, QComboBox] = {}
        for r, (token, positions) in enumerate(missing.items()):
            pos = ", ".join(str(p + 1) for p in positions[:8]) + ("…" if len(positions) > 8 else "")
            grid.addWidget(QLabel(f"<b>{token}.wav</b>"), r, 0)
            grid.addWidget(hint(tr("position {pos}", pos=pos)), r, 1)
            cb = QComboBox()
            cb.addItem("Choose…", None)
            cb.addItem("Skip this element", SKIP)
            for sid in available:
                cb.addItem(tr("Use {file}", file=f"{sid}.wav"), sid)
            cb.currentIndexChanged.connect(self._validate)
            grid.addWidget(cb, r, 2)
            self.combos[token] = cb
        v.addLayout(grid)
        self.buttons = QDialogButtonBox()
        self.ok = self.buttons.addButton("Apply and continue", QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok.setObjectName("Primary")
        self.buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        v.addWidget(self.buttons)
        self._validate()

    def _validate(self) -> None:
        self.ok.setEnabled(all(cb.currentData() is not None for cb in self.combos.values()))

    def remap(self) -> dict[str, str]:
        return {t: ("" if cb.currentData() == SKIP else cb.currentData()) for t, cb in self.combos.items()}


def ask_conflict(parent, dest: Path, conflicts: list[Path], alternative: Path) -> str:
    box = QMessageBox(parent)
    box.setWindowTitle("Files already exist")
    box.setIcon(QMessageBox.Icon.Warning)
    names = "\n".join(f"• {p.relative_to(dest)}" for p in conflicts[:6])
    more = ("\n" + tr("… and {n} more", n=len(conflicts) - 6)) if len(conflicts) > 6 else ""
    box.setText(tr("{n} file(s) in “{folder}” would be replaced:", n=len(conflicts), folder=dest.name) +
                f"\n\n{names}{more}")
    b_new = box.addButton(tr("Export to “{folder}”", folder=alternative.name), QMessageBox.ButtonRole.AcceptRole)
    b_over = box.addButton("Overwrite these files", QMessageBox.ButtonRole.DestructiveRole)
    box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(b_new)
    box.exec()
    clicked = box.clickedButton()
    if clicked is b_new:
        return "new"
    if clicked is b_over:
        return "overwrite"
    return "cancel"


def error_details(parent, title: str, exc: Exception) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setText(str(exc) or exc.__class__.__name__)
    tb = getattr(exc, "traceback_text", "")
    if tb:
        box.setDetailedText(tb)
    box.exec()
