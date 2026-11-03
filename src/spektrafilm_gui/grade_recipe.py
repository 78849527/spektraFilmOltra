"""调色台配方：Lightroom 式影调、色彩、通透、画质与光学参数。

配方是纯数据对象，不依赖 Qt 或图像库；引擎只读取它，UI 只写入它。
所有字段默认中性，默认配方除了色彩空间转换之外不改变交接图。

序列化策略：未知键忽略、缺失键取默认、越界钳位、类型错误回退默认。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1

HSL_BAND_NAMES = (
    'red',
    'orange',
    'yellow',
    'green',
    'aqua',
    'blue',
    'purple',
    'magenta',
)
HSL_BAND_LABELS = ('红', '橙', '黄', '绿', '青', '蓝', '紫', '品红')
HSL_BAND_HUES = (358.0, 25.0, 60.0, 115.0, 180.0, 225.0, 280.0, 330.0)

GRADE_ZONE_NAMES = ('shadows', 'midtones', 'highlights')
GRADE_ZONE_LABELS = ('阴影', '中间调', '高光')


# ── 校验 helper ──────────────────────────────────────────────────


def _number(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(number):
        return float(default)
    return float(max(minimum, min(maximum, number)))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any, default: str = '') -> str:
    if isinstance(value, str):
        return value.strip()
    return default


# ── 子结构 ───────────────────────────────────────────────────────


@dataclass(slots=True)
class LightRecipe:
    exposure: float = 0.0
    contrast: float = 0.0
    highlights: float = 0.0
    shadows: float = 0.0
    whites: float = 0.0
    blacks: float = 0.0
    midtones: float = 0.0
    highlight_rolloff: float = 0.0
    curve_highlights: float = 0.0
    curve_lights: float = 0.0
    curve_darks: float = 0.0
    curve_shadows: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            'exposure': float(self.exposure),
            'contrast': float(self.contrast),
            'highlights': float(self.highlights),
            'shadows': float(self.shadows),
            'whites': float(self.whites),
            'blacks': float(self.blacks),
            'midtones': float(self.midtones),
            'highlight_rolloff': float(self.highlight_rolloff),
            'curve_highlights': float(self.curve_highlights),
            'curve_lights': float(self.curve_lights),
            'curve_darks': float(self.curve_darks),
            'curve_shadows': float(self.curve_shadows),
        }

    @classmethod
    def from_dict(cls, data: Any) -> 'LightRecipe':
        source = _mapping(data)
        return cls(
            exposure=_number(source.get('exposure'), 0.0, -5.0, 5.0),
            contrast=_number(source.get('contrast'), 0.0, -100.0, 100.0),
            highlights=_number(source.get('highlights'), 0.0, -100.0, 100.0),
            shadows=_number(source.get('shadows'), 0.0, -100.0, 100.0),
            whites=_number(source.get('whites'), 0.0, -100.0, 100.0),
            blacks=_number(source.get('blacks'), 0.0, -100.0, 100.0),
            midtones=_number(source.get('midtones'), 0.0, -100.0, 100.0),
            highlight_rolloff=_number(source.get('highlight_rolloff'), 0.0, 0.0, 100.0),
            curve_highlights=_number(source.get('curve_highlights'), 0.0, -100.0, 100.0),
            curve_lights=_number(source.get('curve_lights'), 0.0, -100.0, 100.0),
            curve_darks=_number(source.get('curve_darks'), 0.0, -100.0, 100.0),
            curve_shadows=_number(source.get('curve_shadows'), 0.0, -100.0, 100.0),
        )


@dataclass(slots=True)
class HslBand:
    hue: float = 0.0
    saturation: float = 0.0
    luminance: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            'hue': float(self.hue),
            'saturation': float(self.saturation),
            'luminance': float(self.luminance),
        }

    @classmethod
    def from_dict(cls, data: Any) -> 'HslBand':
        source = _mapping(data)
        return cls(
            hue=_number(source.get('hue'), 0.0, -100.0, 100.0),
            saturation=_number(source.get('saturation'), 0.0, -100.0, 100.0),
            luminance=_number(source.get('luminance'), 0.0, -100.0, 100.0),
        )


@dataclass(slots=True)
class GradeZone:
    hue: float = 0.0
    saturation: float = 0.0
    luminance: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            'hue': float(self.hue),
            'saturation': float(self.saturation),
            'luminance': float(self.luminance),
        }

    @classmethod
    def from_dict(cls, data: Any) -> 'GradeZone':
        source = _mapping(data)
        return cls(
            hue=_number(source.get('hue'), 0.0, 0.0, 360.0),
            saturation=_number(source.get('saturation'), 0.0, 0.0, 100.0),
            luminance=_number(source.get('luminance'), 0.0, -100.0, 100.0),
        )


@dataclass(slots=True)
class ColorGrading:
    shadows: GradeZone = field(default_factory=GradeZone)
    midtones: GradeZone = field(default_factory=GradeZone)
    highlights: GradeZone = field(default_factory=GradeZone)
    blending: float = 50.0
    balance: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            'shadows': self.shadows.to_dict(),
            'midtones': self.midtones.to_dict(),
            'highlights': self.highlights.to_dict(),
            'blending': float(self.blending),
            'balance': float(self.balance),
        }

    @classmethod
    def from_dict(cls, data: Any) -> 'ColorGrading':
        source = _mapping(data)
        return cls(
            shadows=GradeZone.from_dict(source.get('shadows')),
            midtones=GradeZone.from_dict(source.get('midtones')),
            highlights=GradeZone.from_dict(source.get('highlights')),
            blending=_number(source.get('blending'), 50.0, 0.0, 100.0),
            balance=_number(source.get('balance'), 0.0, -100.0, 100.0),
        )


@dataclass(slots=True)
class ColorRecipe:
    temperature: float = 0.0
    tint: float = 0.0
    vibrance: float = 0.0
    saturation: float = 0.0
    hue_shift: float = 0.0
    color_density: float = 0.0
    hsl: list[HslBand] = field(default_factory=lambda: [HslBand() for _ in HSL_BAND_NAMES])
    grading: ColorGrading = field(default_factory=ColorGrading)

    def band(self, index: int) -> HslBand:
        return self.hsl[max(0, min(len(self.hsl) - 1, int(index)))]

    def to_dict(self) -> dict[str, Any]:
        return {
            'temperature': float(self.temperature),
            'tint': float(self.tint),
            'vibrance': float(self.vibrance),
            'saturation': float(self.saturation),
            'hue_shift': float(self.hue_shift),
            'color_density': float(self.color_density),
            'hsl': [band.to_dict() for band in self.hsl],
            'grading': self.grading.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Any) -> 'ColorRecipe':
        source = _mapping(data)
        raw_hsl = source.get('hsl')
        bands: list[HslBand] = []
        if isinstance(raw_hsl, Sequence) and not isinstance(raw_hsl, (str, bytes)):
            for item in list(raw_hsl)[: len(HSL_BAND_NAMES)]:
                bands.append(HslBand.from_dict(item))
        while len(bands) < len(HSL_BAND_NAMES):
            bands.append(HslBand())
        return cls(
            temperature=_number(source.get('temperature'), 0.0, -100.0, 100.0),
            tint=_number(source.get('tint'), 0.0, -100.0, 100.0),
            vibrance=_number(source.get('vibrance'), 0.0, -100.0, 100.0),
            saturation=_number(source.get('saturation'), 0.0, -100.0, 100.0),
            hue_shift=_number(source.get('hue_shift'), 0.0, -180.0, 180.0),
            color_density=_number(source.get('color_density'), 0.0, 0.0, 100.0),
            hsl=bands,
            grading=ColorGrading.from_dict(source.get('grading')),
        )


@dataclass(slots=True)
class TransparencyRecipe:
    tonal: float = 0.0
    color: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {'tonal': float(self.tonal), 'color': float(self.color)}

    @classmethod
    def from_dict(cls, data: Any) -> 'TransparencyRecipe':
        source = _mapping(data)
        return cls(
            tonal=_number(source.get('tonal'), 0.0, 0.0, 100.0),
            color=_number(source.get('color'), 0.0, 0.0, 100.0),
        )


@dataclass(slots=True)
class QualityRecipe:
    clarity: float = 0.0
    texture: float = 0.0
    dehaze: float = 0.0
    sharpen_amount: float = 0.0
    sharpen_radius: float = 1.0
    sharpen_threshold: float = 0.0
    noise_luminance: float = 0.0
    noise_color: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            'clarity': float(self.clarity),
            'texture': float(self.texture),
            'dehaze': float(self.dehaze),
            'sharpen_amount': float(self.sharpen_amount),
            'sharpen_radius': float(self.sharpen_radius),
            'sharpen_threshold': float(self.sharpen_threshold),
            'noise_luminance': float(self.noise_luminance),
            'noise_color': float(self.noise_color),
        }

    @classmethod
    def from_dict(cls, data: Any) -> 'QualityRecipe':
        source = _mapping(data)
        return cls(
            clarity=_number(source.get('clarity'), 0.0, -100.0, 100.0),
            texture=_number(source.get('texture'), 0.0, -100.0, 100.0),
            dehaze=_number(source.get('dehaze'), 0.0, -100.0, 100.0),
            sharpen_amount=_number(source.get('sharpen_amount'), 0.0, 0.0, 100.0),
            sharpen_radius=_number(source.get('sharpen_radius'), 1.0, 0.5, 3.0),
            sharpen_threshold=_number(source.get('sharpen_threshold'), 0.0, 0.0, 100.0),
            noise_luminance=_number(source.get('noise_luminance'), 0.0, 0.0, 100.0),
            noise_color=_number(source.get('noise_color'), 0.0, 0.0, 100.0),
        )


@dataclass(slots=True)
class OpticsRecipe:
    vignette_amount: float = 0.0
    vignette_midpoint: float = 50.0
    vignette_roundness: float = 0.0
    vignette_feather: float = 50.0
    grain_amount: float = 0.0
    grain_size: float = 25.0
    grain_roughness: float = 50.0
    chromatic_aberration: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            'vignette_amount': float(self.vignette_amount),
            'vignette_midpoint': float(self.vignette_midpoint),
            'vignette_roundness': float(self.vignette_roundness),
            'vignette_feather': float(self.vignette_feather),
            'grain_amount': float(self.grain_amount),
            'grain_size': float(self.grain_size),
            'grain_roughness': float(self.grain_roughness),
            'chromatic_aberration': float(self.chromatic_aberration),
        }

    @classmethod
    def from_dict(cls, data: Any) -> 'OpticsRecipe':
        source = _mapping(data)
        return cls(
            vignette_amount=_number(source.get('vignette_amount'), 0.0, -100.0, 100.0),
            vignette_midpoint=_number(source.get('vignette_midpoint'), 50.0, 0.0, 100.0),
            vignette_roundness=_number(source.get('vignette_roundness'), 0.0, -100.0, 100.0),
            vignette_feather=_number(source.get('vignette_feather'), 50.0, 0.0, 100.0),
            grain_amount=_number(source.get('grain_amount'), 0.0, 0.0, 100.0),
            grain_size=_number(source.get('grain_size'), 25.0, 0.0, 100.0),
            grain_roughness=_number(source.get('grain_roughness'), 50.0, 0.0, 100.0),
            chromatic_aberration=_number(source.get('chromatic_aberration'), 0.0, 0.0, 100.0),
        )


@dataclass(slots=True)
class LutRecipe:
    path: str = ''
    strength: float = 100.0

    def to_dict(self) -> dict[str, Any]:
        return {'path': self.path, 'strength': float(self.strength)}

    @classmethod
    def from_dict(cls, data: Any) -> 'LutRecipe':
        source = _mapping(data)
        return cls(
            path=_text(source.get('path')),
            strength=_number(source.get('strength'), 100.0, 0.0, 100.0),
        )


# ── 顶层配方 ─────────────────────────────────────────────────────


@dataclass(slots=True)
class GradeRecipe:
    schema: int = SCHEMA_VERSION
    light: LightRecipe = field(default_factory=LightRecipe)
    color: ColorRecipe = field(default_factory=ColorRecipe)
    transparency: TransparencyRecipe = field(default_factory=TransparencyRecipe)
    quality: QualityRecipe = field(default_factory=QualityRecipe)
    optics: OpticsRecipe = field(default_factory=OpticsRecipe)
    lut: LutRecipe = field(default_factory=LutRecipe)

    def to_dict(self) -> dict[str, Any]:
        return {
            'schema': int(self.schema),
            'light': self.light.to_dict(),
            'color': self.color.to_dict(),
            'transparency': self.transparency.to_dict(),
            'quality': self.quality.to_dict(),
            'optics': self.optics.to_dict(),
            'lut': self.lut.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Any) -> 'GradeRecipe':
        source = _mapping(data)
        try:
            schema = max(0, min(SCHEMA_VERSION, int(source.get('schema', SCHEMA_VERSION))))
        except (TypeError, ValueError):
            schema = SCHEMA_VERSION
        return cls(
            schema=schema,
            light=LightRecipe.from_dict(source.get('light')),
            color=ColorRecipe.from_dict(source.get('color')),
            transparency=TransparencyRecipe.from_dict(source.get('transparency')),
            quality=QualityRecipe.from_dict(source.get('quality')),
            optics=OpticsRecipe.from_dict(source.get('optics')),
            lut=LutRecipe.from_dict(source.get('lut')),
        )

    def clone(self) -> 'GradeRecipe':
        return GradeRecipe.from_dict(self.to_dict())

    def is_identity(self) -> bool:
        return self.to_dict() == GradeRecipe().to_dict()

    def dirty_count(self) -> int:
        """返回非中性参数数量，用于 UI 徽标与测试。"""
        neutral = GradeRecipe()
        count = 0
        for section_name in ('light', 'color', 'transparency', 'quality', 'optics', 'lut'):
            current = getattr(self, section_name).to_dict()
            reference = getattr(neutral, section_name).to_dict()
            if section_name == 'color':
                if current.get('hsl') != reference.get('hsl'):
                    count += _hsl_dirty_count(current.get('hsl'), reference.get('hsl'))
                    current = {k: v for k, v in current.items() if k != 'hsl'}
                    reference = {k: v for k, v in reference.items() if k != 'hsl'}
                if current.get('grading') != reference.get('grading'):
                    count += _grading_dirty_count(current.get('grading'), reference.get('grading'))
                    current = {k: v for k, v in current.items() if k != 'grading'}
                    reference = {k: v for k, v in reference.items() if k != 'grading'}
            for key, value in current.items():
                if value != reference.get(key):
                    count += 1
        return count


def _hsl_dirty_count(current: Any, reference: Any) -> int:
    count = 0
    if not isinstance(current, list) or not isinstance(reference, list):
        return 0
    for band, base in zip(current, reference):
        if not isinstance(band, Mapping) or not isinstance(base, Mapping):
            continue
        for key in ('hue', 'saturation', 'luminance'):
            if band.get(key) != base.get(key):
                count += 1
    return count


def _grading_dirty_count(current: Any, reference: Any) -> int:
    count = 0
    if not isinstance(current, Mapping) or not isinstance(reference, Mapping):
        return 0
    for key in ('shadows', 'midtones', 'highlights'):
        zone = current.get(key)
        base = reference.get(key)
        if not isinstance(zone, Mapping) or not isinstance(base, Mapping):
            continue
        for field_name in ('hue', 'saturation', 'luminance'):
            if zone.get(field_name) != base.get(field_name):
                count += 1
    for key in ('blending', 'balance'):
        if current.get(key) != reference.get(key):
            count += 1
    return count


__all__ = [
    'ColorGrading',
    'ColorRecipe',
    'GRADE_ZONE_LABELS',
    'GRADE_ZONE_NAMES',
    'GradeRecipe',
    'GradeZone',
    'HSL_BAND_HUES',
    'HSL_BAND_LABELS',
    'HSL_BAND_NAMES',
    'HslBand',
    'LightRecipe',
    'LutRecipe',
    'OpticsRecipe',
    'QualityRecipe',
    'SCHEMA_VERSION',
    'TransparencyRecipe',
]
