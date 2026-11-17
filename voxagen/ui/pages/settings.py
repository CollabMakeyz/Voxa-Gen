from __future__ import annotations

import os
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGridLayout, QLineEdit, QSlider, QVBoxLayout, QWidget,
)

from ... import __version__, i18n
from ...i18n import LANGUAGES, tr
from ...core.audio.pipeline import clear_memory_caches
from ...core.notifications.ui_sounds import builtin_sounds, validate_user_sound
from ...models.app_settings import UI_SOUND_EVENTS, UiSoundSettings
from ...paths import cache_dir, resource_root, user_data_dir, user_sounds_dir
from ..widgets.common import Card, FormGrid, Segmented, button, confirm, hbox, hint, label, tool_button
from .base import Page

CUSTOM = "__custom__"


def _dir_size(p: Path) -> int:
    total = 0
    for root, _, files in os.walk(p):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


class SoundRow:
    def __init__(self, page: "SettingsPage", grid: QGridLayout, row: int, event_id: str):
        self.page, self.event_id = page, event_id
        ctx = page.ctx
        self.ev = ctx.settings.ui_sounds.event(event_id)
        self.enabled = QCheckBox(UI_SOUND_EVENTS[event_id][2])
        self.enabled.setChecked(self.ev.enabled)
        self.source = QComboBox()
        self.source.setMinimumWidth(150)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(100)
        self.volume.setValue(int(self.ev.volume * 100))
        self.b_play = button("Play", "play")
        self.b_play.setProperty("silent", True)
        self.b_play.setToolTip("Hear this sound")
        self.b_file = button("Your file…", "folder")
        self.b_file.setToolTip("Use your own sound file (WAV, OGG, MP3, FLAC; up to 5 seconds)")
        self.b_reset = button("Reset", "reset")
        self.b_reset.setToolTip(tr("Back to the default sound: {name}", name=UI_SOUND_EVENTS[event_id][0]))
        for c, w in enumerate((self.enabled, self.source, self.volume, self.b_play, self.b_file, self.b_reset)):
            grid.addWidget(w, row, c)
        self.fill_sources()
        self.enabled.toggled.connect(self._enabled)
        self.volume.valueChanged.connect(self._volume)
        self.source.currentIndexChanged.connect(self._source)
        self.b_play.clicked.connect(lambda: ctx.sounds.play(event_id, force=True))
        self.b_file.clicked.connect(self.choose_file)
        self.b_reset.clicked.connect(self.reset)

    def fill_sources(self) -> None:
        self.source.blockSignals(True)
        self.source.clear()
        for name in builtin_sounds():
            self.source.addItem(name, name)
        src = self.ev.source
        if src and self.source.findData(src) < 0:
            self.source.addItem(tr("Custom · {name}", name=Path(src).name), src)
        self.source.setCurrentIndex(max(0, self.source.findData(src)))
        self.source.blockSignals(False)

    def _enabled(self, on):
        self.ev.enabled = on
        self.page.ctx.save_soon()

    def _volume(self, v):
        self.ev.volume = v / 100.0
        self.page.ctx.save_soon()

    def _source(self, _):
        self.ev.source = self.source.currentData()
        self.page.ctx.sounds.invalidate(self.ev.source)
        self.page.ctx.save_soon()

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self.page, "Choose sound", "", "Audio (*.wav *.ogg *.mp3 *.flac)")
        if not path:
            return
        err = validate_user_sound(path)
        if err:
            return self.page.ctx.toast(err, "error")
        dest = user_sounds_dir() / f"{self.event_id}{Path(path).suffix.lower()}"
        try:
            shutil.copyfile(path, dest)
        except OSError as exc:
            return self.page.ctx.toast(tr("Could not import sound: {error}", error=str(exc)), "error")
        self.ev.source = str(dest)
        self.page.ctx.sounds.invalidate(str(dest))
        self.fill_sources()
        self.page.ctx.save_soon()
        self.page.ctx.sounds.play(self.event_id, force=True)

    def reset(self) -> None:
        default, enabled, _ = UI_SOUND_EVENTS[self.event_id]
        self.ev.source, self.ev.enabled, self.ev.volume = default, enabled, 1.0
        self.enabled.setChecked(enabled)
        self.volume.setValue(100)
        self.fill_sources()
        self.page.ctx.save_soon()


class SettingsPage(Page):
    page_id = "settings"
    title = "Settings"
    subtitle = "Preferences are saved automatically"
    icon = "settings"
    tabs = ["General", "Sounds", "Notifications", "Export & preview", "About"]
    show_title = False

    def __init__(self, ctx):
        super().__init__(ctx)
        s = ctx.settings

        c = Card("General", "Language and how the app behaves. Colours, fonts and sizes are on the Appearance page.")
        g = FormGrid()
        self.language = QComboBox()
        self.language.setProperty("i18n_items_skip", True)
        for code, name in LANGUAGES.items():
            self.language.addItem(name, code)
        self.language.setCurrentIndex(max(0, self.language.findData(i18n.language())))
        self.language.currentIndexChanged.connect(lambda _: ctx.set_language(self.language.currentData()))
        g.row("Language", hbox(self.language, None),
              "The language of every text in Voxa GEN: buttons, explanations, help and notifications. It changes "
              "right away; nothing restarts and no work is lost.",
              "Pirate English and Meowgwenge are joke languages, but everything still works and stays understandable.")
        b_look = button("Open Appearance", "palette")
        b_look.clicked.connect(lambda: ctx.navigateRequested.emit("appearance"))
        g.row("Theme and colours", hbox(b_look, None), "Themes, colours, font, text size and roundness live on the "
                                                       "Appearance page.")
        self.animations = QCheckBox("Animated transitions")
        self.animations.setChecked(s.animations)
        self.animations.toggled.connect(lambda on: self._set("animations", on))
        g.full(self.animations, "Short fades when you change page or tab. Turn off if you prefer instant changes.",
               "Animations")
        self.compact = QCheckBox("Small sidebar (icons only)")
        self.compact.setChecked(s.sidebar_compact)
        self.compact.toggled.connect(self._compact)
        g.full(self.compact, "Hides the logo and the page names to leave more room for the content.", "Small sidebar")
        c.add(g)
        self.add_tab(self.columns([c]))

        c = Card("Interface sounds", 'Small sounds for clicks, exports and errors. They have their own audio channel and never end up in previews or exported files.')
        self.snd_all = QCheckBox("Play interface sounds")
        self.snd_all.setChecked(s.ui_sounds.enabled)
        self.snd_all.toggled.connect(self._sounds_enabled)
        self.snd_master = QSlider(Qt.Orientation.Horizontal)
        self.snd_master.setRange(0, 100)
        self.snd_master.setValue(int(s.ui_sounds.master_volume * 100))
        self.snd_master.setFixedWidth(160)
        self.snd_master.valueChanged.connect(self._sounds_master)
        b_def = button("Restore default sounds", "reset")
        b_def.clicked.connect(self.restore_sounds)
        c.add(hbox(self.snd_all, label("Volume"), self.snd_master, None, b_def))
        c.add(hint("Each event below can be switched off, made quieter, previewed, or replaced by your own "
                   "file (WAV, OGG, MP3 or FLAC, up to 5 seconds)."))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        for col, head in enumerate(("When", "Sound", "Volume")):
            grid.addWidget(label(head, "SubTitle"), 0, col)
        self.sound_rows = [SoundRow(self, grid, r + 1, e) for r, e in enumerate(UI_SOUND_EVENTS)]
        grid.setColumnStretch(6, 1)
        c.add(grid)
        self.add_tab(self.columns([c]))

        c = Card("Notifications", "Voxa GEN shows its own notifications in the top-right corner of your screen. "
                                  "Errors and finished exports are always shown.")
        g = FormGrid()
        for attr, text, explain in (
                ("show_toasts", "Show other notifications",
                 "Small confirmations such as “Preset saved” or “Pitch analysed”."),
                ("taskbar_alert_on_finish", "Flash the taskbar when an export finishes",
                 "Useful when Voxa GEN is behind other windows during a long export."),
                ("confirm_on_cancel", "Ask before cancelling an export",
                 "Prevents cancelling a long export by accident.")):
            cb = QCheckBox(text)
            cb.setChecked(getattr(s, attr))
            cb.toggled.connect(lambda on, a=attr: self._set(a, on))
            g.full(cb, explain, text)
        c.add(g)
        self.add_tab(self.columns([c]))

        c = Card("Export & preview", "Defaults for new exports and how previews behave.")
        g = FormGrid()
        self.out = QLineEdit(s.default_output_dir)
        self.out.setPlaceholderText(str(Path.home() / "Documents"))
        self.out.textChanged.connect(lambda t: self._set("default_output_dir", t.strip()))
        b = button("Browse..", "folder")
        b.clicked.connect(self._choose_out)
        g.row("Default export folder", hbox(self.out, b),
              "Where exports go when the Generator's “Save in” field is empty.")
        self.pvol = QSlider(Qt.Orientation.Horizontal)
        self.pvol.setRange(0, 100)
        self.pvol.setValue(int(s.preview_volume * 100))
        self.pvol.setFixedWidth(160)
        self.pvol.valueChanged.connect(lambda val: ctx.set_preview_volume(val / 100.0))
        g.row("Preview volume", hbox(self.pvol, None), "Only changes how loud previews play. Exports are not affected.")
        self.auto = QCheckBox("Update previews automatically")
        self.auto.setChecked(s.preview_auto_render)
        self.auto.toggled.connect(lambda on: self._set("preview_auto_render", on))
        g.full(self.auto, "Re-render previews when you change a setting. Turn off on slow computers and use the "
                          "Render button instead.", "Automatic previews")
        self.loop = QCheckBox("Loop previews")
        self.loop.setChecked(s.preview_loop)
        self.loop.toggled.connect(lambda on: self._set("preview_loop", on))
        g.full(self.loop, "Start previews with looping switched on.", "Loop previews")
        self.cache_label = hint("")
        b_cache = button("Clear", "trash")
        b_cache.clicked.connect(self.clear_cache)
        g.row("Saved renders", hbox(self.cache_label, None, b_cache),
              "Processed notes are kept on disk so previews and exports don't redo the same work. Clearing frees "
              "space; nothing else changes.")
        c.add(g)
        p = Card("Presets", "Undo changes you made to the presets that come with Voxa GEN. Your own presets "
                            "are kept.")
        b_restore = button("Restore built-in presets", "reset")
        b_restore.clicked.connect(self.restore_presets)
        b_open = button("Manage presets", "presets")
        b_open.clicked.connect(lambda: ctx.navigateRequested.emit("presets"))
        p.add(hbox(b_restore, b_open, None))
        self.add_tab(self.columns([c], [p]))

        c = Card("About", "Version, license, credits and where your data is stored.")
        c.add(label(f"Voxa GEN {__version__}", "SubTitle"))
        c.add(hint("Public release"))
        c.add(label("© 2026 Rambyte Team", wrap=True))
        c.add(hint("Voxa GEN is free software: you can share and change it under the GNU General Public "
                   "License, version 3 or later. It comes with no warranty."))
        self.about_data = hint("")
        self.about_cache = hint("")
        c.add(self.about_data)
        c.add(self.about_cache)
        self.retranslate_ui()
        b_docs = button("Documentation", "file")
        b_docs.clicked.connect(lambda: self._open(resource_root() / "docs"))
        b_gpl = button("License (GPL-3.0)", "info")
        b_gpl.clicked.connect(lambda: self._open(resource_root() / "LICENSE"))
        b_lic = button("Credits and licenses", "info")
        b_lic.clicked.connect(lambda: self._open(resource_root() / "docs" / "LICENSES.md"))
        b_data = button("Open data folder", "folder")
        b_data.clicked.connect(lambda: self._open(user_data_dir()))
        c.add(hbox(b_docs, b_gpl, b_lic, b_data, None))

        cr = Card("Credits", "The people and projects Voxa GEN is built on.")
        for line in (
            "Made by Rambyte Team.",
            "Interface sounds: Friday Night Funkin' charting sounds by The Funkin' Crew Inc., used with credit.",
            "Fonts: Inter by Rasmus Andersson (SIL OFL 1.1); VCR OSD Mono by Riciery Leal, used with credit.",
            "Pitch analysis and the Legacy mode: Praat by Paul Boersma and David Weenink, through Parselmouth "
            "by Yannick Jadoul (GPL-3.0).",
            "Voice analysis and resynthesis: WORLD by Masanori Morise, through pyworld.",
            "Also: Qt / PySide6, NumPy, SciPy, libsndfile and libsoxr.",
        ):
            cr.add(hint(line))
        self.add_tab(self.columns([c], [cr]))
        self.root.addWidget(self.tab_stack, 1)

    def retranslate_ui(self) -> None:
        if hasattr(self, "about_data"):
            self.about_data.setText(tr("Settings, presets and projects: {path}", path=str(user_data_dir())))
            self.about_cache.setText(tr("Saved renders: {path}", path=str(cache_dir())))
            for w in (self.about_data, self.about_cache):
                w.setProperty("i18n_text_skip", True)

    def on_shown(self) -> None:
        mb = _dir_size(cache_dir()) / 1e6
        self.cache_label.setText(tr("{mb} MB", mb=f"{mb:.1f}"))
        self.pvol.blockSignals(True)
        self.pvol.setValue(int(self.ctx.settings.preview_volume * 100))
        self.pvol.blockSignals(False)
        self.language.blockSignals(True)
        self.language.setCurrentIndex(max(0, self.language.findData(i18n.language())))
        self.language.blockSignals(False)

    def _set(self, attr: str, value) -> None:
        setattr(self.ctx.settings, attr, value)
        self.ctx.save_soon()

    def _compact(self, on: bool) -> None:
        self._set("sidebar_compact", on)
        w = self.window()
        if hasattr(w, "set_compact"):
            w.set_compact(on)

    def _sounds_enabled(self, on: bool) -> None:
        self.ctx.settings.ui_sounds.enabled = on
        self.ctx.save_soon()

    def _sounds_master(self, v: int) -> None:
        self.ctx.settings.ui_sounds.master_volume = v / 100.0
        self.ctx.save_soon()

    def restore_sounds(self) -> None:
        self.ctx.settings.ui_sounds.events.clear()
        self.ctx.settings.ui_sounds.enabled = True
        self.ctx.settings.ui_sounds.master_volume = UiSoundSettings().master_volume
        self.snd_all.setChecked(True)
        self.snd_master.setValue(int(UiSoundSettings().master_volume * 100))
        for r in self.sound_rows:
            r.ev = self.ctx.settings.ui_sounds.event(r.event_id)
            r.reset()
        self.ctx.sounds.invalidate()
        self.ctx.toast("Default sounds restored.", "ok")

    def _choose_out(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Default export directory", self.out.text() or str(Path.home()))
        if d:
            self.out.setText(d)

    def clear_cache(self) -> None:
        if not confirm(self, "Clear render cache", "Delete all cached renders? Previews will be re-rendered."):
            return
        root = cache_dir() / "renders"
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        clear_memory_caches()
        self.on_shown()
        self.ctx.toast("Render cache cleared.", "ok")

    def restore_presets(self) -> None:
        if confirm(self, "Restore built-in presets", "Undo all changes made to built-in presets? Your own presets are kept."):
            n = self.ctx.presets.restore_all()
            from ...core.presets.manager import KINDS
            for k in KINDS:
                self.ctx.presetsChanged.emit(k)
            self.ctx.toast(tr("{n} built-in preset(s) restored.", n=n), "ok")

    def _open(self, p: Path) -> None:
        if p.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
        else:
            self.ctx.toast(tr("Not found: {path}", path=str(p)), "warn")
