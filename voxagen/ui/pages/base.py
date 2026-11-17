from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from ..widgets.common import elastic, hbox, label


class FitScrollArea(QScrollArea):

    def __init__(self, inner: QWidget):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWidget(inner)
        inner.installEventFilter(self)
        self._fit()

    def _fit(self) -> None:
        need = self.widget().minimumSizeHint().width() + self.verticalScrollBar().sizeHint().width() + 6
        if need != self.minimumWidth():
            self.setMinimumWidth(need)

    def eventFilter(self, obj, ev):
        if obj is self.widget() and ev.type() == QEvent.Type.LayoutRequest:
            self._fit()
        return False


class Columns(QWidget):

    GAP = 16

    def __init__(self, columns: list[list[QWidget]]):
        super().__init__()
        self.cols = []
        for cards in columns:
            holder = QWidget()
            v = QVBoxLayout(holder)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(self.GAP)
            for c in cards:
                v.addWidget(c)
            v.addStretch(1)
            holder.setParent(self)
            self.cols.append(holder)
        self._stacked = None
        self._relayout(stacked=False)

    def _need(self) -> int:
        return sum(c.minimumSizeHint().width() for c in self.cols) + self.GAP * (len(self.cols) - 1)

    def _relayout(self, stacked: bool) -> None:
        if stacked == self._stacked:
            return
        self._stacked = stacked
        old = self.layout()
        if old is not None:
            for c in self.cols:
                old.removeWidget(c)
            QWidget().setLayout(old)
        lay = QVBoxLayout(self) if stacked else QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(self.GAP)
        for c in self.cols:
            lay.addWidget(c, 1)
        if stacked:
            lay.addStretch(1)

    def resizeEvent(self, e):
        self._relayout(stacked=len(self.cols) > 1 and e.size().width() < self._need())
        super().resizeEvent(e)

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        w = max((c.minimumSizeHint().width() for c in self.cols), default=0)
        return QSize(w, super().minimumSizeHint().height())


class Page(QWidget):
    page_id = ""
    title = ""
    subtitle = ""
    icon = ""
    tabs: list[str] = []
    show_title = True

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(20, 16, 20, 14)
        self.root.setSpacing(12)
        self.header = hbox(spacing=10)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        if self.show_title:
            titles.addWidget(label(self.title, "PageTitle"))
            if self.subtitle:
                titles.addWidget(elastic(label(self.subtitle, "PageSubtitle")))
        self.header.addLayout(titles, 1)
        self.header.addStretch(1)
        header_box = QWidget()
        header_box.setObjectName("PageHeader")
        header_box.setLayout(self.header)
        self.root.addWidget(header_box)
        self.header_box = header_box
        self.current_tab = 0
        self.tab_stack = QStackedWidget() if self.tabs else None

    def add_tab(self, widget: QWidget) -> None:
        self.tab_stack.addWidget(widget)

    def set_tab(self, i: int) -> None:
        if self.tab_stack is None or not (0 <= i < self.tab_stack.count()):
            return
        self.current_tab = i
        self.tab_stack.setCurrentIndex(i)
        if self.ctx.settings.animations:
            from ..widgets.common import fade_in
            fade_in(self.tab_stack.currentWidget(), 140)
        self.ctx.sound("select")

    def scroll(self, inner: QWidget) -> QScrollArea:
        return FitScrollArea(inner)

    def columns(self, *columns) -> QScrollArea:
        return self.scroll(Columns([list(c) for c in columns]))

    def on_shown(self) -> None:
        pass

    def on_theme(self) -> None:
        pass
