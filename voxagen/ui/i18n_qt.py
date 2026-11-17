from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtWidgets import (
    QAbstractButton, QComboBox, QGroupBox, QLabel, QLineEdit, QMenu, QPlainTextEdit, QToolButton, QWidget,
)

from .. import i18n

_SRC = "_i18n_src"
_shown_lang = i18n.DEFAULT


def _sources(obj: QObject) -> dict:
    d = obj.property(_SRC)
    return dict(d) if isinstance(d, dict) else {}


def _translate_slot(obj, slot: str, getter, setter, store: dict, from_lang: str) -> None:
    current = getter()
    if not current or not isinstance(current, str):
        return
    src, shown = store.get(slot, (None, None))
    if src is None or current != shown:
        src = i18n.source_of(current, from_lang) or i18n.source_of(current, i18n.language()) or current
    new = i18n.translate(src)
    if new != current:
        setter(new)
    store[slot] = (src, new)


def translate_object(obj: QObject, from_lang: str | None = None) -> None:
    if obj.property("i18n_skip"):
        return
    from_lang = from_lang or _shown_lang
    if hasattr(obj, "retranslate_ui"):
        try:
            obj.retranslate_ui()
        except RuntimeError:
            return
    if i18n.language() == i18n.DEFAULT and from_lang == i18n.DEFAULT and obj.property(_SRC) is None:
        return
    store = _sources(obj)
    if isinstance(obj, (QLabel, QAbstractButton)) and not obj.property("i18n_text_skip"):
        _translate_slot(obj, "text", obj.text, obj.setText, store, from_lang)
    if isinstance(obj, QWidget):
        if not obj.property("i18n_tip_skip"):
            _translate_slot(obj, "tip", obj.toolTip, obj.setToolTip, store, from_lang)
        if obj.isWindow():
            _translate_slot(obj, "title", obj.windowTitle, obj.setWindowTitle, store, from_lang)
    if isinstance(obj, (QLineEdit, QPlainTextEdit)):
        _translate_slot(obj, "ph", obj.placeholderText, obj.setPlaceholderText, store, from_lang)
    if isinstance(obj, QGroupBox):
        _translate_slot(obj, "title", obj.title, obj.setTitle, store, from_lang)
    if isinstance(obj, QComboBox) and not obj.property("i18n_items_skip"):
        for i in range(obj.count()):
            _translate_slot(obj, f"item{i}", lambda i=i: obj.itemText(i), lambda v, i=i: obj.setItemText(i, v),
                            store, from_lang)
    if isinstance(obj, (QMenu, QToolButton)) or isinstance(obj, QWidget):
        for a in obj.actions():
            astore = _sources(a)
            _translate_slot(a, "text", a.text, a.setText, astore, from_lang)
            _translate_slot(a, "tip", a.toolTip, a.setToolTip, astore, from_lang)
            a.setProperty(_SRC, astore)
    if store:
        obj.setProperty(_SRC, store)


def retranslate_tree(root: QWidget, from_lang: str) -> None:
    for w in [root] + root.findChildren(QWidget):
        try:
            translate_object(w, from_lang)
        except RuntimeError:
            continue


def switch_language(code: str, roots: list[QWidget]) -> None:
    global _shown_lang
    old = _shown_lang
    i18n.set_language(code)
    from PySide6.QtWidgets import QApplication
    tops = list(roots) + [w for w in QApplication.topLevelWidgets() if w not in roots]
    for r in tops:
        retranslate_tree(r, old)
    _shown_lang = i18n.language()


def mark_shown() -> None:
    global _shown_lang
    _shown_lang = i18n.language()
