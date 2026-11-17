from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QSizePolicy, QSlider, QToolButton, QVBoxLayout, QWidget,
)

from ...i18n import tr
from .. import icons, theme

SPACING = 8
CARD_MARGIN = 14
CARD_PAD_X = 22
CARD_PAD_TOP = 14
CARD_PAD_BOTTOM = 22


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


def elastic(lb: QLabel) -> QLabel:
    lb.setWordWrap(True)
    lb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    return lb


def hint(text: str) -> QLabel:
    return label(text, "Hint", wrap=True)


def divider() -> QFrame:
    f = QFrame()
    f.setObjectName("Divider")
    return f


def tool_button(icon_name: str, tooltip: str, checkable: bool = False, size: int = 18) -> QToolButton:
    b = QToolButton()
    b.setIcon(icons.icon(icon_name, size=size))
    b.setToolTip(tooltip)
    b.setCheckable(checkable)
    b.setAutoRaise(True)
    b.setProperty("icon_name", icon_name)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def button(text: str, icon_name: str | None = None, kind: str | None = None) -> QPushButton:
    b = QPushButton(text)
    if icon_name:
        b.setIcon(icons.icon(icon_name, size=16))
        b.setProperty("icon_name", icon_name)
    if kind:
        b.setObjectName(kind)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def refresh_icons(root: QWidget) -> None:
    from PySide6.QtWidgets import QAbstractButton
    for w in root.findChildren(QAbstractButton):
        name = w.property("icon_name")
        if name:
            w.setIcon(icons.icon(name, size=w.iconSize().width() if w.iconSize().width() > 0 else 18))


class Badge(QLabel):
    def __init__(self, text: str = "", tone: str = ""):
        super().__init__(text)
        self.setObjectName("Badge")
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)


def set_tone(widget: QWidget, tone: str) -> None:
    widget.setProperty("tone", tone)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class HelpPopup(QFrame):

    current = None

    def __init__(self, title: str, text: str, why: str = "", tip: str = "", parent: QWidget | None = None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("HelpPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(340)
        self._drag = None
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 12, 16)
        v.setSpacing(6)
        head = QHBoxLayout()
        head.addWidget(label(title or tr("Help"), "HelpTitle", wrap=True), 1)
        close = QPushButton("×")
        close.setObjectName("HelpClose")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setAccessibleName(tr("Close"))
        close.clicked.connect(self.close)
        head.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(head)
        v.addWidget(label(tr("What it is"), "HelpSection"))
        v.addWidget(label(text, "HelpBody", wrap=True))
        if why:
            v.addSpacing(4)
            v.addWidget(label(tr("Why use it"), "HelpSection"))
            v.addWidget(label(why, "HelpWhy", wrap=True))
        if tip:
            v.addSpacing(4)
            v.addWidget(label(tip, "HelpTip", wrap=True))
        for lb in self.findChildren(QLabel):
            lb.setProperty("i18n_skip", True)
            lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        self._drag = None
        super().mouseReleaseEvent(e)

    def closeEvent(self, e) -> None:
        if HelpPopup.current is self:
            HelpPopup.current = None
        super().closeEvent(e)


class HelpButton(QPushButton):

    def __init__(self, title: str, text: str, tip: str = ""):
        super().__init__("?")
        self.setObjectName("Help")
        self.title, self.help_text, self.tip = title, text, tip
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("i18n_tip_skip", True)
        self.setProperty("i18n_text_skip", True)
        self.retranslate_ui()
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(tr("Help: {topic}", topic=tr(title)) if title else tr("Help"))
        self.clicked.connect(self.show_help)

    def retranslate_ui(self) -> None:
        self.setToolTip(tr("Click for help"))

    def why_text(self) -> str:
        from ..help_why import WHY
        return WHY.get(self.help_text, "")

    def show_help(self) -> None:
        if HelpPopup.current is not None:
            HelpPopup.current.close()
        why = self.why_text()
        pop = HelpPopup(tr(self.title), tr(self.help_text), tr(why) if why else "",
                        tr(self.tip) if self.tip else "", self.window())
        HelpPopup.current = pop
        pop.adjustSize()
        pos = self.mapToGlobal(QPoint(self.width() + 6, -8))
        screen = self.screen().availableGeometry()
        if pos.x() + pop.width() > screen.right():
            pos.setX(self.mapToGlobal(QPoint(0, 0)).x() - pop.width() - 6)
        pos.setY(min(pos.y(), screen.bottom() - pop.height()))
        pop.move(pos)
        pop.show()


class Card(QFrame):

    def __init__(self, title: str = "", hint_text: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(theme.pad(CARD_PAD_X), theme.pad(CARD_PAD_TOP), theme.pad(CARD_PAD_X),
                                      theme.pad(CARD_PAD_BOTTOM))
        self._title_src = title
        self.outer.setSpacing(SPACING + 2)
        self.header = QHBoxLayout()
        self.header.setSpacing(SPACING)
        self.header.addStretch(1)
        if title:
            self.title = label(tr(title).upper(), "CardTitle")
            self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.title.setProperty("i18n_text_skip", True)
            self.header.addWidget(self.title)
        self.header.addStretch(1)
        self.outer.addLayout(self.header)
        self.explain = None
        if hint_text:
            self.explain = label(hint_text, "CardExplain", wrap=True)
            self.outer.addWidget(self.explain)
        self.body = QVBoxLayout()
        self.body.setSpacing(SPACING + 2)
        self.outer.addLayout(self.body)

    def add(self, w) -> None:
        if isinstance(w, QWidget):
            self.body.addWidget(w)
        else:
            self.body.addLayout(w)

    def set_title(self, title: str) -> None:
        self._title_src = title
        if hasattr(self, "title"):
            self.title.setText(tr(title).upper())

    def retranslate_ui(self) -> None:
        if self._title_src and hasattr(self, "title"):
            self.title.setText(tr(self._title_src).upper())

    def refresh_metrics(self) -> None:
        self.outer.setContentsMargins(theme.pad(CARD_PAD_X), theme.pad(CARD_PAD_TOP), theme.pad(CARD_PAD_X),
                                      theme.pad(CARD_PAD_BOTTOM))


class FormGrid(QGridLayout):

    def __init__(self):
        super().__init__()
        self.setHorizontalSpacing(12)
        self.setVerticalSpacing(8)
        self.setColumnStretch(1, 1)
        self._row = 0

    def row(self, text: str, field, tooltip: str = "", tip: str = "") -> None:
        lb = label(text)
        self.addWidget(lb, self._row, 0, Qt.AlignmentFlag.AlignVCenter)
        if isinstance(field, QWidget):
            self.addWidget(field, self._row, 1)
        else:
            self.addLayout(field, self._row, 1)
        if tooltip:
            self.addWidget(HelpButton(text, tooltip, tip), self._row, 2, Qt.AlignmentFlag.AlignVCenter)
        self._row += 1

    def full(self, w, tooltip: str = "", title: str = "") -> None:
        if isinstance(w, QWidget):
            self.addWidget(w, self._row, 0, 1, 2)
        else:
            self.addLayout(w, self._row, 0, 1, 2)
        if tooltip:
            self.addWidget(HelpButton(title or getattr(w, "text", lambda: "")(), tooltip), self._row, 2,
                           Qt.AlignmentFlag.AlignVCenter)
        self._row += 1


class Fold(QWidget):

    def __init__(self, title: str, explanation: str, content: QWidget | None = None, opened: bool = False):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        self.toggle = QPushButton()
        self.toggle.setObjectName("FoldHeader")
        self.toggle.setProperty("i18n_text_skip", True)
        self.toggle.setCheckable(True)
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title = title
        v.addWidget(self.toggle)
        self.explain = hint(explanation)
        v.addWidget(self.explain)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 4, 0, 0)
        self.body_layout.setSpacing(8)
        if content is not None:
            self.body_layout.addWidget(content)
        v.addWidget(self.body)
        self.toggle.toggled.connect(self._set)
        self.toggle.setChecked(opened)
        self._set(opened)

    def add(self, w) -> None:
        if isinstance(w, QWidget):
            self.body_layout.addWidget(w)
        else:
            self.body_layout.addLayout(w)

    def _set(self, on: bool) -> None:
        self.toggle.setText(("▾  " if on else "▸  ") + tr(self._title))
        self.body.setVisible(on)

    def retranslate_ui(self) -> None:
        self._set(self.toggle.isChecked())


class ChoiceCards(QWidget):
    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str, str]], value: str | None = None, columns: int = 2):
        super().__init__()
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)
        self._buttons: dict[str, QPushButton] = {}
        for i, (key, title, text) in enumerate(options):
            b = QPushButton()
            b.setObjectName("Choice")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            inner = QVBoxLayout(b)
            inner.setContentsMargins(14, 10, 14, 12)
            inner.setSpacing(3)
            t = label(title, "ChoiceTitle")
            d = label(text, "ChoiceText", wrap=True)
            for w in (t, d):
                w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            inner.addWidget(t)
            inner.addWidget(d)
            inner.addStretch(1)
            b.setMinimumHeight(72)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            b.clicked.connect(lambda _=False, k=key: self._on(k))
            grid.addWidget(b, i // columns, i % columns)
            self._buttons[key] = b
        self._value = None
        self.set_value(value or options[0][0], emit=False)

    def _on(self, key: str) -> None:
        if key != self._value:
            self.set_value(key)
        else:
            self._buttons[key].setChecked(True)

    def set_value(self, key: str, emit: bool = True) -> None:
        if key not in self._buttons:
            return
        self._value = key
        for k, b in self._buttons.items():
            b.setChecked(k == key)
        if emit:
            self.changed.emit(key)

    def value(self) -> str:
        return self._value


def round_button(icon_name: str, tooltip: str) -> QPushButton:
    b = QPushButton()
    b.setObjectName("RoundButton")
    b.setIcon(icons.icon(icon_name, size=18))
    b.setIconSize(QSize(18, 16))
    b.setProperty("icon_name", icon_name)
    b.setToolTip(tooltip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def more_button(actions: list[tuple[str, str, object]], text: str = "More") -> QToolButton:
    from PySide6.QtWidgets import QMenu
    b = QToolButton()
    b.setObjectName("MoreButton")
    b.setText(text)
    b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    menu = QMenu(b)
    b._actions = {}
    for text_, icon_name, cb in actions:
        a = menu.addAction(icons.icon(icon_name, size=16), text_)
        a.triggered.connect(cb)
        b._actions[text_] = a
    b.setMenu(menu)
    return b


def hbox(*items, spacing: int = SPACING, stretch_last: bool = False) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(0, 0, 0, 0)
    for it in items:
        if it is None:
            lay.addStretch(1)
        elif isinstance(it, QWidget):
            lay.addWidget(it)
        else:
            lay.addLayout(it)
    if stretch_last:
        lay.addStretch(1)
    return lay


class Segmented(QFrame):
    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], value: str | None = None, tooltips: dict | None = None):
        super().__init__()
        self.setObjectName("Segmented")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        self._buttons: dict[str, QPushButton] = {}
        for key, text in options:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            if tooltips and key in tooltips:
                b.setToolTip(tooltips[key])
            b.clicked.connect(lambda _=False, k=key: self._on(k))
            lay.addWidget(b)
            self._buttons[key] = b
        self._value = None
        self.set_value(value or options[0][0], emit=False)

    def _on(self, key: str) -> None:
        if key != self._value:
            self.set_value(key)
        else:
            self._buttons[key].setChecked(True)

    def set_value(self, key: str, emit: bool = True) -> None:
        if key not in self._buttons:
            return
        self._value = key
        for k, b in self._buttons.items():
            b.setChecked(k == key)
        if emit:
            self.changed.emit(key)

    def value(self) -> str:
        return self._value

    def set_enabled_option(self, key: str, enabled: bool, tooltip: str = "") -> None:
        if key in self._buttons:
            self._buttons[key].setEnabled(enabled)
            if tooltip:
                self._buttons[key].setToolTip(tooltip)


class ParamControl(QWidget):
    valueChanged = Signal(float)
    toggled = Signal(bool)

    def __init__(self, name: str, description: str, minimum: float, maximum: float, value: float,
                 default: float, decimals: int = 2, suffix: str = "", scale: float = 1.0,
                 checkable: bool = False, checked: bool = True, steps: int = 200):
        super().__init__()
        self.minimum, self.maximum, self.default = minimum, maximum, default
        self.scale = scale
        self.steps = steps
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 2, 0, 2)
        v.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(6)
        self.check = QCheckBox(name) if checkable else None
        if self.check:
            self.check.setChecked(checked)
            self.check.toggled.connect(self._on_toggle)
            top.addWidget(self.check)
        else:
            top.addWidget(label(name))
        self.help = HelpButton(name, description)
        top.addWidget(self.help)
        top.addStretch(1)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, steps)
        self.slider.setMinimumWidth(80)
        self.spin = QDoubleSpinBox()
        self.spin.setDecimals(decimals)
        self.spin.setRange(minimum * scale, maximum * scale)
        self.spin.setSingleStep((maximum - minimum) * scale / 100.0)
        self.spin.setSuffix(suffix)
        self._fit_spin()
        self.spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.reset = tool_button("reset", "", size=14)
        self.reset.setProperty("i18n_tip_skip", True)
        self._reset_tip = (default * scale, suffix)
        self.retranslate_ui()
        top.addWidget(self.slider, 2)
        top.addWidget(self.spin)
        top.addWidget(self.reset)
        v.addLayout(top)
        self.description = description
        self._block = False
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)
        self.reset.clicked.connect(lambda: self.set_value(self.default, emit=True))
        self.set_value(value, emit=False)
        self._apply_enabled()

    def _fit_spin(self) -> None:
        fm = self.spin.fontMetrics()
        sp = self.spin
        texts = [f"{sp.minimum():.{sp.decimals()}f}{sp.suffix()}", f"{sp.maximum():.{sp.decimals()}f}{sp.suffix()}"]
        self.spin.setFixedWidth(max(fm.horizontalAdvance(t) for t in texts) + 46)

    def changeEvent(self, e):
        from PySide6.QtCore import QEvent
        if e.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange) and hasattr(self, "spin"):
            self._fit_spin()
        super().changeEvent(e)

    def retranslate_ui(self) -> None:
        if hasattr(self, "reset"):
            v, suffix = self._reset_tip
            self.reset.setToolTip(tr("Reset to default ({value})", value=f"{v:g}{suffix}"))

    def _to_pos(self, value: float) -> int:
        span = self.maximum - self.minimum
        return int(round((value - self.minimum) / span * self.steps)) if span else 0

    def _from_slider(self, pos: int) -> None:
        if self._block:
            return
        value = self.minimum + (self.maximum - self.minimum) * pos / self.steps
        self.set_value(value, emit=True, from_slider=True)

    def _from_spin(self, shown: float) -> None:
        if self._block:
            return
        self.set_value(shown / self.scale, emit=True)

    def set_value(self, value: float, emit: bool = True, from_slider: bool = False) -> None:
        value = float(min(max(value, self.minimum), self.maximum))
        self._block = True
        if not from_slider:
            self.slider.setValue(self._to_pos(value))
        self.spin.setValue(value * self.scale)
        self._block = False
        self._value = value
        if emit:
            self.valueChanged.emit(value)

    def value(self) -> float:
        return self._value

    def is_checked(self) -> bool:
        return self.check.isChecked() if self.check else True

    def set_checked(self, on: bool) -> None:
        if self.check:
            self.check.blockSignals(True)
            self.check.setChecked(on)
            self.check.blockSignals(False)
            self._apply_enabled()

    def _on_toggle(self, on: bool) -> None:
        self._apply_enabled()
        self.toggled.emit(on)

    def _apply_enabled(self) -> None:
        on = self.is_checked()
        for w in (self.slider, self.spin, self.reset):
            w.setEnabled(on)


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, text: str, action_text: str = "", action=None):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 30, 24, 30)
        v.setSpacing(6)
        v.addStretch(1)
        ic = QLabel()
        ic.setPixmap(icons.icon(icon_name, size=34).pixmap(34, 34))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(ic)
        t = label(title, "CardTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t)
        d = hint(text)
        d.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(d)
        if action_text and action:
            b = button(action_text, kind="Primary")
            b.clicked.connect(action)
            row = hbox(None, b, None)
            v.addSpacing(6)
            v.addLayout(row)
        v.addStretch(1)


class DropZone(QFrame):
    dropped = Signal(list)
    clicked = Signal()

    def __init__(self, text: str):
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        ic = QLabel()
        ic.setPixmap(icons.icon("import", size=18).pixmap(18, 18))
        lay.addWidget(ic)
        self.text = hint(text)
        lay.addWidget(self.text, 1)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            set_tone(self, "")
            self.setProperty("active", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, e):
        self.setProperty("active", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, e):
        self.dragLeaveEvent(e)
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.dropped.emit(paths)


def confirm(parent, title: str, text: str, ok_text: str = "Continue", danger: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
    ok = box.addButton(ok_text, QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is ok


def fade_in(widget: QWidget, ms: int = 160) -> None:
    eff = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


def fmt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    m = int(seconds // 60)
    s = seconds - 60 * m
    return f"{m}:{s:05.2f}"
