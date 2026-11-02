"""快速模式的控制声明与映射规则。

设计约束：
- 只写「自己拥有」的原生字段，跨控制在路径上互不重叠。
- 每个轴都以工程进入时的 native baseline 为 0 点；q=0 逐位保持不变。
- 所有映射结果在写回前硬夹到安全范围，不允许把画面推到全黑/全白。
- 本模块是纯函数，不导入 Qt，也不导入 GUI state 之外的运行时对象。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class QuickAxis:
    name: str
    label: str
    lo: float
    hi: float
    step: float
    decimals: int
    suffix: str
    owned: tuple[str, ...]
    tooltip: str


AXES: dict[str, QuickAxis] = {
    'camera_exposure': QuickAxis(
        'camera_exposure',
        '拍摄曝光',
        -3.0,
        3.0,
        0.1,
        1,
        ' EV',
        ('camera.exposure_compensation_ev', 'simulation.enlarger.print_exposure_compensation'),
        '进入胶片前的拍摄曝光补偿。自动测光开启时仍叠加；拖动时会暂时关闭印相自动亮度补偿，让曝光直接可见，回到 0 时恢复原设置。',
    ),
    'print_brightness': QuickAxis(
        'print_brightness',
        '印相明暗',
        -2.0,
        2.0,
        0.05,
        2,
        ' EV',
        ('simulation.enlarger.print_exposure',),
        '放大机印相曝光。正值为更亮的照片，负值为更暗；围绕当前工程的印相基线调整。',
    ),
    'tonal_contrast': QuickAxis(
        'tonal_contrast',
        '影调反差',
        -100.0,
        100.0,
        1.0,
        0,
        '',
        ('chemistry.gamma_factor', 'chemistry.active'),
        '围绕中灰的印相密度曲线反差。只动显影曲线形态，不动底片密度曲线。',
    ),
    'print_balance_y': QuickAxis(
        'print_balance_y',
        '暖冷',
        -100.0,
        100.0,
        1.0,
        0,
        '',
        ('simulation.enlarger.y_filter_shift',),
        '放大机黄滤镜位移（Kodak CC）。方向在灰卡标定后锁定；当前正值按冷、负值按暖验证。',
    ),
    'print_balance_m': QuickAxis(
        'print_balance_m',
        '品红 / 绿',
        -100.0,
        100.0,
        1.0,
        0,
        '',
        ('simulation.enlarger.m_filter_shift',),
        '放大机品红滤镜位移（Kodak CC）。方向在灰卡标定后锁定；当前正值按品红、负值按绿验证。',
    ),
    'color_density': QuickAxis(
        'color_density',
        '色彩浓度',
        -100.0,
        100.0,
        1.0,
        0,
        '',
        ('couplers.inhibition_interlayer', 'couplers.active'),
        'DIR 成色剂的层间抑制。只影响颜色之间的串扰与浓度，不同时改变各层自身的反差。',
    ),
    'grain_amount': QuickAxis(
        'grain_amount',
        '颗粒强度',
        -100.0,
        100.0,
        1.0,
        0,
        '',
        ('grain.active', 'grain.density_min', 'grain.uniformity'),
        '颗粒密度地板与均匀度。-100 关闭颗粒；0 保持当前胶片基线。',
    ),
    'grain_size': QuickAxis(
        'grain_size',
        '颗粒尺寸',
        -100.0,
        100.0,
        1.0,
        0,
        '',
        ('grain.particle_area_um2', 'grain.blur'),
        '颗粒面积（与 ISO/粒子数相关）与颗粒边缘柔化。正值为更大、更明显的颗粒。',
    ),
    'halation_amount': QuickAxis(
        'halation_amount',
        '光晕强度',
        -100.0,
        100.0,
        1.0,
        0,
        '',
        ('halation.active', 'halation.halation_amount'),
        '片基背反射光晕的强度。-100 关闭光晕；0 保持胶片基线。乳剂内散射仍由专业页控制。',
    ),
    'halation_scale': QuickAxis(
        'halation_scale',
        '光晕范围',
        -100.0,
        100.0,
        1.0,
        0,
        '',
        ('halation.halation_spatial_scale',),
        '光晕第一跳的空间尺度。正值为更大范围的红晕，负值为更紧凑。',
    ),
    'diffusion': QuickAxis(
        'diffusion',
        '光学柔化',
        -100.0,
        100.0,
        1.0,
        0,
        '',
        ('camera_diffusion.active', 'camera_diffusion.strength'),
        '相机端柔光镜（Pro-Mist 家族）。正值增强高光扩散；负值只在基线已开启柔光时减弱；-100 关闭。',
    ),
    'scanner_clarity': QuickAxis(
        'scanner_clarity',
        '扫描清晰度',
        -100.0,
        100.0,
        1.0,
        0,
        '',
        ('scanner.unsharp_mask', 'scanner.lens_blur'),
        '扫描端清晰度。正半轴提高 USM 强度，负半轴增加扫描镜头模糊；0 保持当前扫描基线。',
    ),
}


# UI 布局：('axis', 轴名) 或 ('pad', 组名, 标签, (x 轴, y 轴))。
QUICK_LAYOUT: tuple[tuple[str, tuple[tuple[Any, ...], ...]], ...] = (
    (
        '光调',
        (
            ('axis', 'camera_exposure'),
            ('axis', 'print_brightness'),
            ('axis', 'tonal_contrast'),
        ),
    ),
    (
        '色彩',
        (
            ('pad', '印相色彩', ('print_balance_y', 'print_balance_m')),
            ('axis', 'color_density'),
        ),
    ),
    (
        '质感',
        (
            ('axis', 'grain_amount'),
            ('axis', 'grain_size'),
            ('axis', 'halation_amount'),
            ('axis', 'halation_scale'),
            ('axis', 'diffusion'),
            ('axis', 'scanner_clarity'),
        ),
    ),
)


PRINT_ONLY_AXES = frozenset({
    'print_brightness',
    'tonal_contrast',
    'print_balance_y',
    'print_balance_m',
})

DISABLED_REASON = '正片扫描模式：管线跳过印相阶段，本项不参与成像'


def disabled_axes(*, scan_film: bool) -> frozenset[str]:
    return PRINT_ONLY_AXES if scan_film else frozenset()


def empty_intent() -> dict[str, float]:
    return {name: 0.0 for name in AXES}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _number(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _tuple_number(value: Any, size: int, fallback: float) -> tuple[float, ...]:
    try:
        values = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        values = ()
    if len(values) != size:
        values = (fallback,) * size
    return values


def _baseline_value(baseline: Mapping[str, Any], path: str) -> Any:
    try:
        return baseline[path]
    except KeyError:
        raise KeyError(f'quick baseline missing path: {path}') from None


def expected_values(axis: QuickAxis, q: float, baseline: Mapping[str, Any]) -> dict[str, Any]:
    """返回该轴在 q 处应写入的全部原生字段值（未落盘，纯计算）。"""
    q = _clamp(q, axis.lo, axis.hi)
    name = axis.name

    # 0 点必须逐位恢复基线：任何夹紧都可能把越界的专业基线拉回，从而误判 Custom。
    if abs(q) <= 1e-9:
        return {path: _baseline_value(baseline, path) for path in axis.owned}

    if name == 'camera_exposure':
        base = _number(_baseline_value(baseline, 'camera.exposure_compensation_ev'))
        base_compensation = bool(
            _baseline_value(baseline, 'simulation.enlarger.print_exposure_compensation')
        )
        return {
            'camera.exposure_compensation_ev': _clamp(base + q, -5.0, 5.0),
            'simulation.enlarger.print_exposure_compensation': (
                base_compensation if abs(q) <= 1e-9 else False
            ),
        }

    if name == 'print_brightness':
        base = _number(_baseline_value(baseline, 'simulation.enlarger.print_exposure'), 1.0)
        return {
            'simulation.enlarger.print_exposure': _clamp(base * 2.0 ** (-q), 0.25, 4.0),
        }

    if name == 'tonal_contrast':
        base = _number(_baseline_value(baseline, 'chemistry.gamma_factor'), 1.0)
        base_active = bool(_baseline_value(baseline, 'chemistry.active'))
        return {
            'chemistry.gamma_factor': _clamp(base * (1.0 + 0.35 * q / 100.0), 0.5, 2.0),
            'chemistry.active': True if abs(q) > 1e-9 else base_active,
        }

    if name == 'print_balance_y':
        base = _number(_baseline_value(baseline, 'simulation.enlarger.y_filter_shift'))
        return {
            'simulation.enlarger.y_filter_shift': _clamp(base + 60.0 * q / 100.0, -60.0, 60.0),
        }

    if name == 'print_balance_m':
        base = _number(_baseline_value(baseline, 'simulation.enlarger.m_filter_shift'))
        return {
            'simulation.enlarger.m_filter_shift': _clamp(base + 60.0 * q / 100.0, -60.0, 60.0),
        }

    if name == 'color_density':
        base = _number(_baseline_value(baseline, 'couplers.inhibition_interlayer'), 1.0)
        base_active = bool(_baseline_value(baseline, 'couplers.active'))
        return {
            'couplers.inhibition_interlayer': _clamp(base * (1.0 + 0.5 * q / 100.0), 0.0, 1.5),
            'couplers.active': True if abs(q) > 1e-9 else base_active,
        }

    if name == 'grain_amount':
        density = _tuple_number(
            _baseline_value(baseline, 'grain.density_min'), 3, 0.03
        )
        uniformity = _tuple_number(
            _baseline_value(baseline, 'grain.uniformity'), 3, 0.97
        )
        base_active = bool(_baseline_value(baseline, 'grain.active'))
        density = tuple(
            _clamp(value * (1.0 + 0.9 * q / 100.0), 0.005, 0.08)
            for value in density
        )
        uniformity = tuple(
            _clamp(value - 0.06 * q / 100.0, 0.90, 0.995)
            for value in uniformity
        )
        return {
            'grain.active': False if q <= -99.0 else base_active,
            'grain.density_min': density,
            'grain.uniformity': uniformity,
        }

    if name == 'grain_size':
        area = _number(_baseline_value(baseline, 'grain.particle_area_um2'), 0.2)
        blur = _number(_baseline_value(baseline, 'grain.blur'), 0.65)
        return {
            'grain.particle_area_um2': _clamp(area * 2.0 ** (0.9 * q / 100.0), 0.02, 0.8),
            'grain.blur': _clamp(blur * (1.0 + 0.25 * q / 100.0), 0.0, 1.5),
        }

    if name == 'halation_amount':
        base = _number(_baseline_value(baseline, 'halation.halation_amount'), 1.0)
        base_active = bool(_baseline_value(baseline, 'halation.active'))
        return {
            'halation.active': False if q <= -99.0 else base_active,
            'halation.halation_amount': _clamp(base * (1.0 + 1.2 * q / 100.0), 0.0, 2.0),
        }

    if name == 'halation_scale':
        base = _number(_baseline_value(baseline, 'halation.halation_spatial_scale'), 1.0)
        return {
            'halation.halation_spatial_scale': _clamp(
                base * 2.0 ** (0.6 * q / 100.0), 0.5, 2.5
            ),
        }

    if name == 'diffusion':
        base_active = bool(_baseline_value(baseline, 'camera_diffusion.active'))
        base_strength = _number(_baseline_value(baseline, 'camera_diffusion.strength'), 0.5)
        if q > 0.0:
            strength = base_strength + (2.0 - base_strength) * q / 100.0
        elif q < 0.0:
            strength = base_strength * (1.0 + q / 100.0)
        else:
            strength = base_strength
        active = base_active or q > 0.0
        if q <= -99.0:
            active = False
        return {
            'camera_diffusion.active': active,
            'camera_diffusion.strength': _clamp(strength, 0.0, 2.0),
        }

    if name == 'scanner_clarity':
        sigma, amount = _tuple_number(
            _baseline_value(baseline, 'scanner.unsharp_mask'), 2, 0.7
        )
        lens_blur = _number(_baseline_value(baseline, 'scanner.lens_blur'), 0.0)
        if q >= 0.0:
            amount = amount + (1.8 - amount) * q / 100.0
        else:
            lens_blur = lens_blur + 0.6 * (-q) / 100.0
        return {
            'scanner.unsharp_mask': (float(sigma), _clamp(amount, 0.0, 2.0)),
            'scanner.lens_blur': _clamp(lens_blur, 0.0, 0.8),
        }

    raise KeyError(f'unknown quick axis: {name}')


__all__ = [
    'AXES',
    'DISABLED_REASON',
    'PRINT_ONLY_AXES',
    'QUICK_LAYOUT',
    'QuickAxis',
    'disabled_axes',
    'empty_intent',
    'expected_values',
]
