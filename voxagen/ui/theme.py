from __future__ import annotations

import re
from dataclasses import dataclass, replace

from PySide6.QtGui import QColor, QFont, QPalette


@dataclass(frozen=True)
class Tokens:
    name: str
    bg: str
    sidebar: str
    surface: str
    surface_alt: str
    raised: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_faint: str
    accent: str
    accent_text: str
    accent_soft: str
    processed: str
    ok: str
    warn: str
    error: str
    wave_bg: str
    key_white: str
    key_black: str
    panel: str = "#3b3b3b"
    nav: str = "#2c2c2c"
    nav_checked: str = "#3b3b3b"
    dots: str = "#2e2e2e"
    hover: str = "#4a4a4a"
    tab_selected: str = "#525252"
    input_border: str = "#ffffff"
    focus: str = "#ffa600"
    logo: str = ""


DARK = Tokens(
    name="dark", bg="#1e1e1e", sidebar="#1e1e1e", surface="#2c2c2c", surface_alt="#1e1e1e",
    raised="#3b3b3b", border="#3b3b3b", border_strong="#555555", text="#f5f5f5",
    text_muted="#bdbdbd", text_faint="#858585", accent="#ffa600", accent_text="#1e1e1e",
    accent_soft="#4d3a14", processed="#55c2d6", ok="#5cc98a", warn="#e8c25a", error="#ef6a5e",
    wave_bg="#1e1e1e", key_white="#e8e8e8", key_black="#2c2c2c",
    panel="#3b3b3b", nav="#2c2c2c", nav_checked="#3b3b3b", dots="#2e2e2e", hover="#4a4a4a",
    tab_selected="#525252", input_border="#ffffff",
)

LIGHT = Tokens(
    name="light", bg="#e4e4e4", sidebar="#ededed", surface="#e4e4e4", surface_alt="#ffffff",
    raised="#f7f7f7", border="#d4d4d4", border_strong="#b8b8b8", text="#1e1e1e",
    text_muted="#555555", text_faint="#8f8f8f", accent="#e08e00", accent_text="#1e1e1e",
    accent_soft="#fbe9c8", processed="#16879b", ok="#2f9a5d", warn="#b5870f", error="#c8443a",
    wave_bg="#ffffff", key_white="#ffffff", key_black="#2c2c2c",
    panel="#f7f7f7", nav="#e0e0e0", nav_checked="#f7f7f7", dots="#d2d2d2", hover="#ffffff",
    tab_selected="#cfcfcf", input_border="#1e1e1e",
)

LIGHT = replace(LIGHT, focus="#9a5a00")
THEMES = {"dark": DARK, "light": LIGHT}
FONT_FAMILY = "Inter"
FONT_FALLBACK = "Segoe UI"
TAB_FAMILY = "VCR OSD Mono"
RADIUS_CARD = 36
RADIUS_INPUT = 6
RADIUS_CONTROL = 8
RADIUS_ROUND = 15


def load_fonts() -> list[str]:
    from PySide6.QtGui import QFontDatabase
    from ..paths import assets_dir
    families = []
    for f in sorted((assets_dir() / "fonts").glob("*.ttf")):
        fid = QFontDatabase.addApplicationFont(str(f))
        if fid >= 0:
            families += QFontDatabase.applicationFontFamilies(fid)
    return sorted(set(families))


def tab_font(size_px: int = 16) -> QFont:
    f = QFont(TAB_FAMILY)
    if _look.cjk:
        f.setFamilies([TAB_FAMILY] + CJK_FALLBACKS)
    f.setPixelSize(max(8, int(round(size_px * _look.font_scale))))
    return f
MONO_FAMILY = "Cascadia Mono"
CJK_FALLBACKS = ["Yu Gothic UI", "Meiryo UI", "Meiryo", "MS UI Gothic", "Noto Sans JP"]


@dataclass(frozen=True)
class Look:
    font_family: str = FONT_FAMILY
    font_scale: float = 1.0
    radius_scale: float = 1.0
    density: str = "comfortable"
    card_style: str = "solid"
    icon_style: str = "hand"
    cjk: bool = False


DENSITY = {"compact": 0.72, "comfortable": 1.0, "spacious": 1.3}

_current: Tokens = DARK
_look: Look = Look()


def look() -> Look:
    return _look


def set_look(lk: Look) -> Look:
    global _look
    _look = lk
    return _look


def fs(pt: float) -> float:
    return pt * _look.font_scale


def rad(px: float) -> float:
    return px * _look.radius_scale


def pad(px: float) -> int:
    return int(round(px * DENSITY.get(_look.density, 1.0)))


def _rgb(h: str) -> tuple:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#" + "".join(f"{int(round(max(0.0, min(1.0, c)) * 255)):02x}" for c in rgb)


def valid_hex(h: str) -> bool:
    return bool(re.fullmatch(r"#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", h or ""))


def mix(a: str, b: str, t: float) -> str:
    ra, rb = _rgb(a), _rgb(b)
    return _hex([x + (y - x) * t for x, y in zip(ra, rb)])


def luminance(h: str) -> float:
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def readable_on(bg: str) -> str:
    return "#1e1e1e" if contrast("#1e1e1e", bg) >= contrast("#f5f5f5", bg) else "#f5f5f5"


def push_contrast(fg: str, bg: str, need: float) -> str:
    if contrast(fg, bg) >= need:
        return fg
    target = readable_on(bg)
    for i in range(1, 21):
        c = mix(fg, target, i / 20)
        if contrast(c, bg) >= need:
            return c
    return target


def build_tokens(base: str, colors: dict) -> Tokens:
    t = THEMES.get(base, DARK)
    c = {}
    for k, v in (colors or {}).items():
        if v and valid_hex(v):
            v = v if v.startswith("#") else "#" + v
            c[k] = _hex(_rgb(v))
    kw = {}
    if "background" in c:
        bg = c["background"]
        kw.update(bg=bg, sidebar=bg, surface_alt=bg, wave_bg=bg, dots=mix(bg, readable_on(bg), 0.07))
    if "panel" in c:
        kw.update(panel=c["panel"], nav_checked=c["panel"])
    if "cards" in c:
        kw.update(surface=c["cards"], nav=c["cards"])
    if "buttons" in c:
        b = c["buttons"]
        kw.update(raised=b, border=b, hover=mix(b, readable_on(b), 0.12), tab_selected=mix(b, readable_on(b), 0.1),
                  border_strong=mix(b, readable_on(b), 0.22))
    if "primary" in c:
        a = c["primary"]
        kw.update(accent=a, accent_text=readable_on(a))
    if "secondary" in c:
        kw.update(processed=c["secondary"])
    if "highlight" in c:
        kw.update(focus=c["highlight"])
    elif "primary" in c:
        kw.update(focus=c["primary"])
    if "logo" in c:
        kw.update(logo=c["logo"])
    t = replace(t, **kw)
    if "text" in c:
        tx = c["text"]
        t = replace(t, text=tx, input_border=tx, text_muted=mix(tx, t.surface, 0.25),
                    text_faint=mix(tx, t.surface, 0.48))
    if c:
        t = replace(t, accent_soft=mix(t.accent, t.surface, 0.72), name="custom-" + base + "-" +
                    "-".join(f"{k}{v}" for k, v in sorted(c.items())))
    return t


CONTRAST_RULES = [
    ("Text on cards", "text", "surface", 4.5),
    ("Text on the panel", "text", "panel", 4.5),
    ("Text on the background", "text", "bg", 4.5),
    ("Text on buttons", "text", "raised", 4.5),
    ("Secondary text on cards", "text_muted", "surface", 3.0),
    ("Text on primary buttons", "accent_text", "accent", 4.5),
    ("Highlight outline on cards", "focus", "surface", 3.0),
]


def contrast_issues(t: Tokens) -> list:
    out = []
    for name, fg, bg, need in CONTRAST_RULES:
        ratio = contrast(getattr(t, fg), getattr(t, bg))
        if ratio < need - 1e-6:
            out.append((name, ratio, need))
    return out


def fix_contrast(t: Tokens) -> Tokens:
    text = t.text
    for _ in range(3):
        for b in (t.surface, t.panel, t.bg, t.raised):
            text = push_contrast(text, b, 4.5)
    t = replace(t, text=text, input_border=text)
    return replace(t, text_muted=push_contrast(t.text_muted, t.surface, 3.0),
                   accent_text=push_contrast(t.accent_text, t.accent, 4.5),
                   focus=push_contrast(t.focus, t.surface, 3.0))


BUILTIN_THEMES = [
    ("Voxa Dark", "dark", {}),
    ("Voxa Light", "light", {}),
    ("Midnight Blue", "dark", {"background": "#0f1624", "panel": "#1b2638", "cards": "#141d2c", "buttons": "#24324a",
                               "primary": "#5aa9ff", "secondary": "#ffb35a", "highlight": "#8cc4ff", "text": "#eef3fb"}),
    ("Boyfriend Cyan", "dark", {"background": "#101a1f", "panel": "#1d2e36", "cards": "#16242b", "buttons": "#27404b",
                                "primary": "#31b0d1", "secondary": "#ff4fa3", "highlight": "#7fe3ff", "text": "#f1fbff"}),
    ("Girlfriend Pink", "dark", {"background": "#1f1018", "panel": "#3a1d2c", "cards": "#2a1520", "buttons": "#4a2638",
                                 "primary": "#ff5fa8", "secondary": "#7fd6ff", "highlight": "#ff9ccb", "text": "#fff1f7"}),
    ("Lemon Light", "light", {"background": "#f4f1e4", "panel": "#fffdf3", "cards": "#f1ecd7", "buttons": "#e6dfc2",
                              "primary": "#c9a100", "secondary": "#2c7fa3", "highlight": "#8a6d00", "text": "#262212"}),
    ("High Contrast", "dark", {"background": "#000000", "panel": "#121212", "cards": "#000000", "buttons": "#262626",
                               "primary": "#ffd400", "secondary": "#00e5ff", "highlight": "#ffffff", "text": "#ffffff"}),
]


def current() -> Tokens:
    return _current


def set_current(name_or_tokens) -> Tokens:
    global _current
    _current = name_or_tokens if isinstance(name_or_tokens, Tokens) else THEMES.get(name_or_tokens, DARK)
    return _current


def qcolor(hex_or_token: str, alpha: int | None = None) -> QColor:
    value = getattr(_current, hex_or_token, hex_or_token)
    c = QColor(value)
    if alpha is not None:
        c.setAlpha(alpha)
    return c


def app_font(size: float = 9.5) -> QFont:
    family = _look.font_family or FONT_FAMILY
    f = QFont(family)
    if not f.exactMatch():
        f = QFont(FONT_FALLBACK)
    fams = [f.family()] + ([] if f.family() == FONT_FALLBACK else [FONT_FALLBACK])
    if _look.cjk:
        fams += CJK_FALLBACKS
    f.setFamilies(fams)
    f.setPointSizeF(size * _look.font_scale)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def mono_font(size: float = 9.0) -> QFont:
    f = QFont(MONO_FAMILY)
    if not f.exactMatch():
        f = QFont("Consolas")
    f.setPointSizeF(size)
    return f


def palette(t: Tokens) -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(t.bg))
    p.setColor(QPalette.ColorRole.WindowText, QColor(t.text))
    p.setColor(QPalette.ColorRole.Base, QColor(t.surface_alt))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(t.surface))
    p.setColor(QPalette.ColorRole.Text, QColor(t.text))
    p.setColor(QPalette.ColorRole.Button, QColor(t.surface_alt))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(t.text))
    p.setColor(QPalette.ColorRole.Highlight, QColor(t.accent))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(t.accent_text))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(t.raised))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(t.text))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(t.text_faint))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(t.text_faint))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(t.text_faint))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(t.text_faint))
    return p


def arrow_files(t: Tokens) -> tuple[str, str]:
    from ..paths import cache_dir
    d = cache_dir() / "ui"
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for name, pts in (("up", "1,6 5,2 9,6"), ("down", "1,2 5,6 9,2")):
        p = d / f"{t.name}_{name}.svg"
        p.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="8" viewBox="0 0 10 8">'
                     f'<polyline points="{pts}" fill="none" stroke="{t.text_muted}" stroke-width="1.6" '
                     f'stroke-linecap="round" stroke-linejoin="round"/></svg>', "utf-8")
        out.append(p.as_posix())
    return out[0], out[1]


def stylesheet(t: Tokens, lk: Look | None = None) -> str:
    lk = lk or _look
    qss = _stylesheet(t, lk)
    fs_ = lk.font_scale
    qss = re.sub(r"(\d+(?:\.\d+)?)pt", lambda m: f"{float(m.group(1)) * fs_:.2f}pt", qss)
    rs = lk.radius_scale
    qss = re.sub(r"(border-radius|border-top-left-radius|border-top-right-radius): (\d+)px",
                 lambda m: f"{m.group(1)}: {int(round(int(m.group(2)) * rs))}px", qss)
    dn = DENSITY.get(lk.density, 1.0)
    if dn != 1.0:
        def _pad(m):
            vals = [f"{max(0, int(round(int(v) * dn)))}px" for v in re.findall(r"(\d+)px", m.group(1))]
            return "padding: " + " ".join(vals) + ";"
        qss = re.sub(r"padding: ((?:\d+px ?)+);", _pad, qss)
    if lk.card_style == "outlined":
        qss += f"\n#Card, #ExportBar {{ border: 1px solid {t.border_strong}; }}\n"
    return qss


def _stylesheet(t: Tokens, lk: Look) -> str:
    up, down = arrow_files(t)
    r = 8
    return f"""
* {{ outline: 0; }}
QWidget {{ color: {t.text}; font-size: 10.5pt; }}
QMainWindow {{ background: {t.bg}; }}
QToolTip {{ background: {t.nav}; color: {t.text}; border: 1px solid {t.border_strong}; padding: 6px 8px;
    border-radius: {r}px; }}

#Sidebar {{ background: {t.sidebar}; }}
#NavButton {{ background: {t.nav}; border: 1px solid {t.nav}; border-radius: {r}px; padding: 1px 5px;
             color: {t.text}; font-size: 12pt; min-height: 31px; max-height: 33px; }}
#NavButton:hover {{ background: {t.hover}; border-color: {t.hover}; }}
#NavButton:checked {{ background: {t.nav_checked}; border-color: {t.focus}; }}
#Version {{ color: {t.text}; font-size: 9pt; }}
#PageHost {{ background: transparent; }}

#PageTitle {{ font-size: 18pt; font-weight: 700; }}
#PageSubtitle {{ color: {t.text_muted}; font-size: 10.5pt; }}
#Card {{ background: {t.surface}; border: none; border-radius: {RADIUS_CARD}px; }}
#ExportBar {{ background: {t.surface}; border: none; border-radius: 20px; }}
#CardTitle {{ font-weight: 500; font-size: 12pt; letter-spacing: 0.5px; }}
#CardExplain {{ color: {t.text}; font-size: 9.5pt; }}
#SubTitle {{ font-weight: 600; font-size: 11pt; }}
#CardHint, #Hint {{ color: {t.text_muted}; font-size: 9.5pt; }}
#Faint {{ color: {t.text_faint}; }}
#Mono {{ font-family: "{MONO_FAMILY}", Consolas; }}
#Divider {{ background: {t.border}; max-height: 1px; min-height: 1px; }}
#Badge {{ border-radius: 6px; padding: 3px 9px; font-size: 9pt; background: {t.raised};
         color: {t.text_muted}; border: 1px solid {t.raised}; }}
#Badge[tone="accent"] {{ color: {t.accent}; border-color: {t.accent}; }}
#Badge[tone="ok"] {{ color: {t.ok}; border-color: {t.ok}; }}
#Badge[tone="warn"] {{ color: {t.warn}; border-color: {t.warn}; }}
#Badge[tone="error"] {{ color: {t.error}; border-color: {t.error}; }}
#Badge[tone="processed"] {{ color: {t.processed}; border-color: {t.processed}; }}
#StatusText[tone="error"] {{ color: {t.error}; }}
#StatusText[tone="warn"] {{ color: {t.warn}; }}
#StatusText[tone="ok"] {{ color: {t.ok}; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {t.surface_alt}; border: 1px solid {t.input_border}; border-radius: {RADIUS_INPUT}px;
    padding: 5px 9px; selection-background-color: {t.accent}; selection-color: {t.accent_text};
    min-height: 20px; }}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: {t.focus}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border-color: {t.focus}; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{ color: {t.text_faint}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url("{down}"); width: 10px; height: 8px; margin-right: 6px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {{
    border: none; background: transparent; width: 18px; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{up}"); width: 9px; height: 7px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{down}"); width: 9px; height: 7px; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::down-button:hover {{ background: {t.raised}; border-radius: 4px; }}
QComboBox QAbstractItemView {{ background: {t.nav}; border: 1px solid {t.border_strong}; border-radius: {r}px;
    selection-background-color: {t.raised}; selection-color: {t.text}; padding: 4px; outline: 0; }}

QPushButton {{ background: {t.raised}; border: 1px solid {t.raised}; border-radius: {r}px;
    padding: 6px 14px; min-height: 20px; color: {t.text}; }}
#PageHeader QPushButton, #PageHeader QToolButton, #PanelBar QPushButton, #PanelBar QToolButton {{
    background: {t.nav}; border-color: {t.nav}; }}
#PageHeader QPushButton:hover, #PageHeader QToolButton:hover, #PanelBar QPushButton:hover,
#PanelBar QToolButton:hover {{ background: {t.hover}; border-color: {t.hover}; }}
QPushButton:hover {{ background: {t.hover}; border-color: {t.hover}; }}
QPushButton:pressed {{ background: {t.surface_alt}; }}
QPushButton:disabled {{ color: {t.text_faint}; background: {t.surface}; border-color: {t.surface}; }}
QPushButton:checked {{ background: {t.raised}; border-color: {t.focus}; }}
QPushButton#Primary {{ background: {t.accent}; color: {t.accent_text}; border: 1px solid {t.accent}; font-weight: 700; }}
QPushButton#Primary:hover {{ background: {t.accent}; border-color: {t.text}; }}
QPushButton#Primary:disabled {{ background: {t.accent_soft}; color: {t.text_faint}; border-color: {t.accent_soft}; }}
QPushButton#Danger {{ color: {t.error}; }}
QPushButton#Ghost, QToolButton#Ghost {{ background: transparent; border: 1px solid transparent; }}
QPushButton#Ghost:hover, QToolButton#Ghost:hover {{ background: {t.raised}; }}
QToolButton {{ background: {t.raised}; border: 1px solid {t.raised}; border-radius: {r}px; padding: 5px; }}
QToolButton:hover {{ background: {t.hover}; border-color: {t.hover}; }}
QToolButton:checked {{ border-color: {t.focus}; }}
QToolButton:disabled {{ background: {t.surface}; border-color: {t.surface}; }}

#Help {{ background: {t.raised}; color: {t.text_muted}; border: 1px solid {t.raised}; border-radius: 10px;
    min-width: 20px; max-width: 20px; min-height: 20px; max-height: 20px; padding: 0; font-weight: 700; font-size: 9pt; }}
#Help:hover {{ background: {t.accent}; color: {t.accent_text}; border-color: {t.accent}; }}
#HelpPopup {{ background: {t.nav}; border: 1px solid {t.border_strong}; border-radius: 12px; }}
#HelpTitle {{ font-weight: 600; font-size: 11pt; }}
#HelpBody {{ color: {t.text_muted}; font-size: 10pt; }}
#HelpTip {{ color: {t.accent}; font-size: 9.5pt; }}
#HelpSection {{ color: {t.accent}; font-weight: 700; font-size: 8.5pt; letter-spacing: 1px; }}
#HelpWhy {{ color: {t.text}; font-size: 10pt; }}
#HelpClose {{ background: transparent; color: {t.text_muted}; border: none; border-radius: 10px;
    min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; padding: 0; font-size: 13pt; }}
#HelpClose:hover {{ background: {t.hover}; color: {t.text}; }}
#RoundButton {{ background: {t.raised}; border: 1px solid {t.raised}; border-radius: {RADIUS_ROUND}px;
    min-width: 29px; max-width: 29px; min-height: 29px; max-height: 29px; padding: 0; }}
#RoundButton:hover {{ background: {t.hover}; border-color: {t.hover}; }}
#Choice {{ background: {t.raised}; border: 1px solid {t.raised}; border-radius: 14px; text-align: left; padding: 0; }}
#Choice:hover {{ background: {t.hover}; border-color: {t.hover}; }}
#Choice:checked {{ background: {t.raised}; border: 2px solid {t.focus}; }}
#ChoiceTitle {{ font-weight: 600; font-size: 11pt; background: transparent; }}
#ChoiceText {{ color: {t.text_muted}; font-size: 9.5pt; background: transparent; }}
#FoldHeader {{ background: {t.surface_alt}; border: 1px solid {t.surface_alt}; border-radius: 10px;
    text-align: left; padding: 8px 12px; font-weight: 600; }}
#FoldHeader:hover {{ border-color: {t.border_strong}; }}
#FoldHeader:checked {{ border-color: {t.focus}; }}
#MoreButton {{ background: {t.raised}; border: 1px solid {t.raised}; border-radius: {r}px; padding: 6px 12px; }}
#MoreButton::menu-indicator {{ image: url("{down}"); subcontrol-position: right center; subcontrol-origin: padding;
    width: 10px; height: 8px; right: 8px; }}
#MoreButton {{ padding-right: 26px; }}
#NotifyTitle {{ font-size: 12pt; font-weight: 600; background: transparent; }}
#NotifyBody {{ font-size: 12pt; background: transparent; }}
#NotifyButton {{ background: {t.nav}; border: 1px solid {t.nav}; border-radius: {r}px; padding: 7px 22px; }}
#NotifyButton:hover {{ background: {t.hover}; border-color: {t.hover}; }}
#NotifyClose {{ background: transparent; border: none; border-radius: {r}px; }}
#NotifyClose:hover {{ background: {t.raised}; }}
#Segmented {{ background: {t.surface_alt}; border: none; border-radius: {r + 2}px; }}
#Segmented QPushButton {{ border: 1px solid transparent; border-radius: {r}px; padding: 5px 12px;
    background: transparent; color: {t.text_muted}; }}
#Segmented QPushButton:hover {{ color: {t.text}; background: {t.surface}; }}
#Segmented QPushButton:checked {{ background: {t.raised}; color: {t.text}; border-color: {t.focus}; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: 1px solid {t.border_strong};
    background: {t.surface_alt}; }}
QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; }}
QCheckBox::indicator:disabled {{ background: {t.surface}; }}

QSlider::groove:horizontal {{ height: 6px; background: {t.surface_alt}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 3px; }}
QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
    background: {t.text}; border: 2px solid {t.surface}; }}
QSlider::sub-page:horizontal:disabled {{ background: {t.border_strong}; }}

QProgressBar {{ background: {t.surface_alt}; border: none; border-radius: 5px;
    height: 10px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {t.accent}; border-radius: 5px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.surface}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t.hover}; }}
QScrollBar:horizontal {{ height: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t.surface}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; width: 0; height: 0; }}

QTableView, QTreeView, QListView, QListWidget {{ background: {t.surface_alt}; border: none;
    border-radius: {r + 2}px; alternate-background-color: {t.surface}; gridline-color: {t.border};
    selection-background-color: {t.raised}; selection-color: {t.text}; padding: 4px; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {t.surface_alt}; color: {t.text_muted}; border: none;
    padding: 6px 8px; font-size: 9.5pt; font-weight: 600; }}
QTableView::item, QTreeView::item {{ padding: 4px 6px; }}
QListView::item {{ padding: 6px 8px; border-radius: 6px; }}
QListView::item:selected, QTableView::item:selected, QTreeView::item:selected {{
    background: {t.raised}; color: {t.text}; }}
QListView::item:hover {{ background: {t.surface}; }}
#Swatch {{ border: 1px solid {t.border_strong}; border-radius: 6px; }}

QTabWidget::pane {{ border: none; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{ background: {t.surface_alt}; color: {t.text_muted}; padding: 7px 16px; margin-right: 6px;
    margin-bottom: 6px; border: 1px solid {t.surface_alt}; border-radius: {r}px; }}
QTabBar::tab:selected {{ background: {t.raised}; color: {t.text}; border-color: {t.focus}; }}
QTabBar::tab:hover {{ color: {t.text}; }}

QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 16px; }}
QMenu {{ background: {t.nav}; border: 1px solid {t.border_strong}; border-radius: {r}px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t.raised}; }}
QStatusBar {{ background: {t.sidebar}; color: {t.text_muted}; border: none; }}
QDialog {{ background: {t.panel}; }}
QMessageBox {{ background: {t.panel}; }}

#DropZone {{ border: 1px dashed {t.border_strong}; border-radius: {r + 2}px; background: {t.surface_alt}; }}
#DropZone[active="true"] {{ border-color: {t.accent}; background: {t.accent_soft}; }}
#Chip {{ background: {t.raised}; border: none; border-radius: {r}px; }}
"""
