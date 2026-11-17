from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget

from ...core.preview.player import PreviewPlayer
from .. import icons
from .common import fmt_time, tool_button


class TransportBar(QWidget):
    prevRequested = Signal()
    nextRequested = Signal()
    restartRequested = Signal()

    def __init__(self, player: PreviewPlayer, ctx=None, prev_next: bool = False, restart: bool = True):
        super().__init__()
        self.player = player
        self.ctx = ctx
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.btn_prev = tool_button("prev", "Previous note") if prev_next else None
        self.btn_play = tool_button("play", "Play / pause", size=20)
        self.btn_stop = tool_button("stop", "Stop")
        self.btn_restart = tool_button("restart", "Restart from the beginning") if restart else None
        self.btn_next = tool_button("next", "Next note") if prev_next else None
        self.btn_loop = tool_button("loop", "Loop", checkable=True)
        for b in (self.btn_prev, self.btn_play, self.btn_stop, self.btn_restart, self.btn_next, self.btn_loop):
            if b is not None:
                lay.addWidget(b)
        self.time = QLabel("0:00.00 / 0:00.00")
        self.time.setObjectName("Mono")
        self.time.setMinimumWidth(150)
        lay.addSpacing(6)
        lay.addWidget(self.time)
        lay.addStretch(1)
        vol_icon = QLabel()
        vol_icon.setPixmap(icons.icon("volume", size=16).pixmap(16, 16))
        lay.addWidget(vol_icon)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(90)
        self.volume.setToolTip("Preview volume (does not affect exports)")
        self.volume.setValue(int(player.volume * 100))
        lay.addWidget(self.volume)

        self.btn_play.clicked.connect(player.toggle)
        self.btn_stop.clicked.connect(player.stop)
        self.btn_loop.setChecked(player.loop)
        self.btn_loop.toggled.connect(self._loop)
        if self.btn_restart:
            self.btn_restart.clicked.connect(self._restart)
        if self.btn_prev:
            self.btn_prev.clicked.connect(self.prevRequested)
            self.btn_next.clicked.connect(self.nextRequested)
        self.volume.valueChanged.connect(self._volume)
        player.stateChanged.connect(self._state)
        player.positionChanged.connect(self._pos)
        player.loaded.connect(lambda _: self._pos(player.position))
        self._state(player.state)

    def _loop(self, on: bool) -> None:
        self.player.loop = on

    def _restart(self) -> None:
        self.restartRequested.emit()
        self.player.clear_range()
        self.player.stop()
        self.player.play()

    def _volume(self, v: int) -> None:
        if self.ctx is not None:
            self.ctx.set_preview_volume(v / 100.0)
        else:
            self.player.set_volume(v / 100.0)

    def _state(self, state: str) -> None:
        name = "pause" if state == "playing" else "play"
        self.btn_play.setIcon(icons.icon(name, size=20))
        self.btn_play.setProperty("icon_name", name)

    def _pos(self, s: float) -> None:
        self.time.setText(f"{fmt_time(s)} / {fmt_time(self.player.duration)}")

    def sync_volume(self) -> None:
        self.volume.blockSignals(True)
        self.volume.setValue(int(self.player.volume * 100))
        self.volume.blockSignals(False)
