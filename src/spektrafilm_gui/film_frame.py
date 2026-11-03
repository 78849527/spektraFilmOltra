"""胶片边框：把照片合成进模拟胶片的片边 / 相纸留白里。

上游 Spektrafilm 与常见变体都没有内置边框预设，所以这里用纯 numpy
程序化绘制：无边框、白相纸边、黑卡纸边、135 彩色负片、120 卷片、宝丽来。
颜色以 0..1 定义，输出保持调用方传入的 dtype（uint8 / uint16 / float）。

这一层只负责像素合成，不参与显影管线；调色台的交接图始终是未加边框的原始像素。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DEFAULT_FRAME_PRESET = 'paper_white'


@dataclass(frozen=True)
class FramePreset:
    key: str
    name: str
    subtitle: str
    margin: float  # 相对短边的最小留白
    bottom_extra: float = 0.0  # 下边额外留白（宝丽来）
    base: tuple[float, float, float] = (0.96, 0.95, 0.92)
    accent: tuple[float, float, float] = (0.62, 0.52, 0.36)
    style: str = 'plain'  # plain | matte | sprocket | rollfilm | polaroid


FRAME_PRESETS: tuple[FramePreset, ...] = (
    FramePreset('none', '无边框', '保持原始画幅', 0.0, style='none'),
    FramePreset(
        'paper_white',
        '白相纸边',
        '暗房印相留白',
        0.035,
        base=(0.965, 0.955, 0.928),
        accent=(0.70, 0.64, 0.53),
        style='plain',
    ),
    FramePreset(
        'matte_black',
        '黑卡纸边',
        '装裱黑卡纸',
        0.05,
        base=(0.052, 0.052, 0.057),
        accent=(0.17, 0.17, 0.18),
        style='matte',
    ),
    FramePreset(
        'film_135',
        '135 彩色负片',
        '琥珀片基 + 齿孔',
        0.075,
        base=(0.42, 0.24, 0.12),
        accent=(0.88, 0.63, 0.31),
        style='sprocket',
    ),
    FramePreset(
        'film_120',
        '120 卷片',
        '背纸边 + 卷片刻度',
        0.055,
        base=(0.16, 0.15, 0.14),
        accent=(0.74, 0.70, 0.62),
        style='rollfilm',
    ),
    FramePreset(
        'polaroid',
        '宝丽来白框',
        '宽下边拍立得',
        0.04,
        bottom_extra=0.10,
        base=(0.975, 0.967, 0.948),
        accent=(0.78, 0.74, 0.66),
        style='polaroid',
    ),
)

_DEFAULT_PRESET = FRAME_PRESETS[1]

# 齿孔、片边标记等用色，都是在正片/扫描视角下的观感。
_SPROCKET_HOLE_COLOR = (0.93, 0.905, 0.84)
_EDGE_LINE_DARKEN = 0.35


def preset_by_key(key: str) -> FramePreset:
    """按 key 取预设；未知 key 回退到默认预设。"""
    for preset in FRAME_PRESETS:
        if preset.key == key:
            return preset
    return _DEFAULT_PRESET


def preset_names() -> list[tuple[str, str, str]]:
    """给左侧预设台用的 (key, 名称, 副标题)。"""
    return [(preset.key, preset.name, preset.subtitle) for preset in FRAME_PRESETS]


def _dtype_peak(dtype: np.dtype) -> float:
    if np.issubdtype(dtype, np.integer):
        return float(np.iinfo(dtype).max)
    return 1.0


def _to_pixel(color: tuple[float, float, float], dtype: np.dtype) -> np.ndarray:
    values = np.asarray(color, dtype=np.float64)
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        scaled = np.rint(np.clip(values, 0.0, 1.0) * float(info.max))
        return np.clip(scaled, float(info.min), float(info.max)).astype(dtype)
    return np.asarray(np.clip(values, 0.0, 1.0), dtype=dtype)


def _paint_rect(canvas: np.ndarray, y0: int, x0: int, y1: int, x1: int, color: np.ndarray) -> None:
    height, width = canvas.shape[:2]
    y0 = max(0, min(int(y0), height))
    y1 = max(0, min(int(y1), height))
    x0 = max(0, min(int(x0), width))
    x1 = max(0, min(int(x1), width))
    if y1 <= y0 or x1 <= x0:
        return
    channels = canvas.shape[2]
    if color.shape[0] >= channels:
        canvas[y0:y1, x0:x1, :] = color[:channels]
        return
    canvas[y0:y1, x0:x1, : color.shape[0]] = color
    if channels > color.shape[0]:
        canvas[y0:y1, x0:x1, color.shape[0]:] = _dtype_peak(canvas.dtype)


def _draw_sprocket(canvas: np.ndarray, *, margin: int) -> None:
    """135 片边：上下各一排齿孔 + 片边细线。"""
    height, width = canvas.shape[:2]
    hole = _to_pixel(_SPROCKET_HOLE_COLOR, canvas.dtype)
    edge = _to_pixel((0.20, 0.11, 0.05), canvas.dtype)

    hole_height = max(2, int(round(margin * 0.42)))
    hole_width = max(2, int(round(hole_height * 0.75)))
    gap = max(1, int(round(hole_height * 0.85)))
    step = hole_width + gap
    if step <= 0:
        return

    top_center = margin // 2
    bottom_center = height - margin // 2
    start = int(round(step * 0.4))
    for center_x in range(start, width - hole_width, step):
        x0 = center_x - hole_width // 2
        x1 = x0 + hole_width
        _paint_rect(canvas, top_center - hole_height // 2, x0, top_center + (hole_height + 1) // 2, x1, hole)
        _paint_rect(canvas, bottom_center - hole_height // 2, x0, bottom_center + (hole_height + 1) // 2, x1, hole)

    # 片边与画幅之间的细线，让画面边界明确。
    _paint_rect(canvas, margin - 1, 0, margin, width, edge)
    _paint_rect(canvas, height - margin, 0, height - margin + 1, width, edge)


def _draw_rollfilm(canvas: np.ndarray, *, margin: int) -> None:
    """120 背纸：上边一排卷片编号刻度。"""
    height, width = canvas.shape[:2]
    tick = _to_pixel((0.62, 0.58, 0.50), canvas.dtype)
    edge = _to_pixel((0.08, 0.08, 0.07), canvas.dtype)

    tick_height = max(2, int(round(margin * 0.34)))
    tick_width = max(1, int(round(margin * 0.10)))
    step = max(6, int(round(margin * 0.75)))
    y_center = margin // 2
    for x_center in range(int(round(step * 0.5)), width, step):
        x0 = x_center - tick_width // 2
        _paint_rect(canvas, y_center - tick_height // 2, x0, y_center + (tick_height + 1) // 2, x0 + tick_width, tick)

    _paint_rect(canvas, margin - 1, 0, margin, width, edge)
    _paint_rect(canvas, height - margin, 0, height - margin + 1, width, edge)


def _draw_hairline(canvas: np.ndarray, *, top: int, left: int, height: int, width: int) -> None:
    """画幅外沿一圈细线（卡纸 / 宝丽来用）。"""
    line = _to_pixel((0.42, 0.40, 0.36), canvas.dtype)
    _paint_rect(canvas, top - 1, left - 1, top, left + width + 1, line)
    _paint_rect(canvas, top + height, left - 1, top + height + 1, left + width + 1, line)
    _paint_rect(canvas, top, left - 1, top + height, left, line)
    _paint_rect(canvas, top, left + width, top + height, left + width + 1, line)


def apply_frame(image: np.ndarray, key: str = DEFAULT_FRAME_PRESET, *, padding: float = 0.03) -> np.ndarray:
    """把 ``image`` 合成进指定边框，返回新数组（保持输入 dtype）。

    ``padding`` 是「白边」偏好（相对短边），与预设的最小留白取较大值，
    这样预设保证齿孔画得下，用户仍能用滑杆加粗外框。
    """
    data = np.asarray(image)
    preset = preset_by_key(key)
    if preset.key == 'none' or preset.margin <= 0.0:
        return data
    if data.ndim != 3 or data.shape[2] < 3:
        return data

    source_height, source_width = int(data.shape[0]), int(data.shape[1])
    if source_height <= 0 or source_width <= 0:
        return data

    short_edge = min(source_height, source_width)
    margin_ratio = max(float(preset.margin), max(0.0, float(padding)))
    margin = max(1, int(round(short_edge * margin_ratio)))
    bottom = max(1, int(round(short_edge * (margin_ratio + float(preset.bottom_extra)))))
    top_margin = margin

    channels = int(data.shape[2])
    canvas = np.empty(
        (source_height + top_margin + bottom, source_width + margin * 2, channels),
        dtype=data.dtype,
    )
    base = _to_pixel(preset.base, data.dtype)
    canvas[..., :3] = base
    if channels > 3:
        canvas[..., 3:] = _dtype_peak(data.dtype)

    left = margin
    top = top_margin
    canvas[top:top + source_height, left:left + source_width, :] = data

    if preset.style == 'sprocket':
        _draw_sprocket(canvas, margin=margin)
    elif preset.style == 'rollfilm':
        _draw_rollfilm(canvas, margin=margin)
    elif preset.style == 'matte':
        _draw_hairline(canvas, top=top, left=left, height=source_height, width=source_width)
    elif preset.style == 'polaroid':
        _draw_hairline(canvas, top=top, left=left, height=source_height, width=source_width)

    return canvas
