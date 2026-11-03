"""调色台引擎：把线性 ProPhoto 交接图渲染成 sRGB 显示图。

算法参考：
- oflim ``Shaders.metal`` 的明暗通透（直方图黑/白场 Levels）与颜色通透
  （高光/阴影互补色中和）
- RapidRAW 的对比度、阴影/黑场、饱和度、HSL 8 色带、clarity/structure、
  去雾、两尺度 USM 与暗角公式

所有步骤都在 NumPy/SciPy 内完成，默认配方只做色彩空间转换。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Sequence

import numpy as np
from scipy.ndimage import map_coordinates, minimum_filter, uniform_filter

from spektrafilm_gui.grade_recipe import (
    ColorRecipe,
    GradeRecipe,
    HSL_BAND_HUES,
    LightRecipe,
    OpticsRecipe,
    QualityRecipe,
    TransparencyRecipe,
)

LUMA_REC709 = np.array((0.2126, 0.7152, 0.0722), dtype=np.float32)
_BAND_CENTERS = np.array(HSL_BAND_HUES, dtype=np.float32)

@lru_cache(maxsize=1)
def _prophoto_to_srgb_matrix() -> np.ndarray:
    """线性 ProPhoto → 线性 sRGB；与 develop 预览使用同一套 colour 转换。"""
    import colour

    return np.asarray(
        colour.matrix_RGB_to_RGB('ProPhoto RGB', 'sRGB'),
        dtype=np.float32,
    )

TRANSPARENCY_EDGE_PERCENT = 0.4


@dataclass(frozen=True, slots=True)
class ToneAnalysis:
    black_point: float
    white_point: float
    highlight_rgb: tuple[float, float, float]
    shadow_rgb: tuple[float, float, float]
    highlight_cast: str
    shadow_cast: str
    summary: str


# ── 基础工具 ─────────────────────────────────────────────────────


def srgb_encode(linear: np.ndarray) -> np.ndarray:
    """线性 sRGB → sRGB 编码；先算幂函数分支，再补回暗部线性段。"""
    data = np.asarray(linear, dtype=np.float32)
    positive = np.maximum(data, 0.0)
    result = 1.055 * np.power(positive, 1.0 / 2.4) - 0.055
    low = positive <= 0.0031308
    if bool(np.any(low)):
        result[low] = positive[low] * 12.92
    return result


def srgb_decode(encoded: np.ndarray) -> np.ndarray:
    data = np.asarray(encoded, dtype=np.float32)
    clipped = np.clip(data, 0.0, 1.0)
    low = clipped / 12.92
    high = np.power((clipped + 0.055) / 1.055, 2.4)
    return np.where(clipped <= 0.04045, low, high).astype(np.float32)


def prepare_source(prophoto_linear: np.ndarray) -> np.ndarray:
    """线性 ProPhoto float → 线性 sRGB float32。"""
    image = np.asarray(prophoto_linear, dtype=np.float32)[..., :3]
    return np.einsum(
        '...c,dc->...d',
        image,
        _prophoto_to_srgb_matrix(),
        optimize=True,
    ).astype(np.float32)


def load_handoff_image(path: str | Path) -> np.ndarray:
    """读取交接图，直接按 float32 落地，避免 16-bit TIFF 的 float64 峰值。"""
    import OpenImageIO as oiio

    source = oiio.ImageInput.open(str(path))
    if source is None:
        raise OSError(f'无法打开交接图：{path}')
    pixels = None
    try:
        spec = source.spec()
        height, width, channels = int(spec.height), int(spec.width), int(spec.nchannels)
        pixel_format = spec.format
        scale = None
        if pixel_format == oiio.TypeDesc('uint16'):
            pixels = source.read_image(oiio.TypeDesc('uint16'))
            scale = 65535.0
        elif pixel_format == oiio.TypeDesc('uint8'):
            pixels = source.read_image(oiio.TypeDesc('uint8'))
            scale = 255.0
        else:
            pixels = source.read_image(oiio.TypeDesc('float'))
    finally:
        source.close()

    if pixels is None:
        raise ValueError('交接图数据读取失败')
    image = np.asarray(pixels).reshape(height, width, channels)
    if image.ndim != 3 or image.shape[2] < 3:
        raise ValueError('交接图不是三通道图像')
    result = image[..., :3].astype(np.float32, copy=False)
    if scale is not None:
        result = result / scale
    return np.ascontiguousarray(result, dtype=np.float32)


def downsample_linear(image: np.ndarray, max_long_edge: int) -> np.ndarray:
    """线性图按长边上限抗锯齿下采样；已经足够小时原样返回。"""
    data = np.asarray(image, dtype=np.float32)
    height, width = data.shape[:2]
    longest = max(height, width)
    if longest <= int(max_long_edge) or longest <= 1:
        return data
    from skimage.transform import resize

    scale = float(max_long_edge) / float(longest)
    new_height = max(1, int(round(height * scale)))
    new_width = max(1, int(round(width * scale)))
    # scikit-image 0.26 移除了 channel_axis；输入/输出通道数相同（3）时
    # resize 会把最后一维当通道，只需给出二维输出尺寸加上通道维。
    resized = resize(
        data,
        (new_height, new_width, 3),
        order=1,
        preserve_range=True,
        anti_aliasing=True,
    )
    return np.asarray(resized, dtype=np.float32)


def render_handoff_file(path: str | Path, recipe: GradeRecipe) -> tuple[np.ndarray, ToneAnalysis]:
    source = prepare_source(load_handoff_image(path))
    return render(source, recipe)


def _luma(image: np.ndarray) -> np.ndarray:
    return (
        image[..., 0] * LUMA_REC709[0]
        + image[..., 1] * LUMA_REC709[1]
        + image[..., 2] * LUMA_REC709[2]
    )


def _box_blur(values: np.ndarray, radius: float) -> np.ndarray:
    """两次盒式滤波近似高斯；局部均值类步骤用它换速度。"""
    size = max(3, int(round(radius * 2.0)) | 1)
    result = uniform_filter(values, size=size, mode='nearest')
    return uniform_filter(result, size=size, mode='nearest')


def _smoothstep(edge0: float, edge1: float, value: np.ndarray) -> np.ndarray:
    if edge1 <= edge0:
        return (value >= edge1).astype(np.float32)
    t = np.clip((value - edge0) / (edge1 - edge0), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


def _postprocess(image: np.ndarray) -> np.ndarray:
    data = np.asarray(image, dtype=np.float32)
    np.nan_to_num(data, copy=False, nan=0.0, posinf=1.0, neginf=0.0)
    np.clip(data, 0.0, 1.0, out=data)
    return data


# ── 影调 ─────────────────────────────────────────────────────────


def _apply_exposure_wb(image: np.ndarray, exposure: float, temperature: float, tint: float) -> np.ndarray:
    if abs(exposure) <= 1e-6 and abs(temperature) <= 1e-6 and abs(tint) <= 1e-6:
        return image
    data = image.copy()
    if abs(exposure) > 1e-6:
        data *= float(2.0 ** float(exposure))
    if abs(temperature) > 1e-6 or abs(tint) > 1e-6:
        temp = float(temperature) / 100.0
        tnt = float(tint) / 100.0
        red_gain = 2.0 ** (0.35 * temp + 0.12 * tnt)
        green_gain = 2.0 ** (-0.30 * tnt)
        blue_gain = 2.0 ** (-0.35 * temp + 0.12 * tnt)
        data[..., 0] *= red_gain
        data[..., 1] *= green_gain
        data[..., 2] *= blue_gain
    return data.astype(np.float32)


def _apply_contrast(image: np.ndarray, contrast: float) -> np.ndarray:
    if abs(contrast) < 1e-6:
        return image
    p = np.clip(image, 0.0, 1.0)
    strength = float(2.0 ** (1.25 * float(contrast) / 100.0))
    low_input = np.maximum(2.0 * p, 0.0)
    high_input = np.maximum(2.0 * (1.0 - p), 0.0)
    low_output = 0.5 * np.power(low_input, strength)
    high_output = 1.0 - 0.5 * np.power(high_input, strength)
    return np.where(p < 0.5, low_output, high_output).astype(np.float32)


def _apply_tone_masks(image: np.ndarray, light: LightRecipe) -> np.ndarray:
    amounts = (
        light.shadows,
        light.blacks,
        light.highlights,
        light.whites,
        light.midtones,
    )
    if all(abs(float(value)) <= 1e-6 for value in amounts):
        return image
    data = image
    y = _luma(data)
    if abs(float(light.shadows)) > 1e-6:
        data = data + (
            float(light.shadows) / 100.0 * 0.20
            * y * np.power(np.maximum(1.0 - y, 0.0), 4.5)
        )[..., None]
    if abs(float(light.blacks)) > 1e-6:
        data = data + (
            float(light.blacks) / 100.0 * 0.12
            * y * np.power(np.maximum(1.0 - y, 0.0), 12.0)
        )[..., None]
    if abs(float(light.highlights)) > 1e-6:
        data = data + (
            float(light.highlights) / 100.0 * 0.20
            * (1.0 - y) * np.power(np.maximum(y, 0.0), 4.5)
        )[..., None]
    if abs(float(light.whites)) > 1e-6:
        data = data + (
            float(light.whites) / 100.0 * 0.12
            * (1.0 - y) * np.power(np.maximum(y, 0.0), 12.0)
        )[..., None]
    if abs(float(light.midtones)) > 1e-6:
        data = data + (
            float(light.midtones) / 100.0 * 0.10 * 4.0 * y * np.maximum(1.0 - y, 0.0)
        )[..., None]
    return data.astype(np.float32)


def _apply_highlight_rolloff(image: np.ndarray, rolloff: float) -> np.ndarray:
    if rolloff <= 1e-6:
        return image
    strength = float(rolloff) / 100.0 * 1.5
    over = np.maximum(image - 0.55, 0.0)
    return (image - strength * over * over).astype(np.float32)


def _apply_parametric_curve(image: np.ndarray, light: LightRecipe) -> np.ndarray:
    curve = (
        (light.curve_highlights, 0.88),
        (light.curve_lights, 0.62),
        (light.curve_darks, 0.35),
        (light.curve_shadows, 0.12),
    )
    if all(abs(float(value)) <= 1e-6 for value, _center in curve):
        return image
    data = image
    y = _luma(data)
    for amount, center in curve:
        if abs(float(amount)) < 1e-6:
            continue
        mask = np.exp(-0.5 * np.square((y - center) / 0.14))
        data = data + (float(amount) / 100.0 * 0.18 * mask)[..., None]
    return data.astype(np.float32)


def _apply_tone(image: np.ndarray, light: LightRecipe) -> np.ndarray:
    data = _apply_contrast(image, light.contrast)
    data = _apply_tone_masks(data, light)
    data = _apply_highlight_rolloff(data, light.highlight_rolloff)
    return _apply_parametric_curve(data, light)


# ── 色彩 ─────────────────────────────────────────────────────────


def _hue_chroma(hue_degrees: float) -> np.ndarray:
    return _cached_hue_chroma(float(hue_degrees) % 360.0)


@lru_cache(maxsize=360)
def _cached_hue_chroma(hue_degrees: float) -> np.ndarray:
    from colorsys import hsv_to_rgb

    red, green, blue = hsv_to_rgb(hue_degrees / 360.0, 1.0, 1.0)
    mean = (red + green + blue) / 3.0
    vector = np.array((red - mean, green - mean, blue - mean), dtype=np.float32)
    scale = float(np.max(np.abs(vector))) or 1.0
    return vector / scale


def _rgb_to_hsv(image: np.ndarray) -> np.ndarray:
    from skimage.color import rgb2hsv

    return rgb2hsv(np.clip(image, 0.0, 1.0).astype(np.float32))


def _hsv_to_rgb(image: np.ndarray) -> np.ndarray:
    from skimage.color import hsv2rgb

    return hsv2rgb(image).astype(np.float32)


def _apply_saturation(image: np.ndarray, color: ColorRecipe) -> np.ndarray:
    saturation = float(color.saturation)
    vibrance = float(color.vibrance)
    density = float(color.color_density)
    if abs(saturation) < 1e-6 and abs(vibrance) < 1e-6 and density <= 1e-6:
        return image
    y = _luma(image)[..., None]
    maximum = image.max(axis=2)
    minimum = image.min(axis=2)
    pixel_saturation = np.where(maximum > 1e-4, (maximum - minimum) / maximum, 0.0)
    vib_factor = 1.0 + vibrance / 100.0 * np.power(
        np.maximum(1.0 - pixel_saturation, 0.0), 1.25,
    )
    factor = (1.0 + saturation / 100.0) * vib_factor
    factor = factor * (1.0 + density / 100.0 * 0.5)
    factor = np.maximum(factor, 0.0)[..., None]
    return (y + (image - y) * factor).astype(np.float32)


def _apply_hue_shift(image: np.ndarray, shift: float) -> np.ndarray:
    if abs(shift) < 1e-6:
        return image
    hsv = _rgb_to_hsv(image)
    hsv[..., 0] = (hsv[..., 0] + float(shift) / 360.0) % 1.0
    return _hsv_to_rgb(hsv)


def _apply_hsl_bands(image: np.ndarray, color: ColorRecipe) -> np.ndarray:
    bands = color.hsl
    if not bands or all(
        abs(band.hue) < 1e-6 and abs(band.saturation) < 1e-6 and abs(band.luminance) < 1e-6
        for band in bands
    ):
        return image

    hsv = _rgb_to_hsv(image)
    hue_degrees = hsv[..., 0] * 360.0
    weights: list[np.ndarray] = []
    hue_delta = 0.0
    saturation_factor = 0.0
    luminance_delta = 0.0
    sigma = 24.0
    for index, center in enumerate(_BAND_CENTERS[: len(bands)]):
        band = bands[index]
        delta = (hue_degrees - center + 180.0) % 360.0 - 180.0
        weight = np.exp(-0.5 * np.square(delta / sigma))
        weights.append(weight)
        hue_delta = hue_delta + weight * (float(band.hue) / 100.0 * 30.0)
        saturation_factor = saturation_factor + weight * (float(band.saturation) / 100.0 * 0.5)
        luminance_delta = luminance_delta + weight * (float(band.luminance) / 100.0 * 0.15)

    total = np.maximum(sum(weights), 1e-6)
    hsv[..., 0] = ((hue_degrees + hue_delta / total) % 360.0) / 360.0
    hsv[..., 1] = np.clip(hsv[..., 1] * (1.0 + saturation_factor / total), 0.0, 1.0)
    hsv[..., 2] = np.clip(hsv[..., 2] + luminance_delta / total, 0.0, 1.0)
    return _hsv_to_rgb(hsv)


def _apply_color_grading(image: np.ndarray, color: ColorRecipe) -> np.ndarray:
    grading = color.grading
    zones = (grading.shadows, grading.midtones, grading.highlights)
    if all(
        abs(zone.saturation) < 1e-6 and abs(zone.luminance) < 1e-6
        for zone in zones
    ):
        return image

    y = _luma(image)
    balance = float(grading.balance) / 100.0
    spread = 0.16 + 0.16 * float(grading.blending) / 100.0
    centers = (0.18 - 0.04 * balance, 0.50 + 0.02 * balance, 0.82 + 0.04 * balance)
    sigmas = (spread, spread * 0.9, spread)
    data = image
    for zone, center, sigma in zip(zones, centers, sigmas):
        mask = np.exp(-0.5 * np.square((y - center) / sigma))
        if abs(float(zone.saturation)) > 1e-6:
            chroma = _hue_chroma(zone.hue) * (float(zone.saturation) / 100.0 * 0.12)
            data = data + chroma[None, None, :] * mask[..., None]
        if abs(float(zone.luminance)) > 1e-6:
            data = data + (float(zone.luminance) / 100.0 * 0.08 * mask)[..., None]
    return data.astype(np.float32)


def _apply_color(image: np.ndarray, color: ColorRecipe) -> np.ndarray:
    data = _apply_saturation(image, color)
    data = _apply_hue_shift(data, color.hue_shift)
    data = _apply_hsl_bands(data, color)
    return _apply_color_grading(data, color)


# ── 通透 ─────────────────────────────────────────────────────────


def analyze_tone(image: np.ndarray) -> ToneAnalysis:
    data = np.asarray(image, dtype=np.float32)
    y = _luma(data)
    sample_step = max(1, int(math.sqrt(max(y.size, 1) / 200_000.0)))
    sample = y[::sample_step, ::sample_step]
    black, shadow_cut, highlight_cut, white = (
        float(value)
        for value in np.percentile(
            sample,
            (
                TRANSPARENCY_EDGE_PERCENT,
                10.0,
                90.0,
                100.0 - TRANSPARENCY_EDGE_PERCENT,
            ),
        )
    )
    if white <= black:
        white = min(1.0, black + 0.06)
    shadow_mask = y <= shadow_cut
    highlight_mask = y >= highlight_cut
    if not bool(np.any(shadow_mask)):
        shadow_mask = np.ones_like(y, dtype=bool)
    if not bool(np.any(highlight_mask)):
        highlight_mask = np.ones_like(y, dtype=bool)
    shadow_rgb = tuple(float(value) for value in data[shadow_mask].mean(axis=0))
    highlight_rgb = tuple(float(value) for value in data[highlight_mask].mean(axis=0))
    shadow_cast = _cast_name(shadow_rgb)
    highlight_cast = _cast_name(highlight_rgb)
    summary = (
        f'黑场 {black * 100.0:.1f}% · 白场 {white * 100.0:.1f}%'
        f' · 高光{highlight_cast} · 阴影{shadow_cast}'
    )
    return ToneAnalysis(
        black_point=black,
        white_point=white,
        highlight_rgb=highlight_rgb,
        shadow_rgb=shadow_rgb,
        highlight_cast=highlight_cast,
        shadow_cast=shadow_cast,
        summary=summary,
    )


def _cast_name(rgb: Sequence[float]) -> str:
    red, green, blue = (float(value) for value in tuple(rgb)[:3])
    mean = (red + green + blue) / 3.0
    deviation = (red - mean, green - mean, blue - mean)
    if max(abs(value) for value in deviation) < 0.015:
        return '中性'
    red_high = deviation[0] > 0.015
    green_high = deviation[1] > 0.015
    blue_high = deviation[2] > 0.015
    red_low = deviation[0] < -0.015
    green_low = deviation[1] < -0.015
    blue_low = deviation[2] < -0.015
    if red_high and green_high and blue_low:
        return '偏黄'
    if red_high and blue_high and green_low:
        return '偏品红'
    if green_high and blue_high and red_low:
        return '偏青'
    if red_high and green_low and blue_low:
        return '偏红'
    if green_high and red_low and blue_low:
        return '偏绿'
    if blue_high and red_low and green_low:
        return '偏蓝'
    return '偏色'


def _apply_transparency(
    image: np.ndarray,
    recipe: TransparencyRecipe,
    analysis: ToneAnalysis,
) -> np.ndarray:
    data = image
    tonal = float(recipe.tonal) / 100.0
    if tonal > 1e-6:
        span = max(analysis.white_point - analysis.black_point, 0.06)
        leveled = np.clip((data - analysis.black_point) / span, 0.0, 1.0)
        data = data * (1.0 - tonal) + leveled * tonal

    color_amount = float(recipe.color) / 100.0
    if color_amount > 1e-6:
        highlight_rgb = np.asarray(analysis.highlight_rgb, dtype=np.float32)
        shadow_rgb = np.asarray(analysis.shadow_rgb, dtype=np.float32)
        white_delta = np.clip(-(highlight_rgb - float(highlight_rgb.mean())), -0.05, 0.05)
        black_delta = np.clip(-(shadow_rgb - float(shadow_rgb.mean())), -0.05, 0.05)
        y = _luma(data)
        white_mask = _smoothstep(0.52, 0.96, y)
        black_mask = 1.0 - _smoothstep(0.06, 0.34, y)
        data = (
            data
            + white_delta[None, None, :] * white_mask[..., None] * color_amount
            + black_delta[None, None, :] * black_mask[..., None] * color_amount
        )
    return data.astype(np.float32)


# ── 画质 ─────────────────────────────────────────────────────────


def _apply_clarity_structure(image: np.ndarray, quality: QualityRecipe) -> np.ndarray:
    clarity = float(quality.clarity)
    texture = float(quality.texture)
    if abs(clarity) < 1e-6 and abs(texture) < 1e-6:
        return image
    height, width = image.shape[:2]
    short_edge = max(1, min(height, width))
    y = np.maximum(_luma(image), 1e-4)
    log_luma = np.log2(y)
    data = image
    for amount, ratio, sigma in ((clarity, 0.008, 0.35), (texture, 0.003, 0.25)):
        if abs(float(amount)) < 1e-6:
            continue
        radius = max(1.0, short_edge * ratio)
        base = _box_blur(log_luma, radius)
        detail = log_luma - base
        shaped = detail / (1.0 + np.square(detail / sigma))
        gain = np.power(2.0, float(amount) / 100.0 * 0.5 * shaped)
        data = data * gain[..., None]
    return data.astype(np.float32)


def _apply_dehaze(image: np.ndarray, amount: float) -> np.ndarray:
    if abs(amount) < 1e-6:
        return image
    if amount < 0.0:
        strength = min(1.0, abs(float(amount)) / 100.0)
        return (image * (1.0 - 0.25 * strength) + 0.18 * strength).astype(np.float32)

    strength = 1.0 - (1.0 - float(amount) / 100.0) ** 2
    height, width = image.shape[:2]
    short_edge = max(1, min(height, width))
    dark = image.min(axis=2)
    window = max(3, int(round(short_edge * 0.02)) | 1)
    dark_smooth = minimum_filter(dark, size=window, mode='nearest')
    airlight = float(np.percentile(_luma(image), 99.0))
    airlight = max(airlight, 0.30)
    transmission = np.clip(
        1.0 - strength * 0.95 * dark_smooth / max(airlight, 0.1),
        0.1,
        1.0,
    )
    return (airlight + (image - airlight) / transmission[..., None]).astype(np.float32)


def _apply_noise_reduction(image: np.ndarray, quality: QualityRecipe) -> np.ndarray:
    luminance = float(quality.noise_luminance) / 100.0
    chroma = float(quality.noise_color) / 100.0
    data = image
    short_edge = max(1, min(data.shape[:2]))
    if luminance > 1e-6:
        y = _luma(data)
        smooth = _box_blur(y, max(0.8, short_edge * 0.0015))
        data = data + (smooth - y)[..., None] * (luminance * 0.85)
    if chroma > 1e-6:
        y = _luma(data)
        red = data[..., 0]
        blue = data[..., 2]
        cr = red - y
        cb = blue - y
        radius = max(1.0, short_edge * 0.0025)
        cr_smooth = _box_blur(cr, radius)
        cb_smooth = _box_blur(cb, radius)
        red = red + (cr_smooth - cr) * (chroma * 0.85)
        blue = blue + (cb_smooth - cb) * (chroma * 0.85)
        data = np.stack((red, data[..., 1], blue), axis=2)
    return data.astype(np.float32)


def _core_detail(detail: np.ndarray, threshold: float) -> np.ndarray:
    squared = np.square(detail)
    return detail * squared / (squared + threshold * threshold)


def _apply_sharpening(image: np.ndarray, quality: QualityRecipe) -> np.ndarray:
    amount = float(quality.sharpen_amount) / 100.0
    if amount <= 1e-6:
        return image
    short_edge = max(1, min(image.shape[:2]))
    scale = max(0.6, min(2.0, short_edge / 1080.0))
    radius = float(quality.sharpen_radius) * scale
    y = _luma(image)
    blur_one = _box_blur(y, max(0.6, radius * 0.9))
    blur_wide = _box_blur(y, max(1.2, radius * 2.6))
    threshold = 0.002 + float(quality.sharpen_threshold) / 100.0 * 0.06
    detail = _core_detail(y - blur_one, threshold)
    detail = detail + 0.5 * _core_detail(blur_one - blur_wide, threshold)
    return (image + detail[..., None] * (amount * 2.0)).astype(np.float32)


# ── 光学 ─────────────────────────────────────────────────────────


@lru_cache(maxsize=8)
def _vignette_radius(height: int, width: int, roundness: float) -> np.ndarray:
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    nx = (xx - width / 2.0) / max(width / 2.0, 1.0)
    ny = (yy - height / 2.0) / max(height / 2.0, 1.0)
    nx = nx * (1.0 + 0.25 * roundness)
    ny = ny * (1.0 - 0.25 * roundness)
    return np.sqrt(nx * nx + ny * ny).astype(np.float32)


def _apply_vignette(image: np.ndarray, optics: OpticsRecipe) -> np.ndarray:
    amount = float(optics.vignette_amount) / 100.0
    if abs(amount) < 1e-6:
        return image
    height, width = image.shape[:2]
    roundness = float(optics.vignette_roundness) / 100.0
    radius = _vignette_radius(int(height), int(width), roundness)
    midpoint = 0.20 + float(optics.vignette_midpoint) / 100.0 * 1.10
    feather = max(0.05, float(optics.vignette_feather) / 100.0)
    mask = _smoothstep(midpoint - feather / 2.0, midpoint + feather / 2.0, radius)
    factor = np.maximum(1.0 - amount * mask, 0.0)
    return (image * factor[..., None]).astype(np.float32)


def _apply_chromatic_aberration(image: np.ndarray, amount: float) -> np.ndarray:
    strength = float(amount) / 100.0 * 0.004
    if strength <= 1e-6:
        return image
    height, width = image.shape[:2]
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    cy = height / 2.0
    cx = width / 2.0
    red = map_coordinates(
        image[..., 0],
        (cy + (yy - cy) * (1.0 + strength), cx + (xx - cx) * (1.0 + strength)),
        order=1,
        mode='nearest',
    )
    blue = map_coordinates(
        image[..., 2],
        (cy + (yy - cy) * (1.0 - strength), cx + (xx - cx) * (1.0 - strength)),
        order=1,
        mode='nearest',
    )
    return np.stack((red, image[..., 1], blue), axis=2).astype(np.float32)


@lru_cache(maxsize=4)
def _grain_noise(height: int, width: int) -> np.ndarray:
    rng = np.random.default_rng(20240101)
    return rng.standard_normal((height, width)).astype(np.float32)


def _apply_grain(image: np.ndarray, optics: OpticsRecipe) -> np.ndarray:
    amount = float(optics.grain_amount) / 100.0
    if amount <= 1e-6:
        return image
    height, width = image.shape[:2]
    noise = _grain_noise(int(height), int(width))
    scale = max(0.6, min(3.0, max(1, min(height, width)) / 1080.0))
    sigma = (0.6 + float(optics.grain_size) / 100.0 * 3.0) * scale
    if sigma > 0.9:
        noise = _box_blur(noise, sigma)
    roughness = float(optics.grain_roughness) / 100.0
    if roughness > 1e-6:
        noise = np.sign(noise) * np.power(np.abs(noise), 1.0 - roughness * 0.7)
    deviation = float(noise.std())
    if deviation > 1e-6:
        noise = noise / deviation
    y = _luma(image)
    weight = 0.4 + 0.6 * 4.0 * y * np.maximum(1.0 - y, 0.0)
    return (image + noise[..., None] * (amount * 0.06) * weight[..., None]).astype(np.float32)


def _apply_optics(image: np.ndarray, optics: OpticsRecipe) -> np.ndarray:
    data = _apply_vignette(image, optics)
    data = _apply_chromatic_aberration(data, optics.chromatic_aberration)
    return _apply_grain(data, optics)


# ── LUT ──────────────────────────────────────────────────────────


def parse_cube(path: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """解析 3D .cube，返回 (LUT[b,g,r,3], domain_min, domain_max)。"""
    file_path = Path(path)
    size = 0
    domain_min = np.zeros(3, dtype=np.float32)
    domain_max = np.ones(3, dtype=np.float32)
    values: list[float] = []
    with file_path.open('r', encoding='utf-8', errors='replace') as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            upper = line.upper()
            if upper.startswith('LUT_3D_SIZE'):
                size = int(line.split()[-1])
            elif upper.startswith('DOMAIN_MIN'):
                domain_min = np.array([float(part) for part in line.split()[1:4]], dtype=np.float32)
            elif upper.startswith('DOMAIN_MAX'):
                domain_max = np.array([float(part) for part in line.split()[1:4]], dtype=np.float32)
            elif upper.startswith(('TITLE', 'LUT_1D', 'LUT_3D_INPUT')):
                continue
            else:
                try:
                    parts = [float(part) for part in line.split()]
                except ValueError:
                    continue
                if len(parts) >= 3:
                    values.extend(parts[:3])
    if size < 2:
        raise ValueError('不是有效的 3D .cube 文件')
    expected = size ** 3 * 3
    if len(values) < expected:
        raise ValueError('LUT 数据行数不足')
    lut = np.asarray(values[:expected], dtype=np.float32).reshape(size, size, size, 3)
    return lut, domain_min, domain_max


@lru_cache(maxsize=8)
def _cached_cube(path: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return parse_cube(path)


def apply_lut(image: np.ndarray, path: str, strength: float) -> np.ndarray:
    if not path or float(strength) <= 1e-6:
        return image
    try:
        lut, domain_min, domain_max = _cached_cube(str(path))
    except (OSError, ValueError):
        return image

    size = lut.shape[0]
    coordinates = np.clip(
        (image - domain_min) / np.maximum(domain_max - domain_min, 1e-6),
        0.0,
        1.0,
    ) * float(size - 1)
    lower = np.floor(coordinates).astype(np.int32)
    upper = np.minimum(lower + 1, size - 1)
    fraction = (coordinates - lower).astype(np.float32)

    r0, g0, b0 = lower[..., 0], lower[..., 1], lower[..., 2]
    r1, g1, b1 = upper[..., 0], upper[..., 1], upper[..., 2]
    fr, fg, fb = fraction[..., 0], fraction[..., 1], fraction[..., 2]

    def corner(r_index, g_index, b_index):
        return lut[b_index, g_index, r_index]

    c000 = corner(r0, g0, b0)
    c001 = corner(r1, g0, b0)
    c010 = corner(r0, g1, b0)
    c011 = corner(r1, g1, b0)
    c100 = corner(r0, g0, b1)
    c101 = corner(r1, g0, b1)
    c110 = corner(r0, g1, b1)
    c111 = corner(r1, g1, b1)

    c00 = c000 * (1.0 - fr[..., None]) + c001 * fr[..., None]
    c01 = c010 * (1.0 - fr[..., None]) + c011 * fr[..., None]
    c10 = c100 * (1.0 - fr[..., None]) + c101 * fr[..., None]
    c11 = c110 * (1.0 - fr[..., None]) + c111 * fr[..., None]
    c0 = c00 * (1.0 - fg[..., None]) + c01 * fg[..., None]
    c1 = c10 * (1.0 - fg[..., None]) + c11 * fg[..., None]
    graded = c0 * (1.0 - fb[..., None]) + c1 * fb[..., None]

    mix = float(strength) / 100.0
    return (image * (1.0 - mix) + graded * mix).astype(np.float32)


# ── 主入口 ───────────────────────────────────────────────────────


def render(
    source_linear_srgb: np.ndarray,
    recipe: GradeRecipe,
    *,
    analyze: bool = True,
) -> tuple[np.ndarray, ToneAnalysis]:
    """线性 sRGB 源 → (sRGB 编码显示图, 通透分析)。"""
    source = np.asarray(source_linear_srgb, dtype=np.float32)
    if source.ndim != 3 or source.shape[2] < 3:
        raise ValueError('调色源必须是三通道图像')

    with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        data = source[..., :3]
        data = _apply_exposure_wb(
            data,
            recipe.light.exposure,
            recipe.color.temperature,
            recipe.color.tint,
        )
        data = srgb_encode(data)
        data = _apply_tone(data, recipe.light)
        data = _apply_color(data, recipe.color)
        analysis = analyze_tone(data) if analyze else ToneAnalysis(
            black_point=0.0,
            white_point=1.0,
            highlight_rgb=(1.0, 1.0, 1.0),
            shadow_rgb=(0.0, 0.0, 0.0),
            highlight_cast='中性',
            shadow_cast='中性',
            summary='未分析',
        )
        data = _apply_transparency(data, recipe.transparency, analysis)
        data = _apply_clarity_structure(data, recipe.quality)
        data = _apply_dehaze(data, recipe.quality.dehaze)
        data = _apply_noise_reduction(data, recipe.quality)
        data = _apply_sharpening(data, recipe.quality)
        data = _apply_optics(data, recipe.optics)
        data = apply_lut(data, recipe.lut.path, recipe.lut.strength)

    return _postprocess(data), analysis


__all__ = [
    'ToneAnalysis',
    'analyze_tone',
    'apply_lut',
    'downsample_linear',
    'load_handoff_image',
    'parse_cube',
    'prepare_source',
    'render',
    'render_handoff_file',
    'srgb_decode',
    'srgb_encode',
]
