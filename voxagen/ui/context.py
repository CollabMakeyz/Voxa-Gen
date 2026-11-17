from __future__ import annotations

import random

from PySide6.QtCore import QEvent, QObject, QTimer, Signal
from PySide6.QtWidgets import QAbstractButton, QApplication, QWidget

from .. import i18n
from ..i18n import tr

from ..core.notifications.ui_sounds import UiSoundEngine
from ..core.presets.manager import PresetManager
from ..core.samples.library import SampleLibrary
from ..models.app_settings import AppSettings, SettingsStore
from ..models.config import GeneratorConfig
from ..paths import user_data_dir
from . import theme


class _ClickSounds(QObject):

    def __init__(self, ctx: "AppContext"):
        super().__init__()
        self.ctx = ctx

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Type.Polish and isinstance(obj, QWidget):
            from .i18n_qt import translate_object
            try:
                translate_object(obj)
            except Exception:
                pass
            return False
        if t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease) and isinstance(obj, QAbstractButton):
            if obj.isEnabled() and not obj.property("silent"):
                self.ctx.sound("click_down" if t == QEvent.Type.MouseButtonPress else "click_up")
        return False


class AppContext(QObject):
    libraryChanged = Signal()
    configChanged = Signal(str)
    themeChanged = Signal(str)
    languageChanged = Signal(str)
    presetsChanged = Signal(str)
    notifyRequested = Signal(object)
    busyChanged = Signal(bool)
    navigateRequested = Signal(str)

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.store = SettingsStore(user_data_dir() / "settings.json")
        self.settings: AppSettings = self.store.load()
        if not self.settings.generator.order.use_seed:
            self.settings.generator.order.seed = random.randrange(1, 2 ** 31)
        self.library = SampleLibrary()
        self.presets = PresetManager()
        self.sounds = UiSoundEngine(self.settings.ui_sounds)
        self._players = []
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self.save_now)
        self._click_filter = _ClickSounds(self)
        app.installEventFilter(self._click_filter)
        self.busy = False
        i18n.set_language(self.settings.language or system_language())
        from .i18n_qt import mark_shown
        mark_shown()

    @property
    def config(self) -> GeneratorConfig:
        return self.settings.generator

    def touch(self, section: str = "") -> None:
        self.configChanged.emit(section)
        self.save_soon()

    def save_soon(self) -> None:
        self._save_timer.start()

    def save_now(self) -> None:
        try:
            self.store.save(self.settings)
        except OSError as exc:
            self.toast(f"Could not save settings: {exc}", "error")

    def apply_theme(self, base: str | None = None) -> None:
        spec = self.settings.appearance.current
        if base in ("dark", "light") and base != spec.base:
            spec.base = base
            spec.name = "Voxa Light" if base == "light" else "Voxa Dark"
            spec.colors = {}
        tokens = theme.fix_contrast(theme.build_tokens(spec.base, spec.colors))
        theme.set_look(theme.Look(
            font_family=spec.font_family or theme.FONT_FAMILY,
            font_scale=min(1.35, max(0.85, float(spec.font_scale or 1.0))),
            radius_scale=min(1.5, max(0.0, float(spec.radius_scale))),
            density=spec.density if spec.density in theme.DENSITY else "comfortable",
            card_style=spec.card_style if spec.card_style in ("solid", "outlined") else "solid",
            icon_style=spec.icon_style if spec.icon_style in ("hand", "line", "bold") else "hand",
            cjk=i18n.is_cjk()))
        t = theme.set_current(tokens)
        self.settings.theme = spec.base
        self.app.setFont(theme.app_font(10))
        self.app.setPalette(theme.palette(t))
        self.app.setStyleSheet(theme.stylesheet(t))
        from . import icons
        icons._pixmap.cache_clear()
        icons._hand_icon.cache_clear()
        self.themeChanged.emit(t.name)
        self.save_soon()

    def set_language(self, code: str) -> None:
        code = code if code in i18n.LANGUAGES else i18n.DEFAULT
        self.settings.language = code
        cjk_before = theme.look().cjk
        from .i18n_qt import switch_language
        switch_language(code, [w for w in QApplication.topLevelWidgets()])
        if i18n.is_cjk() != cjk_before:
            self.apply_theme()
        self.languageChanged.emit(code)
        self.save_soon()

    def sound(self, event_id: str) -> None:
        try:
            self.sounds.play(event_id)
        except Exception:
            pass

    def toast(self, message: str, tone: str = "info") -> None:
        if tone == "error":
            self.sound("error")
        from .widgets.notifier import TITLES, NotificationSpec
        self.notifyRequested.emit(NotificationSpec(tr(TITLES.get(tone, "Voxa GEN")), i18n.translate(message), tone))

    def notify(self, title: str, message: str = "", tone: str = "info", actions=None, ms: int | None = None) -> None:
        from .widgets.notifier import NotificationSpec
        if tone == "error":
            self.sound("error")
        self.notifyRequested.emit(NotificationSpec(i18n.translate(title), i18n.translate(message), tone,
                                                   list(actions or []), ms))

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.busyChanged.emit(busy)

    def register_player(self, player) -> None:
        self._players.append(player)
        player.set_volume(self.settings.preview_volume)
        player.loop = self.settings.preview_loop

        def _on_state(state, p=player):
            if state == "playing":
                self.stop_players(except_=p)
        player.stateChanged.connect(_on_state)

    def stop_players(self, except_=None) -> None:
        for p in self._players:
            if p is not except_ and p.state != "stopped":
                p.stop()

    def set_preview_volume(self, v: float) -> None:
        self.settings.preview_volume = v
        for p in self._players:
            p.set_volume(v)
        self.save_soon()

    def reload_session_samples(self) -> None:
        cfg = self.config
        self.library.clear()
        from pathlib import Path
        if cfg.sample_folder and Path(cfg.sample_folder).is_dir():
            self.library.add_folder(cfg.sample_folder)
        if cfg.sample_paths:
            self.library.add_files([p for p in cfg.sample_paths])
        self.libraryChanged.emit()

    def remember_samples(self) -> None:
        cfg = self.config
        folder = cfg.sample_folder
        from pathlib import Path
        extra = []
        for s in self.library.samples():
            if not folder or Path(s.path).parent != Path(folder):
                extra.append(s.path)
        cfg.sample_paths = extra
        self.save_soon()


def system_language() -> str:
    from PySide6.QtCore import QLocale
    name = QLocale.system().name()
    if name.startswith("pt"):
        return "pt_PT" if name == "pt_PT" else "pt_BR"
    if name.startswith("es"):
        return "es"
    if name.startswith("ja"):
        return "ja"
    return "en"
