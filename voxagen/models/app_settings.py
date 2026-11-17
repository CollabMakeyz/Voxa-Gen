from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .config import GeneratorConfig
from .serialization import from_dict, to_dict

SETTINGS_VERSION = 1

UI_SOUND_EVENTS: dict[str, tuple[str, bool, str]] = {
    "click_down":   ("ClickDown", True, "Click (press)"),
    "click_up":     ("ClickUp", True, "Click (release)"),
    "select":       ("keyboard2", True, "Selection"),
    "keyboard":     ("keyboard1", True, "Keyboard interaction"),
    "confirm":      ("keyboard3", True, "Confirmation"),
    "page_open":    ("openWindow", True, "Page / panel open"),
    "page_close":   ("exitWindow", True, "Panel close"),
    "seq_add":      ("noteLay", True, "Sequence: add element"),
    "seq_remove":   ("noteErase", True, "Sequence: remove element"),
    "undo":         ("undo", True, "Undo"),
    "drag_start":   ("stretch1_UI", True, "Drag start"),
    "drag_move":    ("stretch2_UI", False, "Drag / resize"),
    "drag_snap":    ("stretchSNAP_UI", True, "Drop / snap"),
    "export_start": ("metronome1", True, "Export started"),
    "export_done":  ("metronome2", True, "Export completed"),
    "error":        ("hitNoteOpponent", True, "Error"),
    "cancel":       ("exitWindow", True, "Operation cancelled"),
    "preview_note": ("hitNotePlayer", False, "Preview feedback"),
}


@dataclass
class SoundEventSettings:
    enabled: bool = True
    volume: float = 1.0
    source: str = ""


@dataclass
class UiSoundSettings:
    enabled: bool = True
    master_volume: float = 0.6
    events: dict[str, SoundEventSettings] = field(default_factory=dict)

    def event(self, event_id: str) -> SoundEventSettings:
        if event_id not in self.events:
            default = UI_SOUND_EVENTS.get(event_id, ("", False, event_id))
            self.events[event_id] = SoundEventSettings(enabled=default[1], volume=1.0, source=default[0])
        ev = self.events[event_id]
        if not ev.source:
            ev.source = UI_SOUND_EVENTS.get(event_id, ("",))[0]
        return ev


APPEARANCE_COLORS = ("primary", "secondary", "highlight", "background", "panel", "cards", "buttons", "text", "logo")


@dataclass
class ThemeSpec:
    name: str = "Voxa Dark"
    base: str = "dark"
    colors: dict[str, str] = field(default_factory=dict)
    font_family: str = "Inter"
    font_scale: float = 1.0
    radius_scale: float = 1.0
    density: str = "comfortable"
    card_style: str = "solid"
    icon_style: str = "hand"


@dataclass
class AppearanceSettings:
    current: ThemeSpec = field(default_factory=ThemeSpec)
    saved: list[ThemeSpec] = field(default_factory=list)


@dataclass
class AppSettings:
    version: int = SETTINGS_VERSION
    theme: str = "dark"
    language: str = ""
    appearance: AppearanceSettings = field(default_factory=AppearanceSettings)
    animations: bool = True
    sidebar_compact: bool = False
    show_toasts: bool = True
    taskbar_alert_on_finish: bool = True
    confirm_on_cancel: bool = True
    preview_volume: float = 0.8
    preview_auto_render: bool = True
    preview_loop: bool = False
    default_output_dir: str = ""
    last_page: str = "generator"
    window_geometry: str = ""
    ui_sounds: UiSoundSettings = field(default_factory=UiSoundSettings)
    generator: GeneratorConfig = field(default_factory=GeneratorConfig)
    recent_folders: list[str] = field(default_factory=list)
    recent_projects: list[str] = field(default_factory=list)
    batch_queue: list[dict] = field(default_factory=list)


class SettingsStore:

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> AppSettings:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            settings = from_dict(AppSettings, data)
            if "appearance" not in data and settings.theme == "light":
                settings.appearance.current = ThemeSpec("Voxa Light", "light")
            return settings
        except FileNotFoundError:
            return AppSettings()
        except (OSError, ValueError):
            try:
                self.path.replace(self.path.with_suffix(".corrupt.json"))
            except OSError:
                pass
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        settings.version = SETTINGS_VERSION
        atomic_write_json(self.path, to_dict(settings))


def atomic_write_json(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
