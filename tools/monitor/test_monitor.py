from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QPlainTextEdit,
    QProgressBar, QSplitter, QVBoxLayout, QWidget,
)

PY = sys.executable
STATUS = {
    "queued": ("·", "", "na fila"),
    "running": ("▶", "accent", "rodando"),
    "passed": ("✓", "ok", "passou"),
    "failed": ("✗", "error", "falhou"),
    "error": ("!", "error", "erro"),
    "skipped": ("–", "warn", "pulado"),
}


def apply_app_theme(app: QApplication) -> None:
    from voxagen import i18n
    from voxagen.models.app_settings import AppSettings
    from voxagen.paths import user_data_dir
    from voxagen.ui import theme
    from voxagen.models.app_settings import SettingsStore
    settings = AppSettings()
    if SettingsStore is not None:
        try:
            settings = SettingsStore(user_data_dir() / "settings.json").load()
        except Exception:
            pass
    theme.load_fonts()
    spec = settings.appearance.current
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
    app.setFont(theme.app_font(10))
    app.setPalette(theme.palette(t))
    app.setStyleSheet(theme.stylesheet(t))


class Monitor(QMainWindow):
    def __init__(self):
        super().__init__()
        from voxagen.ui.widgets.common import Badge, Card, button, hbox, hint, label
        self._Badge = Badge
        self.setWindowTitle("Voxa GEN · Testes")
        icon = ROOT / "assets" / "ui" / "logo.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(980, 720)

        root = QWidget()
        root.setObjectName("Panel")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(14)

        top = Card("Testes", "Roda a suíte inteira e mostra cada teste na hora em que termina.")
        self.pct = label("0 %", "SubTitle")
        self.pass_pct = hint("Aprovados: —")
        self.badges = {k: Badge("", STATUS[k][1]) for k in ("passed", "failed", "error", "skipped")}
        top.add(hbox(self.pct, self.pass_pct, None, *self.badges.values()))
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        top.add(self.bar)
        self.now = hint("Parado.")
        self.now.setObjectName("StatusText")
        top.add(self.now)
        self.b_run = button("Rodar testes", "play", "primary")
        self.b_fast = button("Só os rápidos", "play")
        self.b_stop = button("Parar", "stop")
        self.b_verify = button("Verificar", "check")
        self.b_stop.setEnabled(False)
        self.b_run.clicked.connect(lambda: self.start(False))
        self.b_fast.clicked.connect(lambda: self.start(True))
        self.b_stop.clicked.connect(self.stop)
        self.b_verify.clicked.connect(self.verify)
        top.add(hbox(self.b_run, self.b_fast, self.b_stop, None, self.b_verify))
        v.addWidget(top)

        split = QSplitter(Qt.Orientation.Horizontal)
        left = Card("Lista", "Clique num teste para ver o que aconteceu.")
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self.show_details)
        left.add(self.list)
        right = Card("Problemas", "O erro do teste escolhido, ou o resultado do verificador.")
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Nenhum problema encontrado até agora.")
        right.add(self.details)
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([520, 440])
        v.addWidget(split, 1)

        self.items: dict[str, QListWidgetItem] = {}
        self.texts: dict[str, str] = {}
        self.counts = dict.fromkeys(("passed", "failed", "error", "skipped"), 0)
        self.total = 0
        self.current = ""
        self.current_t0 = 0.0
        self.t0 = 0.0
        self.proc: QProcess | None = None
        self.events = Path(tempfile.gettempdir()) / f"voxagen-monitor-{os.getpid()}.jsonl"
        self.offset = 0
        self.timer = QTimer(self, interval=250, timeout=self.poll)
        self.verify_steps: list = []
        self._refresh()

    def start(self, fast: bool) -> None:
        if self.proc is not None:
            return
        self.list.clear()
        self.items.clear()
        self.texts.clear()
        self.details.clear()
        self.counts = dict.fromkeys(self.counts, 0)
        self.total = 0
        self.current = ""
        self.events.write_text("", "utf-8")
        self.offset = 0
        args = ["-m", "pytest", "tests", "-q", "-p", "no:cacheprovider", "-p", "pytest_live",
                "--basetemp", str(Path(tempfile.gettempdir()) / f"voxagen-monitor-tmp-{os.getpid()}")]
        if fast:
            args += ["--ignore", "tests/test_ui.py"]
        env = QProcessEnvironment.systemEnvironment()
        env.insert("VXMON_FILE", str(self.events))
        env.insert("QT_QPA_PLATFORM", "offscreen")
        env.insert("PYTHONPATH", str(Path(__file__).parent) + os.pathsep + env.value("PYTHONPATH", ""))
        self.proc = QProcess(self)
        self.proc.setProcessEnvironment(env)
        self.proc.setWorkingDirectory(str(ROOT))
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(lambda: self.proc and self.proc.readAllStandardOutput())
        self.proc.finished.connect(self.finished)
        self.proc.start(PY, args)
        self.t0 = time.perf_counter()
        self.timer.start()
        self._busy(True)
        self.now.setText("Procurando os testes…")

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.kill()

    def finished(self, code: int, _status) -> None:
        self.poll()
        self.timer.stop()
        self.proc = None
        self._busy(False)
        if self.current and self.current in self.items:
            self._set(self.current, "queued")
        self.current = ""
        mins = (time.perf_counter() - self.t0) / 60
        bad = self.counts["failed"] + self.counts["error"]
        done = sum(self.counts.values())
        if done < self.total:
            self._tone("warn", f"Interrompido: {done} de {self.total} testes rodaram ({mins:.1f} min).")
        elif bad:
            self._tone("error", f"Terminou com {bad} problema(s) em {mins:.1f} min. Clique nos ✗ da lista.")
        else:
            self._tone("ok", f"Tudo certo: {self.counts['passed']} testes passaram em {mins:.1f} min. "
                             "Agora rode o Verificar.")
        self._refresh()

    def poll(self) -> None:
        try:
            with open(self.events, encoding="utf-8") as f:
                f.seek(self.offset)
                chunk = f.read()
                self.offset = f.tell()
        except OSError:
            return
        for line in chunk.splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            ev = e.get("ev")
            if ev == "total":
                self.total = int(e["n"])
            elif ev == "start":
                self.current, self.current_t0 = e["id"], time.perf_counter()
                self._set(e["id"], "running")
            elif ev == "done":
                prev = self.items[e["id"]].data(Qt.ItemDataRole.UserRole) if e["id"] in self.items else None
                if prev in self.counts:
                    self.counts[prev] -= 1
                self.counts[e["outcome"]] = self.counts.get(e["outcome"], 0) + 1
                if e.get("text"):
                    self.texts[e["id"]] = e["text"]
                self._set(e["id"], e["outcome"], e.get("seconds"))
                if e["outcome"] in ("failed", "error") and not self.details.toPlainText():
                    self.details.setPlainText(f"{e['id']}\n\n{e['text']}")
        if self.current and self.proc is not None:
            secs = time.perf_counter() - self.current_t0
            self.now.setText(f"Rodando agora: {self.current}  ·  {secs:.0f} s")
        self._refresh()

    def _set(self, node: str, outcome: str, seconds=None) -> None:
        sym, _, words = STATUS.get(outcome, ("?", "", outcome))
        it = self.items.get(node)
        if it is None:
            it = QListWidgetItem()
            self.items[node] = it
            self.list.addItem(it)
        extra = f"  ·  {seconds:.1f} s" if seconds is not None else ""
        it.setText(f"{sym}  {node.replace('tests/', '')}{extra}")
        it.setToolTip(words)
        it.setData(Qt.ItemDataRole.UserRole, outcome)
        from voxagen.ui import theme
        t = theme.current()
        colour = {"passed": t.ok, "failed": t.error, "error": t.error, "skipped": t.warn,
                  "running": t.accent}.get(outcome)
        if colour:
            it.setForeground(theme.qcolor(colour))
        if outcome == "running":
            self.list.scrollToItem(it)

    def _refresh(self) -> None:
        done = sum(self.counts.values())
        pct = int(round(100 * done / self.total)) if self.total else 0
        self.pct.setText(f"{pct} %")
        self.bar.setMaximum(max(1, self.total))
        self.bar.setValue(done)
        ran = self.counts["passed"] + self.counts["failed"] + self.counts["error"]
        self.pass_pct.setText(f"Aprovados: {100 * self.counts['passed'] / ran:.0f} % dos {ran} que já rodaram"
                              if ran else "Aprovados: —")
        names = {"passed": ("passou", "passaram"), "failed": ("falhou", "falharam"),
                 "error": ("com erro", "com erro"), "skipped": ("pulado", "pulados")}
        for k, b in self.badges.items():
            b.setText(f"{self.counts[k]} {names[k][self.counts[k] != 1]}")
            b.setVisible(bool(self.counts[k]) or k == "passed")

    def show_details(self, item, _prev=None) -> None:
        if item is None:
            return
        node = next((k for k, v in self.items.items() if v is item), "")
        text = self.texts.get(node)
        if text:
            self.details.setPlainText(f"{node}\n\n{text}")

    def _tone(self, tone: str, text: str) -> None:
        self.now.setText(text)
        self.now.setProperty("tone", tone)
        self.now.style().unpolish(self.now)
        self.now.style().polish(self.now)

    def _busy(self, on: bool) -> None:
        self.b_run.setEnabled(not on)
        self.b_fast.setEnabled(not on)
        self.b_verify.setEnabled(not on)
        self.b_stop.setEnabled(on)
        if on:
            self._tone("", "Rodando…")

    def verify(self) -> None:
        if self.proc is not None:
            return
        report = Path(tempfile.gettempdir()) / f"voxagen-monitor-selftest-{os.getpid()}.json"
        self.verify_steps = [
            ("Traduções completas e sem erro de placeholder",
             ["-m", "pytest", "tests/test_i18n.py", "-q", "-p", "no:cacheprovider", "--basetemp",
              str(Path(tempfile.gettempdir()) / f"voxagen-monitor-i18n-{os.getpid()}")], None),
            ("Self-test do app (todos os modos + uma exportação)",
             [str(ROOT / "run.py"), "--selftest", str(report)], report),
        ]
        self.verify_log = ["VERIFICADOR", ""]
        self.details.setPlainText("\n".join(self.verify_log))
        self._busy(True)
        self._next_verify()

    def _next_verify(self) -> None:
        if not self.verify_steps:
            self._busy(False)
            bad = any(l.startswith("✗") for l in self.verify_log)
            self._tone("error" if bad else "ok", "Verificador: encontrou problemas." if bad
                       else "Verificador: tudo certo.")
            return
        name, args, report = self.verify_steps.pop(0)
        self._tone("", f"Verificando: {name}…")
        proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("QT_QPA_PLATFORM", "offscreen")
        proc.setProcessEnvironment(env)
        proc.setWorkingDirectory(str(ROOT))
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        def done(code, _s):
            out = bytes(proc.readAll()).decode("utf-8", "replace")
            ok = code == 0
            detail = ""
            if report is not None and report.exists():
                try:
                    ok = ok and bool(json.loads(report.read_text("utf-8")).get("ok"))
                except ValueError:
                    ok = False
            self.verify_log.append(f"{'✓' if ok else '✗'}  {name}" + (f"  ({detail})" if detail else ""))
            if not ok:
                self.verify_log.append(out[-2500:])
            self.details.setPlainText("\n".join(self.verify_log))
            proc.deleteLater()
            self._next_verify()

        proc.finished.connect(done)
        proc.start(PY, args)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_app_theme(app)
    w = Monitor()
    w.show()
    if "--run" in sys.argv:
        w.start("--fast" in sys.argv)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
