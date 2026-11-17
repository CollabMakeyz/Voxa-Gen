from __future__ import annotations

import logging
import sys
import traceback
import warnings

warnings.filterwarnings("ignore", message=".*pkg_resources.*")


def _excepthook(exc_type, exc, tb):
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    logging.getLogger("voxagen").error(text)
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance():
            box = QMessageBox(QMessageBox.Icon.Critical, "Unexpected error", str(exc) or exc_type.__name__)
            box.setDetailedText(text)
            box.exec()
    except Exception:
        pass


def selftest(report_path: str) -> int:
    import json
    import tempfile
    from pathlib import Path

    import numpy as np
    import soundfile as sf

    report = {"ok": False, "steps": []}
    try:
        from .core.audio.engines import get_engine
        from .core.export.exporter import export_chromatic
        from .core.notifications.ui_sounds import builtin_sounds
        from .core.pitch.detect import median_f0
        from .core.pitch.tuning import cents_between
        from .core.samples.library import SampleLibrary
        from .models.config import GeneratorConfig

        sr = 48000
        t = np.arange(int(sr * 0.5)) / sr
        x = sum(np.sin(2 * np.pi * 220 * k * t) / k for k in range(1, 30)) * 0.3
        cfg = GeneratorConfig()
        for mode in ("natural", "robot", "legacy"):
            eng = get_engine(mode, cfg)
            out = eng.render(eng.analyze(x[:, None], sr), x[:, None], sr, 330.0)
            err = cents_between(median_f0(out.audio, out.sr), 330.0)
            report["steps"].append({"engine": mode, "cents_error": round(err, 3)})
            assert abs(err) < 5, f"{mode} pitch error {err}"
        tmp = Path(tempfile.mkdtemp(prefix="voxagen_selftest_"))
        sf.write(tmp / "a.wav", x, sr)
        lib = SampleLibrary()
        lib.add_files([tmp / "a.wav"])
        cfg.musical.semitones = 4
        res = export_chromatic(cfg, lib, tmp / "export")
        report["steps"].append({"export_valid": res.validation.ok, "files": len(res.notes) + 1})
        assert res.validation.ok
        report["steps"].append({"builtin_sounds": len(builtin_sounds())})
        assert len(builtin_sounds()) == 17
        from .core.effects import EFFECTS, FxContext
        from . import i18n
        for k, e in EFFECTS.items():
            y = e.process(x[:24000, None], sr, e.resolve({}), FxContext(220.0, 1, 0))
            assert y.shape == (24000, 1) and np.isfinite(y).all() and not np.allclose(y, x[:24000, None]), k
        report["steps"].append({"effects": len(EFFECTS)})
        for code in i18n.LANGUAGES:
            i18n.set_language(code)
            assert code == "en" or i18n.translate("Export complete") != "Export complete", code
        i18n.set_language("en")
        report["steps"].append({"languages": len(i18n.LANGUAGES)})
        report["ok"] = True
    except Exception as exc:
        report["error"] = f"{exc.__class__.__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
    Path(report_path).write_text(json.dumps(report, indent=2), "utf-8")
    return 0 if report["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv)
    if "--selftest" in args:
        i = args.index("--selftest")
        return selftest(args[i + 1] if i + 1 < len(args) else "voxagen_selftest.json")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from . import APP_ID, APP_NAME
    from .paths import user_data_dir

    logging.basicConfig(filename=str(user_data_dir() / "voxagen.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    sys.excepthook = _excepthook
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_ID}.app")
        except Exception:
            pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ID)
    app.setStyle("Fusion")

    from .ui import theme
    from .ui.context import AppContext
    from .ui.main_window import MainWindow

    theme.load_fonts()
    app.setFont(theme.app_font(10))
    ctx = AppContext(app)
    ctx.apply_theme()
    try:
        ctx.reload_session_samples()
    except Exception as exc:
        logging.getLogger("voxagen").warning("could not restore samples: %s", exc)
    win = MainWindow(ctx)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
