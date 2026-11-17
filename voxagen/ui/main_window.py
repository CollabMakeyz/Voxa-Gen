from __future__ import annotations

from PySide6.QtCore import QByteArray, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from .. import APP_NAME, __version__
from ..core.workers import Task
from . import icons
from ..i18n import tr
from .context import AppContext
from .pages.appearance import AppearancePage
from .pages.generator import GeneratorPage
from .pages.lab import LabPage
from .pages.settings import SettingsPage
from .widgets.common import Card, confirm, fade_in, refresh_icons
from .widgets.notifier import Notifier
from .widgets.shell import NAV_ICON_SIZE, ContentHost, LogoView, nav_icon


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(1360, 780)
        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        sv = QVBoxLayout(self.sidebar)
        sv.setContentsMargins(0, 22, 0, 4)
        sv.setSpacing(0)
        self.logo = LogoView()
        logo_row = QHBoxLayout()
        logo_row.setContentsMargins(10, 0, 0, 0)
        logo_row.addWidget(self.logo)
        logo_row.addStretch(1)
        sv.addLayout(logo_row)
        sv.addSpacing(max(8, 176 - 22 - self.logo.height()))

        self.stack = QStackedWidget()
        self.stack.setObjectName("PageHost")
        self.pages = [GeneratorPage(ctx), LabPage(ctx), AppearancePage(ctx), SettingsPage(ctx)]
        self._presets_window = None
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.nav: dict[str, QPushButton] = {}
        nav_box = QVBoxLayout()
        nav_box.setContentsMargins(10, 0, 10, 0)
        nav_box.setSpacing(15)
        for i, page in enumerate(self.pages):
            self.stack.addWidget(page)
            b = QPushButton(self._nav_text(page))
            b.setObjectName("NavButton")
            b.setProperty("i18n_text_skip", True)
            b.setProperty("i18n_tip_skip", True)
            b.setCheckable(True)
            b.setIcon(nav_icon(page.page_id))
            b.setIconSize(NAV_ICON_SIZE)
            b.setFixedHeight(35)
            b.setToolTip(f"{tr(page.title)}  (Ctrl+{i + 1})")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setProperty("silent", True)
            b.clicked.connect(lambda _=False, pid=page.page_id: self.navigate(pid))
            self.group.addButton(b)
            nav_box.addWidget(b)
            self.nav[page.page_id] = b
            sc = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            sc.activated.connect(lambda pid=page.page_id: self.navigate(pid))
        sv.addLayout(nav_box)
        sv.addStretch(1)
        self.version = QLabel(f"Voxa {__version__}")
        self.version.setObjectName("Version")
        self.version.setProperty("i18n_skip", True)
        self.version.setContentsMargins(4, 0, 0, 0)
        sv.addWidget(self.version)
        lay.addWidget(self.sidebar)
        self.content = ContentHost(self.stack)
        self.content.tabs.currentChanged.connect(lambda i: self.stack.currentWidget().set_tab(i))
        lay.addWidget(self.content, 1)
        self.setCentralWidget(central)


        self.notifier = Notifier(self)
        ctx.notifyRequested.connect(self._notify)
        ctx.navigateRequested.connect(self.navigate)
        ctx.themeChanged.connect(self._theme_changed)

        self.set_compact(ctx.settings.sidebar_compact)
        if ctx.settings.window_geometry:
            try:
                self.restoreGeometry(QByteArray.fromHex(ctx.settings.window_geometry.encode()))
            except Exception:
                pass
        self._current = ""
        self.navigate(ctx.settings.last_page if ctx.settings.last_page in self.nav else "generator", sound=False)

    def navigate(self, page_id: str, sound: bool = True) -> None:
        if page_id == "presets":
            return self.open_presets()
        if page_id == "samples":
            self.navigate("generator", sound)
            gen = self.pages[0]
            gen.go_tab(gen.TAB_SAMPLES)
            return
        if page_id not in self.nav or page_id == self._current:
            if page_id in self.nav:
                self.nav[page_id].setChecked(True)
            return
        page = next(p for p in self.pages if p.page_id == page_id)
        self.nav[page_id].setChecked(True)
        self.stack.setCurrentWidget(page)
        if self.ctx.settings.animations and self._current:
            fade_in(page, 170)
        self._current = page_id
        self.ctx.settings.last_page = page_id
        self.ctx.save_soon()
        if sound:
            self.ctx.sound("page_open")
        self.content.tabs.set_tabs(page.tabs, page.current_tab)
        page.on_shown()

    def open_presets(self) -> None:
        from .pages.presets import PresetsDialog
        if self._presets_window is None:
            self._presets_window = PresetsDialog(self.ctx, self)
        self._presets_window.show()
        self._presets_window.raise_()
        self._presets_window.activateWindow()
        self.ctx.sound("page_open")

    @staticmethod
    def _nav_text(page) -> str:
        return " " + tr("Generate" if page.page_id == "generator" else page.title)

    def retranslate_ui(self) -> None:
        if not hasattr(self, "nav"):
            return
        compact = self.ctx.settings.sidebar_compact
        for i, page in enumerate(self.pages):
            b = self.nav[page.page_id]
            b.setText("" if compact else self._nav_text(page))
            b.setToolTip(f"{tr(page.title)}  (Ctrl+{i + 1})")

    def set_compact(self, on: bool) -> None:
        for pid, b in self.nav.items():
            page = next(p for p in self.pages if p.page_id == pid)
            b.setText("" if on else self._nav_text(page))
        self.logo.setVisible(not on)
        self.version.setText(__version__ if on else f"Voxa {__version__}")
        self.sidebar.setFixedWidth(72 if on else 320)

    def _notify(self, spec) -> None:
        if self.ctx.settings.show_toasts or spec.tone == "error" or spec.actions:
            self.notifier.notify(spec)

    def _theme_changed(self, _name: str) -> None:
        refresh_icons(self)
        for pid, b in self.nav.items():
            b.setIcon(nav_icon(pid))
        for c in self.findChildren(Card):
            c.refresh_metrics()
        if self._presets_window is not None:
            refresh_icons(self._presets_window)
            for c in self._presets_window.findChildren(Card):
                c.refresh_metrics()
        self.content.tabs.update()
        self.logo.update()
        self.content._tile = None
        self.setWindowIcon(icons.app_icon())
        for w in self.findChildren(QWidget):
            w.update()

    def closeEvent(self, e):
        gen = self.pages[0]
        if gen.is_exporting() or gen.batch.running:
            if not confirm(self, tr("Export in progress"), tr("An export is running. Cancel it and quit?"), tr("Quit"),
                           danger=True):
                e.ignore()
                return
        elif not gen.project.confirm_discard():
            e.ignore()
            return
        if self._presets_window is not None:
            self._presets_window.close()
        self.ctx.stop_players()
        self.notifier.close_all()
        Task.cancel_all_and_wait(8000)
        self.ctx.settings.window_geometry = bytes(self.saveGeometry().toHex()).decode()
        self.ctx.save_now()
        super().closeEvent(e)
