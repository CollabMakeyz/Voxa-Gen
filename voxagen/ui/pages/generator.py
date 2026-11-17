from __future__ import annotations

import copy
import os
import random
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIntValidator, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QGridLayout, QLineEdit,
    QHBoxLayout, QProgressBar, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from ...core.audio.pipeline import plan_notes
from ...core.export.exporter import (
    ExportConflict, destination_folder, export_chromatic, find_conflicts, planned_files, unique_destination,
    validate_template,
)
from ...core.pitch.tuning import NOTE_NAMES, TEMPERAMENTS, midi_of, note_name
from ...core.sequences.order import MissingSampleError, OrderError, build_order
from ...core.effects.chain import describe_chain
from ...core.workers import Task
from ...i18n import tr
from ...models.config import BIT_DEPTHS
from ...models.serialization import from_dict, to_dict
from ..widgets.analyzer_panel import AnalyzerPanel
from ..widgets.batch_panel import BatchPanel
from ..widgets.chrom_preview import ChromPreview
from ..widgets.project_bar import ProjectController
from ..widgets.common import (
    Card, ChoiceCards, DropZone, Fold, FormGrid, HelpButton, Segmented, button, confirm, elastic, fmt_time, hbox,
    hint, label, round_button, set_tone,
)
from ..widgets.dialogs import MissingSamplesDialog, ask_conflict, error_details
from ..widgets.natural_controls import NaturalControls
from ..widgets.sample_preview import SamplePreview
from ..widgets.sequence_editor import SequenceEditor
from .base import Page

MODE_TEXT = {
    "natural": 'Natural measures the voice once, then rebuilds every note at its exact pitch. The voice keeps its character (formants), its breaths and its consonants. Samples keep their length.',
    "robot": "Robot uses the same idea with quicker, coarser measurements. Use it for fast drafts or very "
             "long chromatics.",
    "legacy": "Legacy keeps the classic processing exactly as it was, for projects made with older tools.",
    "lab": "Lab profile runs Natural with the tools you set up on the Lab page.",
}
SAMPLE_RATES = ["44100", "48000", "88200", "96000"]
BIT_LABELS = {"pcm16": "16-bit PCM", "pcm24": "24-bit PCM", "float32": "32-bit float"}
FIT_LABELS = {"pad_trim": "Pad + trim", "pad_only": "Pad only (never cut)", "stretch": "Time-stretch"}


class CustomCentsDialog(QDialog):
    def __init__(self, parent, cents: list[float]):
        super().__init__(parent)
        self.setWindowTitle("Custom temperament")
        v = QVBoxLayout(self)
        v.addWidget(hint("Offset of each pitch class from equal temperament, in cents."))
        grid = QGridLayout()
        self.spins = []
        for i, name in enumerate(NOTE_NAMES):
            s = QDoubleSpinBox()
            s.setRange(-100, 100)
            s.setDecimals(2)
            s.setSuffix(" ct")
            s.setValue(cents[i] if i < len(cents) else 0.0)
            grid.addWidget(label(name), i // 4 * 2, i % 4)
            grid.addWidget(s, i // 4 * 2 + 1, i % 4)
            self.spins.append(s)
        v.addLayout(grid)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self) -> list[float]:
        return [s.value() for s in self.spins]


class GeneratorPage(Page):
    page_id = "generator"
    title = "Generator"
    subtitle = "Turn voice samples into a complete chromatic scale"
    icon = "generator"
    tabs = ["Basic", "Samples", "Order", "Exporting", "Preview", "Batch"]
    show_title = False
    TAB_SAMPLES = 1

    def __init__(self, ctx):
        super().__init__(ctx)
        self._export_task: Task | None = None
        self._loading = False
        self.batch = BatchPanel(ctx, self)
        self.project = ProjectController(ctx, self, self.batch)
        self.header.addLayout(self.project.widgets(), 1)
        b_presets = button("Manage presets", "presets")
        b_presets.setToolTip("All presets: sequences, modes, LAB profiles, effect chains, export settings")
        b_presets.clicked.connect(lambda: ctx.navigateRequested.emit("presets"))
        self.header.addWidget(b_presets)
        sc = QShortcut(QKeySequence("Ctrl+S"), self)
        sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc.activated.connect(self.project.save)
        self.add_tab(self.columns([self._source_card()], [self._musical_card()]))
        self.add_tab(self._samples_tab())
        self.add_tab(self.columns([self._order_card()], [self._sequence_card(), self._sequence_preview_card()]))
        self.add_tab(self.columns([self._mode_card(), self._effects_card()],
                                  [self._format_card(), self._timing_card(), self._output_card()]))
        self.add_tab(self._preview_tab())
        self.add_tab(self.columns([self.batch.queue_card], [self.batch.add_card]))
        self.root.addWidget(self.tab_stack, 1)
        self.root.addWidget(self._export_bar())

        ctx.libraryChanged.connect(self._refresh_source)
        ctx.configChanged.connect(self._on_config_changed)
        ctx.presetsChanged.connect(self._on_presets)
        self._elapsed = QElapsedTimer()
        self._clock = QTimer(self)
        self._clock.setInterval(200)
        self._clock.timeout.connect(self._tick_clock)
        self._wire_export_fields()
        self.load_from_config()

    def _source_card(self) -> Card:
        c = Card("Source", "Pick the folder with your voice samples (WAV). Names like 1.wav, a.wav or e2.wav are "
                           "recognised on their own. Your original files are never changed.")
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("No folder chosen yet")
        self.folder.setReadOnly(True)
        b_browse = button("Browse..", "folder")
        b_browse.setToolTip("Choose the folder that holds your samples")
        b_browse.clicked.connect(self.browse_folder)
        b_reload = round_button("refresh", "Rescan the folder (finds new, changed or deleted files)")
        b_reload.clicked.connect(self.reload_samples)
        c.add(hbox(self.folder, b_browse, b_reload))
        drop = DropZone("…or drop WAV files / folders here")
        drop.dropped.connect(self.add_paths)
        drop.clicked.connect(self.add_files_dialog)
        c.add(drop)
        self.source_summary = elastic(label("", "StatusText"))
        b_manage = button("See all samples", "samples")
        b_manage.setToolTip("Open the Samples tab: formats, detected pitch, previews and the sample check")
        b_manage.clicked.connect(lambda: self.go_tab(self.TAB_SAMPLES))
        c.add(hbox(self.source_summary, b_manage))
        return c

    def _musical_card(self) -> Card:
        c = Card("Musical settings", "Which notes the chromatic covers. The defaults work for most voices.")
        g = FormGrid()
        self.start_note = QComboBox()
        self.start_note.addItems(NOTE_NAMES)
        self.start_oct = QSpinBox()
        self.start_oct.setRange(0, 8)
        g.row("First note", hbox(self.start_note, label("octave"), self.start_oct, None),
              "The lowest note of the chromatic. C4 is middle C on a piano.",
              "Tip: C2 or C3 suits most FNF chromatics.")
        self.semitones = QSpinBox()
        self.semitones.setRange(1, 128)
        self.range_label = hint("")
        g.row("How many notes", hbox(self.semitones, self.range_label, None),
              "How many notes to generate, one semitone apart. 12 notes = one octave.")
        self.a4 = QDoubleSpinBox()
        self.a4.setRange(380.0, 480.0)
        self.a4.setDecimals(2)
        self.a4.setSuffix(" Hz")
        g.row("Tuning (A4)", self.a4, "The pitch every note is tuned against. Almost all music uses 440 Hz.",
              "Leave it at 440 Hz unless your song is tuned differently.")
        tuning = Fold("Advanced tuning", "Temperament and pitch correction on/off. Only change these if you "
                                         "know you need them.")
        tg = FormGrid()
        self.temperament = QComboBox()
        for t in TEMPERAMENTS:
            self.temperament.addItem({"equal": "Equal (normal)", "just": "Just intonation",
                                      "pythagorean": "Pythagorean", "custom": "Custom offsets"}[t], t)
        self.temp_root = QComboBox()
        self.temp_root.addItems(NOTE_NAMES)
        self.b_custom = button("Edit offsets", "edit")
        self.b_custom.clicked.connect(self.edit_custom_cents)
        tg.row("Temperament", self.temperament,
               "How the 12 notes are spaced. 'Equal' is what pianos and DAWs use. The others sound purer in one "
               "key and worse in others.", "Recommended: Equal.")
        tg.row("Key (root)", hbox(self.temp_root, self.b_custom, None),
               "The key that Just and Pythagorean are built on. 'Edit offsets' sets your own tuning per note.")
        self.retune = QCheckBox("Tune every note to its pitch")
        tg.full(self.retune, "On: each note is moved to its exact pitch (normal). Off: samples keep their own "
                              "pitch and are only placed in order.", "Pitch correction")
        tuning.add(tg)
        c.add(g)
        c.add(tuning)
        for w in (self.start_note, self.temperament, self.temp_root):
            w.currentIndexChanged.connect(self._save_musical)
        for w in (self.start_oct, self.semitones, self.a4):
            w.valueChanged.connect(self._save_musical)
        self.retune.toggled.connect(self._save_musical)
        return c

    def _samples_tab(self) -> QWidget:
        from .sample_manager import SampleManagerView
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self.samples_switch = Segmented([("list", "All samples"), ("check", "Check for problems")], "list")
        help_ = HelpButton("Samples", "“All samples” lists every sample with its format and detected note, lets you "
                                      "leave samples out and preview them. “Check for problems” looks for issues "
                                      "that would make the chromatic sound wrong, with a fix for each.")
        v.addLayout(hbox(self.samples_switch, help_, None))
        self.samples_stack = QStackedWidget()
        self.samples_view = SampleManagerView(self.ctx)
        self.analyzer = AnalyzerPanel(self.ctx)
        self.analyzer.sampleActivated.connect(self._show_sample)
        self.samples_stack.addWidget(self.samples_view)
        self.samples_stack.addWidget(self.scroll(self.analyzer))
        self.samples_switch.changed.connect(lambda k: self.samples_stack.setCurrentIndex(0 if k == "list" else 1))
        v.addWidget(self.samples_stack, 1)
        return w

    def _show_sample(self, sid: str) -> None:
        self.samples_switch.set_value("list")
        self.samples_view.select(sid)

    def go_tab(self, i: int) -> None:
        self.set_tab(i)
        w = self.window()
        if hasattr(w, "content"):
            w.content.tabs.set_current(i, emit=False)

    def _order_card(self) -> Card:
        c = Card("Order", "Which sample is used for each note.")
        self.order_mode = ChoiceCards([
            ("sequential", "In order", "1, 2, 3… by name, then starts again."),
            ("shuffle", "Shuffle", "Mixed up, but every sample is used once before any repeats."),
            ("random", "Random", "A random sample for every note. Repeats can happen."),
            ("vocal", "Vocal sequence", "Your own list of sample names, e.g. BF Classic Sequence."),
        ])
        self.order_mode.changed.connect(self._save_order)
        c.add(self.order_mode)
        self.seed_row = QWidget()
        self.fixed_seed = QCheckBox("Keep this order next time")
        self.seed = QSpinBox()
        self.seed.setRange(1, 2 ** 31 - 1)
        b_reroll = button("New order", "dice")
        b_reroll.setToolTip("Shuffle again with a new random order")
        b_reroll.clicked.connect(self.reroll)
        seed_help = HelpButton("Random order", "Shuffle and Random use a number (the seed) to decide the order. "
                                               "The preview and the export always use the same one. Tick 'Keep this "
                                               "order' to get the same order after restarting the app.")
        sl = hbox(b_reroll, self.fixed_seed, None, label("seed"), self.seed, seed_help)
        self.seed_row.setLayout(sl)
        c.add(self.seed_row)
        self.order_preview = hint("")
        self.order_preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        c.add(self.order_preview)
        self.fixed_seed.toggled.connect(self._save_order)
        self.seed.valueChanged.connect(self._save_order)
        return c

    def _sequence_card(self) -> Card:
        c = Card("Vocal sequence", "Type or click sample names to build the order the notes use. The list repeats "
                                   "until every note has a sample.")
        self.seq_card = c
        self.sequence_editor = SequenceEditor(self.ctx)
        self.sequence_editor.changed.connect(self._refresh_order_preview)
        c.add(self.sequence_editor)
        self.seq_off = hint("Choose “Vocal sequence” in Order to build your own sequence.")
        c.add(self.seq_off)
        return c

    def _sequence_preview_card(self) -> Card:
        c = Card("Listen to the sequence", "Play the sequence once, in order, without exporting: with the "
                                           "original samples, or processed with the current export mode.")
        self.seq_preview_card = c
        c.add(self.sequence_editor.preview_box)
        return c

    def _mode_card(self) -> Card:
        c = Card("Export mode", "How the samples are tuned. Natural is the best for almost everyone.")
        self.mode = ChoiceCards([
            ("natural", "Natural  ★", "Best quality. Keeps the voice natural at any pitch."),
            ("robot", "Robot", 'Faster and lighter. Still exactly in tune (not a robot effect).'),
            ("legacy", "Legacy", "The classic chain, kept the same for old projects."),
            ("lab", "Lab profile", "Your own settings, made on the Lab page."),
        ])
        self.mode.changed.connect(self._save_mode)
        c.add(self.mode)
        self.mode_text = hint("")
        c.add(self.mode_text)
        self.mode_stack = QStackedWidget()
        nat = QWidget()
        nv = QVBoxLayout(nat)
        nv.setContentsMargins(0, 0, 0, 0)
        nv.setSpacing(10)
        self.nat_preset = QComboBox()
        b_load = button("Use preset", "import")
        b_load.clicked.connect(self.load_natural_preset)
        nat_help = HelpButton("Natural presets", "Ready-made Natural settings: Clean (default), Expressive (keeps "
                                                 "vibrato), Smooth (softer) and Ultra (most detail, slowest).")
        nv.addLayout(hbox(label("Preset"), self.nat_preset, b_load, nat_help, None))
        self.nat_controls = NaturalControls(self.ctx.config.natural)
        self.nat_controls.changed.connect(lambda: self.ctx.touch("natural"))
        self.nat_adv = Fold("Advanced Natural settings",
                            "Natural picks good values on its own. Open this to fine-tune each tool; every "
                            "setting has a “?” that explains it.")
        b_def = button("Restore defaults", "reset")
        b_def.clicked.connect(self.nat_controls.restore_defaults)
        self.nat_adv.add(hbox(None, b_def))
        self.nat_adv.add(self.nat_controls)
        nv.addWidget(self.nat_adv)
        self.mode_stack.addWidget(nat)
        rob = Fold("Advanced Robot settings", "Speed versus detail. The defaults are already fast.")
        rg = FormGrid()
        self.robot_frame = QDoubleSpinBox()
        self.robot_frame.setRange(5, 20)
        self.robot_frame.setSuffix(" ms")
        self.robot_frame.valueChanged.connect(lambda v: self._set("robot", "frame_period_ms", v))
        rg.row("Analysis step", self.robot_frame, "How often the voice is measured. Bigger = faster but less "
                                                 "detailed.", "Default: 10 ms.")
        self.robot_rs = QComboBox()
        for k, t in (("lq", "Low (fast)"), ("mq", "Medium"), ("hq", "High"), ("vhq", "Very high")):
            self.robot_rs.addItem(t, k)
        self.robot_rs.currentIndexChanged.connect(lambda _: self._set("robot", "resampling_quality", self.robot_rs.currentData()))
        rg.row("Resampling", self.robot_rs, "Quality of converting to the export sample rate.")
        self.robot_gain = QCheckBox("Keep the original loudness")
        self.robot_gain.toggled.connect(lambda on: self._set("robot", "gain_compensation", on))
        rg.full(self.robot_gain, "Matches the volume of each processed note to the original sample.",
                "Gain compensation")
        rob.add(rg)
        self.mode_stack.addWidget(rob)
        leg = QWidget()
        lgv = QVBoxLayout(leg)
        lgv.setContentsMargins(0, 0, 0, 0)
        lgv.addWidget(hint('Legacy has no settings on purpose. It always works the same way, and old projects keep sounding the same: mono, 48 kHz, classic PSOLA retuning.'))
        self.mode_stack.addWidget(leg)
        lab = QWidget()
        lbv = QVBoxLayout(lab)
        lbv.setContentsMargins(0, 0, 0, 0)
        self.lab_profile = QComboBox()
        b_apply = button("Use profile", "check")
        b_apply.clicked.connect(self.use_lab_profile)
        b_open = button("Open Lab", "lab")
        b_open.clicked.connect(lambda: self.ctx.navigateRequested.emit("lab"))
        lbv.addLayout(hbox(label("Profile"), self.lab_profile, b_apply, None, b_open))
        self.lab_summary = hint("")
        lbv.addWidget(self.lab_summary)
        self.mode_stack.addWidget(lab)
        c.add(self.mode_stack)
        return c

    def _effects_card(self) -> Card:
        c = Card("Effects", "Optional creative effects from the LAB (distortion, vibrato, chorus…). They are only "
                            "added when you turn them on here.")
        self.fx_on = QCheckBox("Add the LAB effects to this export")
        self.fx_on.toggled.connect(self._save_fx)
        fx_help = HelpButton("Effects in the export", "Runs the LAB effect chain on every note after the export mode (Natural, Robot, Legacy or Lab): chromatic preview, export and batch jobs. Off means effects don't touch the export at all. Your sample files are never changed.",
                             "Default: off.")
        c.add(hbox(self.fx_on, fx_help, None))
        self.fx_summary = elastic(label("", "StatusText"))
        c.add(self.fx_summary)
        b_open = button("Edit effects in the LAB", "sliders")
        b_open.clicked.connect(self._open_lab_effects)
        c.add(hbox(b_open, None))
        self.ctx.configChanged.connect(lambda sec: sec == "effects" and self._sync_fx())
        return c

    def _save_fx(self, on: bool) -> None:
        if self._loading:
            return
        self.ctx.config.effects.enabled = on
        self.ctx.touch("effects")
        self._sync_fx()

    def _sync_fx(self) -> None:
        fx = self.ctx.config.effects
        self.fx_on.blockSignals(True)
        self.fx_on.setChecked(fx.enabled)
        self.fx_on.blockSignals(False)
        chain = describe_chain(fx)
        if not fx.chain:
            self.fx_summary.setText(tr("No effects yet. Build a chain in LAB › Effects."))
            set_tone(self.fx_summary, "")
        elif not fx.enabled:
            self.fx_summary.setText(tr("Off. Chain ready: {chain}", chain=_tr_chain(chain)))
            set_tone(self.fx_summary, "")
        else:
            self.fx_summary.setText(tr("On: {chain}", chain=_tr_chain(chain) or tr("no active effect")))
            set_tone(self.fx_summary, "ok" if chain else "warn")
        self.fx_summary.setProperty("i18n_text_skip", True)

    def _open_lab_effects(self) -> None:
        self.ctx.navigateRequested.emit("lab")
        w = self.window()
        lab = next((p for p in getattr(w, "pages", []) if p.page_id == "lab"), None)
        if lab is not None:
            lab._go_tab(1)

    def _format_card(self) -> Card:
        c = Card("File format", "What kind of WAV is written. The defaults work in FL Studio and most programs.")
        g = FormGrid()
        self.sr = QComboBox()
        self.sr.setEditable(True)
        self.sr.addItems(SAMPLE_RATES)
        self.sr.setValidator(QIntValidator(8000, 384000, self))
        self.sr.setMinimumWidth(120)
        g.row("Sample rate", hbox(self.sr, label("Hz"), None),
              "How many samples per second. 48000 Hz is standard; you can also type your own value.",
              "Recommended: 48000 Hz.")
        self.bits = QComboBox()
        for b in BIT_DEPTHS:
            self.bits.addItem(BIT_LABELS[b], b)
        g.row("Bit depth", self.bits, "16-bit is smaller and works everywhere. 24-bit and 32-bit float keep more "
                                      "detail for mixing.", "Recommended: 16-bit for FNF, 24-bit for studio work.")
        self.channels = Segmented([("mono", "Mono"), ("stereo", "Stereo")])
        g.row("Channels", hbox(self.channels, None),
              "Mono is one channel (normal for voices). Stereo keeps the left/right image of stereo samples.")
        adv = Fold("Advanced format", "Dither for 16-bit files.")
        ag = FormGrid()
        self.dither = QCheckBox("Dither when saving 16-bit")
        ag.full(self.dither, "Adds a tiny, inaudible noise so quiet parts don't get grainy when saving as "
                             "16-bit. Leave it on.", "Dither")
        adv.add(ag)
        c.add(g)
        c.add(adv)
        return c

    def _timing_card(self) -> Card:
        c = Card("Notes & volume", "How long each note is, the silence between notes, and how loud the file is.")
        g = FormGrid()
        self.gap = QDoubleSpinBox()
        self.gap.setRange(0, 10000)
        self.gap.setDecimals(0)
        self.gap.setSuffix(" ms")
        g.row("Silence between notes", self.gap, "The gap between notes in the full chromatic file.",
              "Default: 300 ms.")
        self.fixed = QCheckBox("Same length for every note")
        self.fixed_ms = QDoubleSpinBox()
        self.fixed_ms.setRange(10, 60000)
        self.fixed_ms.setDecimals(0)
        self.fixed_ms.setSuffix(" ms")
        g.row("Note length", hbox(self.fixed, self.fixed_ms, None),
              "Off: each note keeps the length of its sample. On: every note gets this length.")
        self.fit = QComboBox()
        for k, t in FIT_LABELS.items():
            self.fit.addItem(t, k)
        g.row("If a sample is longer", self.fit,
              "Pad + trim: shorter notes get silence, longer ones are cut. Pad only: never cuts anything. "
              "Time-stretch: makes the note longer or shorter without changing its pitch.")
        self.fade_in = QDoubleSpinBox()
        self.fade_out = QDoubleSpinBox()
        for s in (self.fade_in, self.fade_out):
            s.setRange(0, 5000)
            s.setDecimals(1)
            s.setSuffix(" ms")
        g.row("Fades", hbox(label("in"), self.fade_in, label("out"), self.fade_out, None),
              "A short fade at the start and end of each note removes clicks.", "Try 2 ms in and 15 ms out.")
        self.normalize = QCheckBox("Make it as loud as possible")
        self.norm_db = QDoubleSpinBox()
        self.norm_db.setRange(-24, 0)
        self.norm_db.setDecimals(1)
        self.norm_db.setSuffix(" dBFS")
        g.row("Normalize", hbox(self.normalize, self.norm_db, None),
              "Raises the volume so the loudest point reaches this level (0 dBFS = maximum).",
              "Recommended target: -1 dBFS.")
        adv = Fold("Advanced volume", "Per-note normalization, master volume, clipping and silence trimming.")
        ag = FormGrid()
        self.norm_mode = QComboBox()
        self.norm_mode.addItem("Whole chromatic", "global")
        self.norm_mode.addItem("Each note", "per_note")
        ag.row("Normalize over", self.norm_mode, "Whole chromatic keeps the notes' relative volume. Each note makes "
                                                 "every note equally loud.")
        self.master = QDoubleSpinBox()
        self.master.setRange(-60, 24)
        self.master.setDecimals(1)
        self.master.setSuffix(" dB")
        ag.row("Master volume", self.master, "Raises or lowers the whole export.")
        self.clip = QCheckBox("Never distort (prevent clipping)")
        ag.full(self.clip, "If the export would be too loud and distort, it is lowered just enough. You are told "
                           "when this happens.", "Prevent clipping")
        self.trim = QCheckBox("Cut silence from the samples")
        self.trim_db = QDoubleSpinBox()
        self.trim_db.setRange(-90, -10)
        self.trim_db.setSuffix(" dBFS")
        ag.row("Silence", hbox(self.trim, self.trim_db, None),
               "Removes silence at the start and end of each sample before processing. Sounds quieter than this "
               "level count as silence.")
        adv.add(ag)
        c.add(g)
        c.add(adv)
        return c

    def _output_card(self) -> Card:
        c = Card("Output", "Where the files go and what they are called.")
        g = FormGrid()
        self.w_chrom = QCheckBox("Full chromatic (one WAV)")
        g.full(self.w_chrom, "One WAV with every note in a row.", "Full chromatic")
        self.markers = QCheckBox("Add slice markers")
        g.full(self.markers, "Marks where each note starts, so FL Studio Slicex cuts the file into notes by itself.",
               "Slice markers")
        self.w_notes = QCheckBox("One WAV per note")
        g.full(self.w_notes, "Also saves every note as its own file in a sub-folder.", "Individual notes")
        self.out_dir = QLineEdit()
        self.out_dir.setPlaceholderText("Default folder (Settings)")
        b_out = button("Browse..", "folder")
        b_out.clicked.connect(self.choose_out_dir)
        g.row("Save in", hbox(self.out_dir, b_out), "The folder where the export folder is created.")
        self.folder_name = QLineEdit()
        g.row("Folder name", self.folder_name, "Name of the new folder for this export. Existing files are never "
                                               "replaced without asking.")
        adv = Fold("Advanced file names", "Change how the WAV files are named.")
        ag = FormGrid()
        self.chrom_name = QLineEdit()
        ag.row("Chromatic file", hbox(self.chrom_name, label(".wav"), None), "Name of the full chromatic file.")
        self.note_tpl = QLineEdit()
        self.subfolder = QLineEdit()
        ag.row("Note files", hbox(self.subfolder, label("/"), self.note_tpl, label(".wav")),
               "Sub-folder and name pattern for the single notes. You can use {index} {note} {pitch} {octave} "
               "{midi} {sample} {hz}.", "Example: note_{index:03d} → note_001.wav")
        adv.add(ag)
        c.add(g)
        c.add(adv)
        self.tpl_status = elastic(label("", "StatusText"))
        c.add(self.tpl_status)
        return c

    def _wire_export_fields(self) -> None:
        self.sr.currentTextChanged.connect(self._save_export)
        for w in (self.bits, self.norm_mode, self.fit):
            w.currentIndexChanged.connect(self._save_export)
        self.channels.changed.connect(self._save_export)
        for w in (self.norm_db, self.fade_in, self.fade_out, self.gap, self.fixed_ms, self.master, self.trim_db):
            w.valueChanged.connect(self._save_export)
        for w in (self.dither, self.normalize, self.fixed, self.clip, self.trim, self.w_chrom, self.markers, self.w_notes):
            w.toggled.connect(self._save_export)
        for w in (self.out_dir, self.folder_name, self.chrom_name, self.note_tpl, self.subfolder):
            w.textChanged.connect(self._save_export)

    def _preview_tab(self) -> QWidget:
        chrom = Card("Chromatic preview", 'Hear the whole chromatic before exporting, with the exact processing the export uses. Click a key to hear one note.')
        self.chrom = ChromPreview(self.ctx)
        chrom.add(self.chrom)
        single = Card("Sample preview", "Hear one sample before and after processing. A/B switches between the "
                                        "original and the processed sound at the same spot.")
        self.sample_preview = SamplePreview(self.ctx)
        single.add(self.sample_preview)
        return self.columns([chrom], [single])

    def _export_bar(self) -> Card:
        c = Card()
        c.setObjectName("ExportBar")
        c.outer.setContentsMargins(18, 12, 18, 12)
        self.b_export = button("Export chromatic", "export", "Primary")
        self.b_export.setMinimumWidth(180)
        self.b_export.clicked.connect(self.start_export)
        self.b_cancel_export = button("Cancel", "close", "Danger")
        self.b_cancel_export.clicked.connect(self.cancel_export)
        self.b_cancel_export.hide()
        self.b_open = button("Open folder", "folder")
        self.b_open.hide()
        self.b_open.clicked.connect(self.open_last_export)
        self.export_stage = label("Ready to export", "CardTitle")
        self.export_detail = elastic(label("", "Hint"))
        self.export_progress = QProgressBar()
        self.export_progress.setRange(0, 1000)
        self.export_progress.setValue(0)
        self.export_time = label("", "Mono")
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addLayout(hbox(self.export_stage, self.export_detail, None, self.export_time))
        col.addWidget(self.export_progress)
        c.add(hbox(self.b_export, col, self.b_cancel_export, self.b_open))
        self._last_export: Path | None = None
        return c

    def load_from_config(self) -> None:
        self._loading = True
        cfg = self.ctx.config
        m, o, ex = cfg.musical, cfg.order, cfg.export
        self.folder.setText(cfg.sample_folder)
        self.start_note.setCurrentIndex(m.start_note)
        self.start_oct.setValue(m.start_octave)
        self.semitones.setValue(m.semitones)
        self.a4.setValue(m.a4_hz)
        self.temperament.setCurrentIndex(max(0, self.temperament.findData(m.temperament)))
        self.temp_root.setCurrentIndex(m.temperament_root)
        self.retune.setChecked(m.retune)
        self.order_mode.set_value(o.mode, emit=False)
        self.fixed_seed.setChecked(o.use_seed)
        self.seed.setValue(o.seed)
        self.mode.set_value(cfg.mode, emit=False)
        self.nat_controls.load(cfg.natural)
        self.robot_frame.setValue(cfg.robot.frame_period_ms)
        self.robot_rs.setCurrentIndex(max(0, self.robot_rs.findData(cfg.robot.resampling_quality)))
        self.robot_gain.setChecked(cfg.robot.gain_compensation)
        self.sr.setCurrentText(str(ex.sample_rate))
        self.bits.setCurrentIndex(max(0, self.bits.findData(ex.bit_depth)))
        self.dither.setChecked(ex.dither)
        self.channels.set_value(ex.channels, emit=False)
        self.normalize.setChecked(ex.normalize)
        self.norm_mode.setCurrentIndex(max(0, self.norm_mode.findData(ex.normalize_mode)))
        self.norm_db.setValue(ex.normalize_peak_db)
        self.fade_in.setValue(ex.fade_in_ms)
        self.fade_out.setValue(ex.fade_out_ms)
        self.gap.setValue(ex.gap_ms)
        self.fixed.setChecked(ex.fixed_duration)
        self.fixed_ms.setValue(ex.fixed_duration_ms)
        self.fit.setCurrentIndex(max(0, self.fit.findData(ex.fit_mode)))
        self.master.setValue(ex.master_volume_db)
        self.clip.setChecked(ex.prevent_clipping)
        self.trim.setChecked(ex.trim_silence)
        self.trim_db.setValue(ex.trim_threshold_db)
        self.w_chrom.setChecked(ex.write_chromatic)
        self.markers.setChecked(ex.markers)
        self.w_notes.setChecked(ex.write_individual)
        self.out_dir.setText(ex.output_dir)
        self.folder_name.setText(ex.folder_name)
        self.chrom_name.setText(ex.chromatic_name)
        self.note_tpl.setText(ex.note_name_template)
        self.subfolder.setText(ex.samples_subfolder)
        self._loading = False
        self._sync_visibility()
        self._refresh_source()
        self._on_presets("natural")
        self._on_presets("lab")
        self.sequence_editor.refresh()
        self._sync_fx()
        self._refresh_order_preview()

    def _save_musical(self, *_) -> None:
        if self._loading:
            return
        m = self.ctx.config.musical
        m.start_note = self.start_note.currentIndex()
        m.start_octave = self.start_oct.value()
        m.semitones = self.semitones.value()
        m.a4_hz = self.a4.value()
        m.temperament = self.temperament.currentData()
        m.temperament_root = self.temp_root.currentIndex()
        m.retune = self.retune.isChecked()
        self._sync_visibility()
        self.ctx.touch("musical")
        self._refresh_order_preview()

    def _save_order(self, *_) -> None:
        if self._loading:
            return
        o = self.ctx.config.order
        o.mode = self.order_mode.value()
        o.use_seed = self.fixed_seed.isChecked()
        o.seed = self.seed.value()
        self._sync_visibility()
        self.ctx.touch("order")
        self._refresh_order_preview()

    def _save_mode(self, *_) -> None:
        if self._loading:
            return
        self.ctx.config.mode = self.mode.value()
        self._sync_visibility()
        self.ctx.touch("mode")

    def _set(self, section: str, key: str, value) -> None:
        if self._loading:
            return
        setattr(getattr(self.ctx.config, section), key, value)
        self.ctx.touch(section)

    def _save_export(self, *_) -> None:
        if self._loading:
            return
        ex = self.ctx.config.export
        try:
            sr = int(self.sr.currentText())
            if 8000 <= sr <= 384000:
                ex.sample_rate = sr
        except ValueError:
            pass
        ex.bit_depth = self.bits.currentData()
        ex.dither = self.dither.isChecked()
        ex.channels = self.channels.value()
        ex.normalize = self.normalize.isChecked()
        ex.normalize_mode = self.norm_mode.currentData()
        ex.normalize_peak_db = self.norm_db.value()
        ex.fade_in_ms = self.fade_in.value()
        ex.fade_out_ms = self.fade_out.value()
        ex.gap_ms = self.gap.value()
        ex.fixed_duration = self.fixed.isChecked()
        ex.fixed_duration_ms = self.fixed_ms.value()
        ex.fit_mode = self.fit.currentData()
        ex.master_volume_db = self.master.value()
        ex.prevent_clipping = self.clip.isChecked()
        ex.trim_silence = self.trim.isChecked()
        ex.trim_threshold_db = self.trim_db.value()
        ex.write_chromatic = self.w_chrom.isChecked()
        ex.markers = self.markers.isChecked()
        ex.write_individual = self.w_notes.isChecked()
        ex.output_dir = self.out_dir.text().strip()
        ex.folder_name = self.folder_name.text().strip() or "Voxa GEN Export"
        ex.chromatic_name = self.chrom_name.text().strip() or "chromatic"
        ex.note_name_template = self.note_tpl.text().strip() or "note_{index:03d}"
        ex.samples_subfolder = self.subfolder.text().strip() or "samples"
        self._sync_visibility()
        self.ctx.touch("export")

    def _sync_visibility(self) -> None:
        cfg = self.ctx.config
        m = cfg.musical
        start = midi_of(m.start_note, m.start_octave)
        self.range_label.setText(f"{note_name(start)} → {note_name(start + m.semitones - 1)}")
        self.range_label.setProperty("i18n_text_skip", True)
        self.temp_root.setEnabled(m.temperament in ("just", "pythagorean"))
        self.b_custom.setEnabled(m.temperament == "custom")
        self.seed_row.setVisible(cfg.order.mode in ("shuffle", "random"))
        vocal = cfg.order.mode == "vocal"
        self.sequence_editor.setVisible(vocal)
        self.seq_off.setVisible(not vocal)
        self.seq_preview_card.setVisible(vocal)
        idx = {"natural": 0, "robot": 1, "legacy": 2, "lab": 3}[cfg.mode]
        self.mode_stack.setCurrentIndex(idx)
        self.mode_text.setText(tr(MODE_TEXT[cfg.mode]))
        self.mode_text.setVisible(True)
        if not m.retune:
            self.mode_text.setText(tr("Pitch correction is off (Basic → Advanced tuning): notes keep their own pitch."))
        ex = cfg.export
        self.dither.setEnabled(ex.bit_depth == "pcm16")
        self.norm_mode.setEnabled(ex.normalize and cfg.mode != "legacy")
        self.norm_db.setEnabled(ex.normalize and cfg.mode != "legacy")
        self.fixed_ms.setEnabled(ex.fixed_duration)
        self.fit.setEnabled(ex.fixed_duration)
        self.trim_db.setEnabled(ex.trim_silence)
        self.markers.setEnabled(ex.write_chromatic)
        self.note_tpl.setEnabled(ex.write_individual)
        self.subfolder.setEnabled(ex.write_individual)
        err = validate_template(ex.note_name_template) if ex.write_individual else None
        if err:
            self.tpl_status.setText(tr(err))
            set_tone(self.tpl_status, "error")
        else:
            dest = destination_folder(ex, self.ctx.settings.default_output_dir)
            self.tpl_status.setText(f"→ {dest}")
            set_tone(self.tpl_status, "")

    def _on_config_changed(self, section: str) -> None:
        if section in ("lab_profile", "all", "mode_external"):
            self.load_from_config()

    def _on_presets(self, kind: str) -> None:
        if kind == "natural":
            self.nat_preset.clear()
            for p in self.ctx.presets.list("natural"):
                self.nat_preset.addItem(p.name, p.name)
        if kind == "lab":
            cur = self.ctx.config.lab_profile_name
            self.lab_profile.clear()
            for p in self.ctx.presets.list("lab"):
                self.lab_profile.addItem(p.name, p.name)
            i = self.lab_profile.findData(cur)
            if i >= 0:
                self.lab_profile.setCurrentIndex(i)
            self._lab_summary()

    def _lab_summary(self) -> None:
        cfg = self.ctx.config
        p = cfg.lab
        off = [k for k, v in p.tools_enabled.items() if not v]
        name = tr(cfg.lab_profile_name) if cfg.lab_profile_name else tr("(unsaved LAB settings)")
        self.lab_summary.setText(tr("Active: {name} · formants {f} · humanization {h} · smoothing {s} · artifact "
                                    "red. {a}", name=name, f=f"{p.formant_preservation:.0%}",
                                    h=f"{p.humanization:.0%}", s=f"{p.smoothing:.0%}",
                                    a=f"{p.artifact_reduction:.0%}") + (
            " · " + tr("off: {tools}", tools=", ".join(off)) if off else ""))

    def browse_folder(self) -> None:
        start = self.ctx.config.sample_folder or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, tr("Choose sample folder"), start)
        if d:
            self.set_folder(d)

    def set_folder(self, folder: str) -> None:
        self.ctx.config.sample_folder = folder
        self.ctx.config.sample_paths = []
        self.folder.setText(folder)
        try:
            self.ctx.library.clear()
            res = self.ctx.library.add_folder(folder)
        except Exception as exc:
            return self.ctx.toast(tr("Cannot read folder: {error}", error=str(exc)), "error")
        rec = self.ctx.settings.recent_folders
        if folder in rec:
            rec.remove(folder)
        rec.insert(0, folder)
        del rec[8:]
        self.ctx.libraryChanged.emit()
        self.ctx.touch("samples")
        self.ctx.sound("confirm")
        self._report_add(res)

    def add_files_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, tr("Add WAV files"), self.ctx.config.sample_folder,
                                                tr("WAV audio (*.wav)"))
        if files:
            self.add_paths(files)

    def add_paths(self, paths: list[str]) -> None:
        if len(paths) == 1 and os.path.isdir(paths[0]) and not len(self.ctx.library):
            return self.set_folder(paths[0])
        res = self.ctx.library.add_files(paths)
        self.ctx.remember_samples()
        self.ctx.libraryChanged.emit()
        self.ctx.touch("samples")
        self._report_add(res)

    def _report_add(self, res) -> None:
        msg = tr("{n} sample(s) added", n=len(res.added))
        if res.skipped:
            msg += " · " + tr("{n} non-WAV file(s) ignored", n=len(res.skipped))
        if res.conflicts:
            names = ", ".join(sorted({sid for _, sid in res.conflicts}))
            msg += " · " + tr("name conflict: {names} (already loaded from another folder)", names=names)
        self.ctx.toast(msg, "warn" if res.conflicts else "ok")

    def reload_samples(self) -> None:
        changed = self.ctx.library.reload()
        folder = self.ctx.config.sample_folder
        added = self.ctx.library.add_folder(folder).added if folder and os.path.isdir(folder) else []
        self.ctx.libraryChanged.emit()
        self.ctx.touch("samples")
        self.ctx.toast(tr("Reloaded · {c} changed · {a} new · {m} missing", c=len(changed), a=len(added),
                          m=len(self.ctx.library.missing())), "ok")

    def _refresh_source(self) -> None:
        lib = self.ctx.library
        n = len(lib)
        usable = len(lib.usable_ids(set(self.ctx.config.disabled_samples)))
        miss = len(lib.missing())
        dup = len(lib.duplicates())
        errors = sum(1 for s in lib.samples() if s.status == "error")
        parts = [tr("{u} of {n} samples in use", u=usable, n=n)] if n else [tr("No samples loaded")]
        if miss:
            parts.append(tr("{n} missing", n=miss))
        if errors:
            parts.append(tr("{n} unreadable", n=errors))
        if dup:
            parts.append(tr("{n} duplicate", n=dup))
        self.source_summary.setText(" · ".join(parts))
        set_tone(self.source_summary, "error" if (miss or errors) else ("warn" if dup or not n else "ok"))
        self._refresh_order_preview()

    def _refresh_order_preview(self) -> None:
        cfg = self.ctx.config
        if cfg.order.mode == "vocal":
            self.order_preview.setText("")
            return
        try:
            ids = self.ctx.library.usable_ids(set(cfg.disabled_samples))
            order = build_order(min(cfg.musical.semitones, 24), ids, cfg.order)
            more = " …" if cfg.musical.semitones > 24 else ""
            self.order_preview.setText(tr("Order: {list}", list=" ".join(order) + more))
        except OrderError as exc:
            self.order_preview.setText(tr(str(exc)))

    def reroll(self) -> None:
        self.seed.setValue(random.randrange(1, 2 ** 31 - 1))
        self.ctx.sound("confirm")

    def edit_custom_cents(self) -> None:
        dlg = CustomCentsDialog(self, self.ctx.config.musical.custom_cents)
        if dlg.exec():
            self.ctx.config.musical.custom_cents = dlg.values()
            self.ctx.touch("musical")

    def load_natural_preset(self) -> None:
        p = self.ctx.presets.get("natural", self.nat_preset.currentData() or "")
        if p is None:
            return
        params = p.typed()
        for k, v in to_dict(params).items():
            setattr(self.ctx.config.natural, k, v)
        self.nat_controls.load(self.ctx.config.natural)
        self.ctx.touch("natural")
        self.ctx.toast(tr("Natural settings: {name}", name=tr(p.name)), "ok")

    def use_lab_profile(self) -> None:
        name = self.lab_profile.currentData()
        p = self.ctx.presets.get("lab", name or "")
        if p is None:
            return
        self.ctx.config.lab = from_dict(type(self.ctx.config.lab), p.data)
        self.ctx.config.lab_profile_name = p.name
        self._lab_summary()
        self.ctx.touch("lab")
        self.ctx.toast(tr("LAB profile “{name}” is active for Lab mode.", name=tr(p.name)), "ok")

    def choose_out_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Export destination"), self.out_dir.text() or
                                             self.ctx.settings.default_output_dir or os.path.expanduser("~"))
        if d:
            self.out_dir.setText(d)

    def start_export(self) -> None:
        if self._export_task is not None and self._export_task.running:
            return
        if self.batch.running:
            return self.ctx.toast("The batch queue is running. Wait for it or cancel it first.", "warn")
        cfg = copy.deepcopy(self.ctx.config)
        lib = self.ctx.library
        if not lib.usable_ids(set(cfg.disabled_samples)):
            return self.ctx.toast("No usable samples are loaded.", "error")
        err = validate_template(cfg.export.note_name_template)
        if err and cfg.export.write_individual:
            return self.ctx.toast(err, "error")
        try:
            plans = plan_notes(cfg, lib)
        except MissingSampleError as exc:
            dlg = MissingSamplesDialog(self, exc.missing, lib.usable_ids())
            if not dlg.exec():
                self.ctx.sound("cancel")
                return self.ctx.toast("Export cancelled: missing samples were not resolved.", "warn")
            self.ctx.config.order.remap.update(dlg.remap())
            self.ctx.touch("order")
            self.sequence_editor.refresh()
            return self.start_export()
        except OrderError as exc:
            return self.ctx.toast(str(exc), "error")
        dest = destination_folder(cfg.export, self.ctx.settings.default_output_dir)
        names = [(p.index, p.name, p.midi, p.sample_id, p.target_hz) for p in plans]
        conflicts = find_conflicts(dest, planned_files(cfg, names))
        overwrite = False
        if conflicts:
            choice = ask_conflict(self, dest, conflicts, unique_destination(dest))
            if choice == "cancel":
                self.ctx.sound("cancel")
                return
            if choice == "new":
                dest = unique_destination(dest)
            else:
                overwrite = True

        def job(progress, cancelled):
            return export_chromatic(cfg, lib, dest, overwrite=overwrite, progress=progress, cancel=cancelled)

        self._export_total = len(plans)
        self._export_stage_name = ""
        self.b_export.setEnabled(False)
        self.b_cancel_export.show()
        self.b_cancel_export.setEnabled(True)
        self.b_open.hide()
        self.export_progress.setValue(0)
        self.export_stage.setText(tr("Exporting · {mode}", mode=tr(cfg.mode.capitalize())))
        self.export_detail.setText(dest.name)
        self.export_detail.setToolTip(str(dest))
        self._elapsed.start()
        self._clock.start()
        self.ctx.set_busy(True)
        self.ctx.sound("export_start")
        t = Task(job, "export", self)
        t.progress.connect(self._export_progress)
        t.succeeded.connect(self._export_ok)
        t.failed.connect(self._export_failed)
        t.cancelled.connect(self._export_cancelled)
        t.finished.connect(self._export_finished)
        self._export_task = t.start()

    def _export_progress(self, stage: str, cur: int, total: int, lbl: str) -> None:
        weights = {"render": (0, 800), "write": (800, 190), "validate": (990, 10)}
        base, span = weights.get(stage, (0, 1000))
        frac = cur / total if total else 1.0
        self.export_progress.setValue(int(base + span * frac))
        name = tr({"render": "Processing", "write": "Writing files", "validate": "Validating"}.get(stage, stage))
        if stage == "render":
            self.export_stage.setText(tr("{stage} · note {n}/{total}", stage=name, n=min(cur + 1, total), total=total))
        else:
            self.export_stage.setText(f"{name} · {min(cur + 1, total)}/{total}")
        self.export_detail.setText(lbl)

    def _tick_clock(self) -> None:
        self.export_time.setText(fmt_time(self._elapsed.elapsed() / 1000.0))

    def cancel_export(self) -> None:
        if self._export_task is None or not self._export_task.running:
            return
        if self.ctx.settings.confirm_on_cancel and not confirm(self, tr("Cancel export"),
                                                               tr("Stop the export? Nothing will be written.")):
            return
        self._export_task.cancel()
        self.b_cancel_export.setEnabled(False)
        self.export_stage.setText(tr("Cancelling…"))

    def _export_ok(self, res) -> None:
        self._last_export = res.folder
        self.export_progress.setValue(1000)
        n_ok = sum(c.ok for c in res.validation.checks)
        self.export_stage.setText(tr("Export complete"))
        warn = (" · " + tr("{n} warning(s)", n=len(res.warnings))) if res.warnings else ""
        self.export_detail.setToolTip(str(res.folder))
        self.export_detail.setText(tr("{folder} · {n} notes · validation {ok}/{total} checks passed",
                                      folder=res.folder.name, n=len(res.generation.notes), ok=n_ok,
                                      total=len(res.validation.checks)) + warn)
        self.b_open.show()
        self.ctx.sound("export_done")
        from ..widgets.notifier import Action
        mode = tr(res.generation.config.mode.capitalize())
        fx = res.generation.config.effects
        if fx.enabled and describe_chain(fx):
            mode += " + " + tr("effects")
        msg = tr("Saved to {folder}", folder=str(res.folder)) + "\n" + tr(
            "{n} notes · {mode} · validation {ok}/{total} passed", n=len(res.generation.notes), mode=mode, ok=n_ok,
            total=len(res.validation.checks))
        if res.warnings:
            msg += "\n⚠ " + tr(res.warnings[0])
        folder = res.folder
        self.ctx.notify("Export complete", msg, "warn" if res.warnings else "ok",
                        [Action(tr("Open folder"), lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))),
                                primary=True)])
        if self.ctx.settings.taskbar_alert_on_finish:
            from PySide6.QtWidgets import QApplication
            QApplication.alert(self.window())

    def _export_failed(self, exc) -> None:
        self.export_stage.setText(tr("Export failed"))
        self.export_detail.setText(str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__)
        self.export_progress.setValue(0)
        self.ctx.sound("error")
        self.ctx.notify("Export failed", str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__, "error")
        if not isinstance(exc, ExportConflict):
            error_details(self, "Export failed", exc)

    def _export_cancelled(self) -> None:
        self.export_stage.setText(tr("Export cancelled"))
        self.export_detail.setText(tr("No files were written."))
        self.export_progress.setValue(0)
        self.ctx.sound("cancel")
        self.ctx.notify("Export cancelled", "No files were written.", "info")

    def _export_finished(self) -> None:
        self._clock.stop()
        self._tick_clock()
        self.b_export.setEnabled(True)
        self.b_cancel_export.hide()
        self.ctx.set_busy(False)

    def open_last_export(self) -> None:
        if self._last_export and self._last_export.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_export)))

    def is_exporting(self) -> bool:
        return self._export_task is not None and self._export_task.running


def _tr_chain(chain: str) -> str:
    return " → ".join(tr(n) for n in chain.split(" → ")) if chain else ""
