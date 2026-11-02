"""快速模式：把传统调色台的直觉参数映射到 Spektrafilm 的原生参数。

设计原则：
- **专业参数为准**：进入快速模式时从当前 GuiState 反推快速滑块；快速滑块
  只写它负责的原生字段，不动其他专业设置。
- **绝对映射 + 安全限**：每个快速滑块有明确中点和安全范围，映射后硬夹住，
  避免一次拖动把画面推到死黑、死白或全灰。
- **可逆**：每个快速滑块都有主原生字段可反推；复合项（锐化/清晰度、颗粒/
  颗粒粗细）按组应用，避免两套值打架。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from spektrafilm_gui.state import GuiState, clone_gui_state


QUICK_GROUPS = (
    (
        '光调',
        (
            'exposure',
            'contrast',
            'shadows',
            'highlights',
            'highlight_rolloff',
            'whites',
            'blacks',
        ),
    ),
    ('色彩', ('saturation', 'temperature', 'tint', 'vibrance')),
    ('质感', ('sharpening', 'clarity', 'grain', 'grain_size')),
)


@dataclass(frozen=True)
class QuickControl:
    name: str
    label: str
    lo: float
    hi: float
    step: float
    decimals: int
    default: float = 0.0
    suffix: str = ''


CONTROLS: dict[str, QuickControl] = {
    'exposure': QuickControl('exposure', '曝光', -2.0, 2.0, 0.05, 2, suffix=' EV'),
    'contrast': QuickControl('contrast', '对比度', -100.0, 100.0, 1.0, 0),
    'shadows': QuickControl('shadows', '阴影', -100.0, 100.0, 1.0, 0),
    'highlights': QuickControl('highlights', '高光', -100.0, 100.0, 1.0, 0),
    'highlight_rolloff': QuickControl('highlight_rolloff', '高光柔和', 0.0, 100.0, 1.0, 0),
    'whites': QuickControl('whites', '白色', -100.0, 100.0, 1.0, 0),
    'blacks': QuickControl('blacks', '黑色', -100.0, 100.0, 1.0, 0),
    'saturation': QuickControl('saturation', '饱和度', -100.0, 100.0, 1.0, 0),
    'temperature': QuickControl('temperature', '色温', -100.0, 100.0, 1.0, 0),
    'tint': QuickControl('tint', '色调', -100.0, 100.0, 1.0, 0),
    'vibrance': QuickControl('vibrance', '自然饱和度', -100.0, 100.0, 1.0, 0),
    'sharpening': QuickControl('sharpening', '锐化', 0.0, 100.0, 1.0, 0),
    'clarity': QuickControl('clarity', '清晰度', -100.0, 100.0, 1.0, 0),
    'grain': QuickControl('grain', '颗粒', 0.0, 100.0, 1.0, 0),
    'grain_size': QuickControl('grain_size', '颗粒粗细', 0.0, 100.0, 1.0, 0),
}


@dataclass(slots=True)
class QuickParams:
    exposure: float = 0.0
    contrast: float = 0.0
    shadows: float = 0.0
    highlights: float = 0.0
    highlight_rolloff: float = 0.0
    whites: float = 0.0
    blacks: float = 0.0
    saturation: float = 0.0
    temperature: float = 0.0
    tint: float = 0.0
    vibrance: float = 0.0
    sharpening: float = 0.0
    clarity: float = 0.0
    grain: float = 0.0
    grain_size: float = 0.0

    def value(self, name: str) -> float:
        return float(getattr(self, name, 0.0))

    def set(self, name: str, value: float) -> None:
        control = CONTROLS[name]
        setattr(self, name, _clamp(value, control.lo, control.hi))


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _signed(value: float) -> float:
    return float(value)


# ── 反推：专业参数 → 快速滑块 ──────────────────────────────────


def quick_from_state(state: GuiState) -> QuickParams:
    quick = QuickParams()
    enlarger = state.simulation.enlarger
    try:
        quick.exposure = _clamp(-_log2(float(enlarger.print_exposure)), -2.0, 2.0)
    except Exception:
        quick.exposure = 0.0

    chemistry = state.chemistry
    quick.contrast = _clamp((float(chemistry.gamma_factor) - 1.0) / 0.25 * 100.0, -100.0, 100.0)
    quick.shadows = _clamp((1.0 - float(chemistry.gamma_factor_fast)) / 0.2 * 100.0, -100.0, 100.0)
    quick.highlights = _clamp((1.0 - float(chemistry.gamma_factor_slow)) / 0.2 * 100.0, -100.0, 100.0)
    quick.highlight_rolloff = _clamp(float(chemistry.developer_exhaustion) / 0.6 * 100.0, 0.0, 100.0)

    scanner = state.scanner
    if scanner.white_correction:
        level = float(scanner.white_level)
        if level >= 0.98:
            quick.whites = _clamp((level - 0.98) / 0.02 * 100.0, -100.0, 100.0)
        else:
            quick.whites = _clamp((level - 0.98) / 0.23 * 100.0, -100.0, 100.0)
    if scanner.black_correction:
        level = float(scanner.black_level)
        if level >= 0.01:
            quick.blacks = _clamp((level - 0.01) / 0.05 * 100.0, -100.0, 100.0)
        else:
            quick.blacks = _clamp((level - 0.01) / 0.008 * 100.0, -100.0, 100.0)

    couplers = state.couplers
    quick.saturation = _clamp((float(couplers.amount) - 1.0) / 0.5 * 100.0, -100.0, 100.0)
    quick.vibrance = _clamp((float(couplers.inhibition_interlayer) - 1.0) / 0.3 * 100.0, -100.0, 100.0)
    quick.temperature = _clamp(float(enlarger.y_filter_shift) / 60.0 * 100.0, -100.0, 100.0)
    quick.tint = _clamp(float(enlarger.m_filter_shift) / 60.0 * 100.0, -100.0, 100.0)

    sigma, amount = scanner.unsharp_mask
    sigma = float(sigma)
    amount = float(amount)
    if sigma > 1.0:
        quick.clarity = _clamp(amount / 0.6 * 100.0, -100.0, 100.0)
        quick.sharpening = 0.0
    else:
        quick.sharpening = _clamp(amount / 1.0 * 100.0, 0.0, 100.0)
        quick.clarity = _clamp(-float(scanner.lens_blur) / 0.8 * 100.0, -100.0, 0.0)

    grain = state.grain
    if grain.active:
        density = float(grain.density_min[0]) if isinstance(grain.density_min, (tuple, list)) else float(grain.density_min)
        quick.grain = _clamp((density - 0.02) / 0.06 * 100.0, 0.0, 100.0)
    quick.grain_size = _clamp((float(grain.particle_area_um2) - 0.05) / 0.75 * 100.0, 0.0, 100.0)
    return quick


def _log2(value: float) -> float:
    import math

    return math.log2(max(value, 1e-9))


# ── 正推：快速滑块 → 专业参数 ──────────────────────────────────


def apply_quick_control(state: GuiState, quick: QuickParams, name: str) -> GuiState:
    """只修改 ``name`` 负责的原生字段，保留其他专业设置。"""
    if name not in CONTROLS:
        return state
    new_state = clone_gui_state(state)
    if name == 'exposure':
        new_state.simulation.enlarger.print_exposure = _clamp(2.0 ** (-float(quick.exposure)), 0.25, 4.0)
    elif name == 'contrast':
        value = float(quick.contrast) / 100.0
        new_state.chemistry = replace(
            new_state.chemistry,
            gamma_factor=_clamp(1.0 + 0.25 * value, 0.75, 1.25),
            active=True,
        )
        new_state.special.film_render.density_curve_gamma = _clamp(1.0 + 0.3 * value, 0.7, 1.3)
    elif name == 'shadows':
        new_state.chemistry = replace(
            new_state.chemistry,
            gamma_factor_fast=_clamp(1.0 - 0.2 * float(quick.shadows) / 100.0, 0.8, 1.2),
            active=True,
        )
    elif name == 'highlights':
        new_state.chemistry = replace(
            new_state.chemistry,
            gamma_factor_slow=_clamp(1.0 - 0.2 * float(quick.highlights) / 100.0, 0.8, 1.2),
            active=True,
        )
    elif name == 'highlight_rolloff':
        new_state.chemistry = replace(
            new_state.chemistry,
            developer_exhaustion=_clamp(0.6 * float(quick.highlight_rolloff) / 100.0, 0.0, 0.6),
            active=True,
        )
    elif name == 'whites':
        whites = float(quick.whites)
        if whites >= 0:
            new_state.scanner.white_level = _clamp(0.98 + 0.02 * whites / 100.0, 0.75, 1.0)
        else:
            new_state.scanner.white_level = _clamp(0.98 - 0.23 * (-whites) / 100.0, 0.75, 1.0)
        new_state.scanner.white_correction = whites != 0.0
    elif name == 'blacks':
        blacks = float(quick.blacks)
        if blacks >= 0:
            new_state.scanner.black_level = _clamp(0.01 + 0.05 * blacks / 100.0, 0.002, 0.06)
        else:
            new_state.scanner.black_level = _clamp(0.01 + 0.008 * blacks / 100.0, 0.002, 0.06)
        new_state.scanner.black_correction = blacks != 0.0
    elif name == 'saturation':
        new_state.couplers.amount = _clamp(1.0 + 0.5 * float(quick.saturation) / 100.0, 0.5, 1.5)
        if quick.saturation != 0.0:
            new_state.couplers.active = True
    elif name == 'vibrance':
        new_state.couplers.inhibition_interlayer = _clamp(
            1.0 + 0.3 * float(quick.vibrance) / 100.0,
            0.7,
            1.3,
        )
        if quick.vibrance != 0.0:
            new_state.couplers.active = True
    elif name == 'temperature':
        new_state.simulation.enlarger.y_filter_shift = _clamp(60.0 * float(quick.temperature) / 100.0, -60.0, 60.0)
    elif name == 'tint':
        new_state.simulation.enlarger.m_filter_shift = _clamp(60.0 * float(quick.tint) / 100.0, -60.0, 60.0)
    elif name in {'sharpening', 'clarity'}:
        _apply_texture(new_state, quick)
    elif name == 'grain':
        _apply_grain_amount(new_state, quick)
    elif name == 'grain_size':
        _apply_grain_size(new_state, quick)
    return new_state


def _apply_texture(state: GuiState, quick: QuickParams) -> None:
    sharp = float(quick.sharpening)
    clarity = float(quick.clarity)
    amount_sharp = 1.0 * sharp / 100.0
    amount_clarity = 0.6 * max(clarity, 0.0) / 100.0
    total = _clamp(amount_sharp + amount_clarity, 0.0, 1.5)
    if total > 0:
        sigma = (0.7 * amount_sharp + 1.5 * amount_clarity) / (amount_sharp + amount_clarity)
    else:
        sigma = 0.7
    state.scanner.unsharp_mask = (float(sigma), float(total))
    state.scanner.lens_blur = _clamp(0.8 * max(-clarity, 0.0) / 100.0, 0.0, 0.8)


def _apply_grain_amount(state: GuiState, quick: QuickParams) -> None:
    amount = _clamp(float(quick.grain), 0.0, 100.0)
    state.grain.active = amount > 0.0
    state.grain.density_min = (
        _clamp(0.02 + 0.06 * amount / 100.0, 0.02, 0.08),
        _clamp(0.02 + 0.06 * amount / 100.0, 0.02, 0.08),
        _clamp(0.02 + 0.06 * amount / 100.0, 0.02, 0.08),
    )
    uniformity = _clamp(0.99 - 0.08 * amount / 100.0, 0.9, 0.99)
    state.grain.uniformity = (uniformity, uniformity, uniformity)


def _apply_grain_size(state: GuiState, quick: QuickParams) -> None:
    size = _clamp(float(quick.grain_size), 0.0, 100.0)
    state.grain.particle_area_um2 = _clamp(0.05 + 0.75 * size / 100.0, 0.05, 0.8)
    state.grain.blur = _clamp(0.3 + 0.8 * size / 100.0, 0.3, 1.1)


__all__ = [
    'CONTROLS',
    'QUICK_GROUPS',
    'QuickControl',
    'QuickParams',
    'apply_quick_control',
    'quick_from_state',
]
