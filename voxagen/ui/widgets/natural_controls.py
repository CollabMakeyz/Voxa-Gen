from __future__ import annotations

from dataclasses import fields

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QVBoxLayout, QWidget

from ...models.config import NaturalParams
from .common import FormGrid, ParamControl, divider, hint, label

QUALITY = [("standard", "Standard · 5 ms frames"), ("high", "High · 2.5 ms frames"), ("ultra", "Ultra · 1 ms frames")]
RESAMPLING = [("lq", "Low (fast)"), ("mq", "Medium"), ("hq", "High"), ("vhq", "Very high")]

SPECS = [
    ("pitch_accuracy", "Pitch Correction",
     "How strongly slow pitch drift is pulled onto the target note. 100 % = dead flat on the target. Lower values keep some of the singer's natural drift (always centred on the target).",
     0, 1, 100, " %", 0, "pitch_correction"),
    ("humanization", "Humanization",
     'Keeps the fast natural micro-variation (vibrato, jitter) of the source. It averages out to zero and has a cap. The note stays in tune.',
     0, 1, 100, " %", 0, "humanization"),
    ("humanization_max_cents", "Humanization depth limit",
     "Maximum pitch deviation humanization may keep, in cents.", 0, 50, 1, " ct", 1, "humanization"),
    ("formant_preservation", "Formant Preservation",
     "100 % keeps the vocal-tract resonances of the source (same voice at any pitch). 0 % moves them "
     "with the pitch (chipmunk / giant effect).", 0, 1, 100, " %", 0, "formant_preservation"),
    ("transient_preservation", "Transient Control",
     "Blends the time-aligned original attacks back in, keeping consonant clicks and onsets crisp.",
     0, 1, 100, " %", 0, "transient"),
    ("transient_window_ms", "Transient window", "Length of each preserved attack.", 5, 80, 1, " ms", 0, "transient"),
    ("smoothing", "Smoothing",
     "Temporal smoothing of the spectral envelope and of voiced/unvoiced transitions. Reduces "
     "flutter; too much softens articulation.", 0, 1, 100, " %", 0, "smoothing"),
    ("artifact_reduction", "Artifact Reduction",
     "Raises the high-band aperiodicity floor (less metallic buzz) and limits frame-to-frame envelope "
     "jumps (less warble).", 0, 1, 100, " %", 0, "artifact_reduction"),
    ("unvoiced_mix", "Voiced/Unvoiced Processing",
     "Consonants, breaths and silence have no pitch: this much of them comes from the untouched original "
     "instead of the resynthesis.", 0, 1, 100, " %", 0, "vuv"),
    ("wet", "Wet / Dry",
     'Blend between the refined output (wet) and plain resynthesis (dry). Both sit on the target pitch. Turning it never detunes anything.', 0, 1, 100, " %", 0, None),
]


class NaturalControls(QWidget):
    changed = Signal()

    def __init__(self, params: NaturalParams, tool_switches: bool = False):
        super().__init__()
        self.params = params
        self.tool_switches = tool_switches
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        self.controls: dict[str, ParamControl] = {}
        defaults = NaturalParams()
        for key, name, desc, lo, hi, scale, suffix, dec, tool in SPECS:
            checkable = tool_switches and tool is not None and key not in ("humanization_max_cents", "transient_window_ms")
            c = ParamControl(name, desc, lo, hi, getattr(params, key), getattr(defaults, key), dec, suffix,
                             scale, checkable=checkable, checked=params.tool_on(tool) if tool else True)
            c.valueChanged.connect(lambda val, k=key: self._set(k, val))
            if checkable:
                c.toggled.connect(lambda on, t=tool: self._toggle(t, on))
            self.controls[key] = c
            v.addWidget(c)
        v.addWidget(divider())
        grid = FormGrid()
        self.quality = QComboBox()
        for k, text in QUALITY:
            self.quality.addItem(text, k)
        self.quality.currentIndexChanged.connect(lambda _: self._set("quality", self.quality.currentData()))
        grid.row("Processing quality", self.quality,
                 "Analysis resolution. Higher is more detailed and slower; it never changes the target pitch.")
        self.resampling = QComboBox()
        for k, text in RESAMPLING:
            self.resampling.addItem(text, k)
        self.resampling.currentIndexChanged.connect(lambda _: self._set("resampling_quality", self.resampling.currentData()))
        grid.row("Resampling quality", self.resampling, "Quality of the final conversion to the export sample rate (soxr).")
        self.gain = QCheckBox("Gain compensation")
        self.gain.setToolTip("Matches the loudness of the processed note to the source (active RMS, ±12 dB max).")
        self.gain.toggled.connect(lambda on: self._set("gain_compensation", on))
        grid.full(self.gain, "Matches the loudness of each processed note to the original sample. Tuning won't make notes louder or quieter (at most ±12 dB).", "Gain compensation")
        self.vuv = QCheckBox("Voiced/unvoiced split")
        self.vuv.setToolTip("Process voiced and unvoiced segments separately (see Voiced/Unvoiced Processing).")
        self.vuv.toggled.connect(lambda on: self._set("vuv_processing", on))
        grid.full(self.vuv, "Treats sung (voiced) and unsung parts such as breaths and consonants separately. "
                            "Keep it on for natural consonants.", "Voiced/unvoiced split")
        self.auto = QCheckBox("Automatic analysis range (recommended)")
        self.auto.setToolTip("Detects the voice range automatically. Disable to set the pitch search range by hand.")
        self.auto.toggled.connect(self._auto)
        grid.full(self.auto, "Finds the voice's pitch range by itself. Turn off only if a very low or very "
                             "high voice is detected wrongly, then set the range below.", "Automatic range")
        self.floor = QDoubleSpinBox()
        self.floor.setRange(30, 400)
        self.floor.setSuffix(" Hz")
        self.floor.valueChanged.connect(lambda val: self._set("f0_floor", val))
        self.ceil = QDoubleSpinBox()
        self.ceil.setRange(200, 2000)
        self.ceil.setSuffix(" Hz")
        self.ceil.valueChanged.connect(lambda val: self._set("f0_ceil", val))
        grid.row("Pitch search floor", self.floor, "The lowest pitch the voice is searched at (when the "
                 "automatic range is off).")
        grid.row("Pitch search ceiling", self.ceil, "The highest pitch the voice is searched at (when the "
                 "automatic range is off).")
        v.addLayout(grid)
        self.load(params)

    def load(self, params: NaturalParams) -> None:
        self.params = params
        self._loading = True
        for key, c in self.controls.items():
            c.set_value(getattr(params, key), emit=False)
        for key, _, _, _, _, _, _, _, tool in SPECS:
            if tool and self.controls[key].check is not None:
                self.controls[key].set_checked(params.tool_on(tool))
        for combo, val in ((self.quality, params.quality), (self.resampling, params.resampling_quality)):
            combo.blockSignals(True)
            combo.setCurrentIndex(max(0, combo.findData(val)))
            combo.blockSignals(False)
        for w, val in ((self.gain, params.gain_compensation), (self.vuv, params.vuv_processing),
                       (self.auto, params.auto)):
            w.blockSignals(True)
            w.setChecked(val)
            w.blockSignals(False)
        for w, val in ((self.floor, params.f0_floor), (self.ceil, params.f0_ceil)):
            w.blockSignals(True)
            w.setValue(val)
            w.blockSignals(False)
        self._sync_tool_rows()
        self.floor.setEnabled(not params.auto)
        self.ceil.setEnabled(not params.auto)
        self._loading = False

    def _set(self, key: str, value) -> None:
        if getattr(self, "_loading", False):
            return
        self.last_key = key
        setattr(self.params, key, value)
        self.changed.emit()

    def _toggle(self, tool: str, on: bool) -> None:
        self.last_key = ""
        self.params.tools_enabled[tool] = on
        self._sync_tool_rows()
        self.changed.emit()

    def _sync_tool_rows(self) -> None:
        for key, _, _, _, _, _, _, _, tool in SPECS:
            c = self.controls[key]
            if tool and c.check is None and self.tool_switches:
                on = self.params.tool_on(tool)
                for w in (c.slider, c.spin, c.reset):
                    w.setEnabled(on)

    def _auto(self, on: bool) -> None:
        self.floor.setEnabled(not on)
        self.ceil.setEnabled(not on)
        self._set("auto", on)

    def restore_defaults(self) -> None:
        self.last_key = ""
        d = NaturalParams()
        for f in fields(NaturalParams):
            setattr(self.params, f.name, getattr(d, f.name))
        self.load(self.params)
        self.changed.emit()
