from __future__ import annotations

import copy

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QColorDialog, QFontComboBox, QGridLayout, QInputDialog, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QSlider,
)

from ...i18n import tr
from ...models.app_settings import ThemeSpec
from .. import theme
from ..widgets.common import (
    Card, FormGrid, HelpButton, Segmented, button, confirm, elastic, hbox, hint, label, set_tone,
)
from .base import Page

COLOR_ROWS = [
    ("primary", "Primary colour", "Main buttons (like Export), sliders, progress bars and the original (A) waveform."),
    ("secondary", "Secondary colour", "The processed (B) sound in previews, and secondary badges."),
    ("highlight", "Highlight colour", "Outlines of the selected tab, choice, field or menu entry, and keyboard focus."),
    ("background", "Background", "Behind everything: the sidebar, the dotted area and input fields."),
    ("panel", "Panels", "The large rounded panel that holds each page, and the folder tabs."),
    ("cards", "Cards", "The rounded cards inside the panel, and the sidebar buttons."),
    ("buttons", "Buttons", "Normal buttons and controls. Hover and border shades are derived from it."),
    ("text", "Text", "All text. Lighter and fainter text shades are derived from it."),
    ("logo", "Logo colour", "Recolours the Voxa GEN logo. Leave it empty for the original colours."),
]
TOKEN_OF = {"primary": "accent", "secondary": "processed", "highlight": "focus", "background": "bg", "panel": "panel",
            "cards": "surface", "buttons": "raised", "text": "text", "logo": "logo"}


class Swatch(QPushButton):
    def __init__(self):
        super().__init__()
        self.setObjectName("Swatch")
        self.setFixedSize(46, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_color(self, hex_: str) -> None:
        if hex_:
            self.setStyleSheet(f"#Swatch {{ background: {hex_}; }}")
            self.setText("")
        else:
            self.setStyleSheet("")
            self.setText("—")


class AppearancePage(Page):
    page_id = "appearance"
    title = "Appearance"
    subtitle = "Colours, font and sizes of the whole app"
    icon = "palette"
    tabs = ["Themes", "Colours", "Text & layout"]
    show_title = False

    def __init__(self, ctx):
        super().__init__(ctx)
        self._loading = False
        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(120)
        self._apply_timer.timeout.connect(self._apply_now)
        self.add_tab(self.columns([self._themes_card()], [self._check_card()]))
        self.add_tab(self.columns([self._colors_card()], [self._check_card2()]))
        self.add_tab(self.columns([self._text_card()], [self._layout_card()]))
        self.root.addWidget(self.tab_stack, 1)
        ctx.themeChanged.connect(lambda _: self._refresh_checks())
        ctx.languageChanged.connect(lambda _: self.load())
        self.load()

    @property
    def spec(self) -> ThemeSpec:
        return self.ctx.settings.appearance.current

    def _themes_card(self) -> Card:
        c = Card("Themes", 'Pick a starting theme. Changes hit the whole app right away. Save to keep them as your own theme.')
        self.themes = QListWidget()
        self.themes.setMinimumHeight(260)
        from PySide6.QtCore import QSize
        self.themes.setIconSize(QSize(64, 16))
        self.themes.itemDoubleClicked.connect(lambda _: self.apply_selected())
        c.add(self.themes)
        b_apply = button("Use theme", "check", "Primary")
        b_apply.clicked.connect(self.apply_selected)
        b_save = button("Save current as…", "save")
        b_save.setToolTip("Keep the current colours, font and sizes as a theme of your own")
        b_save.clicked.connect(self.save_as)
        self.b_delete = button("Delete", "trash")
        self.b_delete.clicked.connect(self.delete_saved)
        c.add(hbox(b_apply, b_save, None, self.b_delete))
        self.themes.currentRowChanged.connect(lambda _: self._theme_selected())
        self.base = Segmented([("dark", "Dark"), ("light", "Light")], self.spec.base)
        self.base.changed.connect(self._set_base)
        g = FormGrid()
        g.row("Base", hbox(self.base, None),
              "Light or dark defaults for every colour you have not changed. Switching it resets the colours to "
              "that base; your font and size settings stay.")
        c.add(g)
        return c

    def _theme_entries(self) -> list[ThemeSpec]:
        out = [ThemeSpec(name, base, dict(colors)) for name, base, colors in theme.BUILTIN_THEMES]
        return out + [copy.deepcopy(t) for t in self.ctx.settings.appearance.saved]

    def _fill_themes(self) -> None:
        cur = self.spec.name
        self.themes.blockSignals(True)
        self.themes.clear()
        builtin = {n for n, _, _ in theme.BUILTIN_THEMES}
        for t in self._theme_entries():
            tok = theme.build_tokens(t.base, t.colors)
            tag = tr("built-in") if t.name in builtin else tr("yours")
            it = QListWidgetItem(f"{tr(t.name)}   ·   {tag}")
            it.setData(Qt.ItemDataRole.UserRole, t.name)
            it.setData(Qt.ItemDataRole.DecorationRole, _swatch_icon([tok.accent, tok.processed, tok.surface, tok.bg]))
            self.themes.addItem(it)
            if t.name == cur:
                self.themes.setCurrentItem(it)
        self.themes.blockSignals(False)
        self.themes.setProperty("i18n_skip", True)
        self._theme_selected()

    def _selected_theme(self) -> ThemeSpec | None:
        it = self.themes.currentItem()
        if it is None:
            return None
        name = it.data(Qt.ItemDataRole.UserRole)
        return next((t for t in self._theme_entries() if t.name == name), None)

    def _theme_selected(self) -> None:
        t = self._selected_theme()
        builtin = {n for n, _, _ in theme.BUILTIN_THEMES}
        self.b_delete.setEnabled(t is not None and t.name not in builtin)

    def apply_selected(self) -> None:
        t = self._selected_theme()
        if t is None:
            return
        self.ctx.settings.appearance.current = copy.deepcopy(t)
        self.ctx.sound("confirm")
        self._apply_now()
        self.load()

    def save_as(self) -> None:
        name, ok = QInputDialog.getText(self, tr("Save theme"), tr("Theme name:"), text=tr("My theme"))
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in {n for n, _, _ in theme.BUILTIN_THEMES}:
            return self.ctx.toast("Built-in themes cannot be replaced; choose another name.", "warn")
        saved = self.ctx.settings.appearance.saved
        existing = next((t for t in saved if t.name == name), None)
        if existing and not confirm(self, tr("Replace theme"), tr("Replace your theme “{name}”?", name=name)):
            return
        spec = copy.deepcopy(self.spec)
        spec.name = name
        if existing:
            saved[saved.index(existing)] = spec
        else:
            saved.append(spec)
        self.spec.name = name
        self.ctx.save_soon()
        self._fill_themes()
        self.ctx.toast(tr("Theme “{name}” saved.", name=name), "ok")

    def delete_saved(self) -> None:
        t = self._selected_theme()
        if t is None or t.name in {n for n, _, _ in theme.BUILTIN_THEMES}:
            return
        if confirm(self, tr("Delete theme"), tr("Delete your theme “{name}”?", name=t.name), tr("Delete"), danger=True):
            saved = self.ctx.settings.appearance.saved
            self.ctx.settings.appearance.saved = [x for x in saved if x.name != t.name]
            self.ctx.save_soon()
            self._fill_themes()

    def _set_base(self, base: str) -> None:
        if self._loading:
            return
        self.spec.base = base
        self.spec.colors = {}
        self.spec.name = "Custom"
        self._changed()
        self.load()

    def _colors_card(self) -> Card:
        c = Card("Colours", "Click a swatch to pick a colour, or type a hex code like #FFA600. Clear a field to go back to the theme's colour. Hover, border and faint-text shades follow along.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(0, 1)
        self.color_rows: dict[str, tuple] = {}
        for r, (key, name, explain) in enumerate(COLOR_ROWS):
            sw = Swatch()
            edit = QLineEdit()
            edit.setPlaceholderText(tr("theme default"))
            edit.setMaximumWidth(110)
            reset = button("Reset", "reset")
            sw.clicked.connect(lambda _=False, k=key: self.pick(k))
            edit.editingFinished.connect(lambda k=key, e=edit: self._typed(k, e.text()))
            reset.clicked.connect(lambda _=False, k=key: self._set_color(k, ""))
            grid.addWidget(label(name), r, 0)
            grid.addWidget(sw, r, 1)
            grid.addWidget(edit, r, 2)
            grid.addWidget(reset, r, 3)
            grid.addWidget(HelpButton(name, explain), r, 4)
            self.color_rows[key] = (sw, edit)
        c.add(grid)
        return c

    def pick(self, key: str) -> None:
        cur = self.spec.colors.get(key) or getattr(theme.current(), TOKEN_OF[key]) or "#ffa600"
        col = QColorDialog.getColor(QColor(cur), self, tr("Choose a colour"))
        if col.isValid():
            self._set_color(key, col.name())

    def _typed(self, key: str, text: str) -> None:
        text = text.strip()
        if text and not theme.valid_hex(text):
            self.ctx.toast(tr("“{text}” is not a colour. Use a hex code like #FFA600.", text=text), "warn")
            return self.load()
        self._set_color(key, ("#" + text.lstrip("#")) if text else "")

    def _set_color(self, key: str, value: str) -> None:
        if self._loading:
            return
        if value:
            self.spec.colors[key] = value.lower()
        else:
            self.spec.colors.pop(key, None)
        if not self.spec.name.endswith("*"):
            self.spec.name = self.spec.name + " *"
        self._changed()
        self.load()

    def _check_card(self) -> Card:
        c = Card("Readability", 'Voxa GEN checks that text stays readable on every surface. When a combination is too weak, it fixes the text colour for you.')
        self.check_text = elastic(label("", "StatusText"))
        c.add(self.check_text)
        return c

    def _check_card2(self) -> Card:
        c = Card("Readability check", "Contrast of the colours you picked (WCAG). Text needs at least 4.5:1, "
                                      "outlines and secondary text 3:1.")
        self.check_text2 = elastic(label("", "StatusText"))
        c.add(self.check_text2)
        self.check_detail = elastic(hint(""))
        c.add(self.check_detail)
        return c

    def _refresh_checks(self) -> None:
        raw = theme.build_tokens(self.spec.base, self.spec.colors)
        issues = theme.contrast_issues(raw)
        if not issues:
            text, tone = tr("All text and outlines are easy to read."), "ok"
            detail = ""
        else:
            text = tr("{n} combinations were too weak and were adjusted automatically.", n=len(issues))
            tone = "warn"
            detail = "\n".join(tr("{what}: {ratio}:1 (needs {need}:1)", what=tr(n), ratio=f"{r:.1f}", need=f"{need:g}")
                               for n, r, need in issues)
        for w in (self.check_text, self.check_text2):
            w.setText(text)
            set_tone(w, tone)
            w.setProperty("i18n_text_skip", True)
        self.check_detail.setText(detail)
        self.check_detail.setProperty("i18n_text_skip", True)

    def _text_card(self) -> Card:
        c = Card("Text", "The font and size of every text in the app. The folder tabs keep their pixel font.")
        g = FormGrid()
        self.font = QFontComboBox()
        self.font.setFontFilters(QFontComboBox.FontFilter.ScalableFonts)
        self.font.currentFontChanged.connect(self._font)
        b_font_reset = button("Inter", "reset")
        b_font_reset.setToolTip("Back to the default font (Inter)")
        from PySide6.QtWidgets import QSizePolicy
        b_font_reset.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        b_font_reset.clicked.connect(lambda: self.font.setCurrentFont(QFont(theme.FONT_FAMILY)))
        g.row("Font", hbox(self.font, b_font_reset), "Any font installed on this computer. Inter is the default; "
                                                     "simple sans-serif fonts are the easiest to read.")
        self.size = QSlider(Qt.Orientation.Horizontal)
        self.size.setRange(85, 135)
        self.size.setSingleStep(5)
        self.size.setPageStep(5)
        self.size_label = label("", "Mono")
        self.size.valueChanged.connect(self._size)
        g.row("Text size", hbox(self.size, self.size_label),
              "Makes every text bigger or smaller (85-135 %). Layouts adapt; very large text may need a "
              "bigger window.", "Default: 100 %.")
        c.add(g)
        return c

    def _layout_card(self) -> Card:
        c = Card("Shapes and spacing", "How round the corners are, how much room the controls get, and the style "
                                       "of the panels and icons.")
        g = FormGrid()
        self.radius = QSlider(Qt.Orientation.Horizontal)
        self.radius.setRange(0, 150)
        self.radius.setSingleStep(10)
        self.radius_label = label("", "Mono")
        self.radius.valueChanged.connect(self._radius)
        g.row("Roundness", hbox(self.radius, self.radius_label),
              "0 % gives square corners, 100 % is the design, 150 % is extra round.")
        self.density = Segmented([("compact", "Compact"), ("comfortable", "Comfortable"), ("spacious", "Spacious")])
        self.density.changed.connect(lambda v: self._set("density", v))
        g.row("Density", hbox(self.density, None),
              "The room inside buttons, fields and cards. Compact fits more on small screens.")
        self.cards = Segmented([("solid", "Solid"), ("outlined", "Outlined")])
        self.cards.changed.connect(lambda v: self._set("card_style", v))
        g.row("Cards", hbox(self.cards, None), "Solid cards are filled blocks; outlined cards also get a thin border, "
                                               "which helps on very dark or very light themes.")
        self.icons = Segmented([("hand", "Hand-drawn"), ("line", "Thin lines"), ("bold", "Bold lines")])
        self.icons.changed.connect(lambda v: self._set("icon_style", v))
        g.row("Icons", hbox(self.icons, None), "Hand-drawn uses the design's artwork in the sidebar; the line styles "
                                               "use simple icons everywhere.")
        c.add(g)
        b_reset = button("Reset text and layout", "reset")
        b_reset.clicked.connect(self.reset_layout)
        c.add(hbox(None, b_reset))
        return c

    def _font(self, f: QFont) -> None:
        self._set("font_family", f.family())

    def _size(self, v: int) -> None:
        v = int(round(v / 5.0) * 5)
        self.size_label.setText(f"{v} %")
        self._set("font_scale", v / 100.0)

    def _radius(self, v: int) -> None:
        self.radius_label.setText(f"{v} %")
        self._set("radius_scale", v / 100.0)

    def _set(self, attr: str, value) -> None:
        if self._loading:
            return
        if getattr(self.spec, attr) == value:
            return
        setattr(self.spec, attr, value)
        self._changed()

    def reset_layout(self) -> None:
        d = ThemeSpec()
        for attr in ("font_family", "font_scale", "radius_scale", "density", "card_style", "icon_style"):
            setattr(self.spec, attr, getattr(d, attr))
        self._changed()
        self.load()

    def _changed(self) -> None:
        self._apply_timer.start()

    def _apply_now(self) -> None:
        self.ctx.apply_theme()

    def load(self) -> None:
        self._loading = True
        sp = self.spec
        self.base.set_value(sp.base, emit=False)
        tok = theme.current()
        for key, (sw, edit) in self.color_rows.items():
            val = sp.colors.get(key, "")
            shown = val or getattr(tok, TOKEN_OF[key], "")
            sw.set_color(shown)
            edit.setText(val)
        self.font.blockSignals(True)
        self.font.setCurrentFont(QFont(sp.font_family or theme.FONT_FAMILY))
        self.font.blockSignals(False)
        self.size.setValue(int(round(sp.font_scale * 100)))
        self.size_label.setText(f"{int(round(sp.font_scale * 100))} %")
        self.radius.setValue(int(round(sp.radius_scale * 100)))
        self.radius_label.setText(f"{int(round(sp.radius_scale * 100))} %")
        self.density.set_value(sp.density, emit=False)
        self.cards.set_value(sp.card_style, emit=False)
        self.icons.set_value(sp.icon_style, emit=False)
        self._loading = False
        self._fill_themes()
        self._refresh_checks()

    def on_shown(self) -> None:
        self.load()


def _swatch_icon(colors: list[str]):
    from PySide6.QtGui import QIcon, QPainter, QPixmap
    pm = QPixmap(64, 16)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    for i, c in enumerate(colors):
        p.setBrush(QColor(c))
        p.setPen(QColor(0, 0, 0, 60))
        p.drawRoundedRect(i * 16 + 1, 1, 14, 14, 4, 4)
    p.end()
    return QIcon(pm)
