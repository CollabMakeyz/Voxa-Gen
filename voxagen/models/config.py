from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MusicalSettings:
    start_note: int = 0
    start_octave: int = 2
    semitones: int = 36
    a4_hz: float = 440.0
    temperament: str = "equal"
    temperament_root: int = 0
    custom_cents: list[float] = field(default_factory=lambda: [0.0] * 12)
    retune: bool = True


ORDER_MODES = ("sequential", "shuffle", "random", "vocal")


@dataclass
class OrderSettings:
    mode: str = "sequential"
    use_seed: bool = False
    seed: int = 1234
    sequence: list[str] = field(default_factory=list)
    sequence_name: str = ""
    remap: dict[str, str] = field(default_factory=dict)


EXPORT_MODES = ("natural", "robot", "legacy", "lab")


@dataclass
class NaturalParams:
    auto: bool = True
    formant_preservation: float = 1.0
    pitch_accuracy: float = 1.0
    humanization: float = 0.0
    humanization_max_cents: float = 15.0
    transient_preservation: float = 0.5
    transient_window_ms: float = 25.0
    smoothing: float = 0.3
    artifact_reduction: float = 0.5
    vuv_processing: bool = True
    unvoiced_mix: float = 1.0
    quality: str = "high"
    resampling_quality: str = "vhq"
    wet: float = 1.0
    gain_compensation: bool = True
    f0_floor: float = 50.0
    f0_ceil: float = 1100.0
    tools_enabled: dict[str, bool] = field(default_factory=dict)

    def tool_on(self, key: str) -> bool:
        return bool(self.tools_enabled.get(key, True))

    def effective(self) -> "NaturalParams":
        from dataclasses import replace
        p = replace(self, tools_enabled=dict(self.tools_enabled))
        if not self.tool_on("humanization"):
            p.humanization = 0.0
        if not self.tool_on("formant_preservation"):
            p.formant_preservation = 0.0
        if not self.tool_on("transient"):
            p.transient_preservation = 0.0
        if not self.tool_on("smoothing"):
            p.smoothing = 0.0
        if not self.tool_on("artifact_reduction"):
            p.artifact_reduction = 0.0
        if not self.tool_on("vuv"):
            p.vuv_processing = False
        return p


LAB_TOOLS = ("pitch_correction", "humanization", "formant_preservation", "transient", "smoothing",
             "artifact_reduction", "vuv")


@dataclass
class RobotParams:
    frame_period_ms: float = 10.0
    resampling_quality: str = "mq"
    gain_compensation: bool = False


@dataclass
class LegacyParams:
    internal_rate: int = 48000
    time_step: float = 0.03
    pitch_floor: float = 20.0
    pitch_ceiling: float = 1200.0


BIT_DEPTHS = ("pcm16", "pcm24", "float32")
FIT_MODES = ("pad_trim", "pad_only", "stretch")


@dataclass
class ExportSettings:
    sample_rate: int = 48000
    bit_depth: str = "pcm16"
    channels: str = "mono"
    normalize: bool = False
    normalize_mode: str = "global"
    normalize_peak_db: float = -0.3
    fade_in_ms: float = 0.0
    fade_out_ms: float = 0.0
    gap_ms: float = 300.0
    fixed_duration: bool = False
    fixed_duration_ms: float = 1000.0
    fit_mode: str = "pad_trim"
    master_volume_db: float = 0.0
    prevent_clipping: bool = True
    dither: bool = True
    trim_silence: bool = False
    trim_threshold_db: float = -50.0
    markers: bool = True
    write_chromatic: bool = True
    write_individual: bool = True
    output_dir: str = ""
    folder_name: str = "Voxa GEN Export"
    chromatic_name: str = "chromatic"
    note_name_template: str = "note_{index:03d}"
    samples_subfolder: str = "samples"


@dataclass
class EffectSlot:
    effect: str = "eq"
    enabled: bool = True
    mix: float = 1.0
    params: dict = field(default_factory=dict)


@dataclass
class EffectsSettings:
    enabled: bool = False
    chain: list[EffectSlot] = field(default_factory=list)
    preset_name: str = ""
    seed: int = 7


@dataclass
class GeneratorConfig:
    musical: MusicalSettings = field(default_factory=MusicalSettings)
    order: OrderSettings = field(default_factory=OrderSettings)
    export: ExportSettings = field(default_factory=ExportSettings)
    mode: str = "natural"
    natural: NaturalParams = field(default_factory=NaturalParams)
    robot: RobotParams = field(default_factory=RobotParams)
    legacy: LegacyParams = field(default_factory=LegacyParams)
    lab: NaturalParams = field(default_factory=NaturalParams)
    lab_profile_name: str = ""
    sample_folder: str = ""
    sample_paths: list[str] = field(default_factory=list)
    disabled_samples: list[str] = field(default_factory=list)
    effects: EffectsSettings = field(default_factory=EffectsSettings)
