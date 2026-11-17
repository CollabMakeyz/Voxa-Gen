import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from voxagen.core.effects import registry
from voxagen.ui.help_why import WHY
from voxagen.ui.widgets.common import HelpButton, HelpPopup

app = QApplication.instance() or QApplication([])

from voxagen import i18n

i18n.set_language("en")


def _effect_helps():
    out = []
    for obj in vars(registry).values():
        if isinstance(obj, dict):
            for e in obj.values():
                if hasattr(e, "help") and hasattr(e, "params"):
                    out.append(e.help)
                    out += [p.help for p in e.params if getattr(p, "help", "")]
    return out


def test_every_help_text_has_a_why():
    from voxagen.ui.context import AppContext
    from voxagen.ui.main_window import MainWindow
    ctx = AppContext(app)
    win = MainWindow(ctx)
    helps = [b.help_text for b in win.findChildren(HelpButton)] + _effect_helps()
    assert helps
    missing = sorted({h[:60] for h in helps if h not in WHY})
    assert not missing, missing
    win.close()
    win.deleteLater()
    ctx.deleteLater() if hasattr(ctx, "deleteLater") else None
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_popup_stays_open_until_closed():
    i18n.set_language("en")
    b = HelpButton("Tuning (A4)", "The pitch every note is tuned against. Almost all music uses 440 Hz.")
    b.show_help()
    pop = HelpPopup.current
    assert pop is not None and pop.isVisible()
    assert pop.windowType() == Qt.WindowType.Tool
    texts = [lb.text() for lb in pop.findChildren(QLabel)]
    assert WHY[b.help_text] in texts
    app.processEvents()
    assert pop.isVisible()
    b.show_help()
    assert HelpPopup.current is not pop
    HelpPopup.current.close()
    assert HelpPopup.current is None
