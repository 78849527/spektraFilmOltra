"""预览与显示的纯像素处理，不依赖 Qt。

Qt 壳和 Electron 服务层共用这一份实现，避免两套显示逻辑分叉。
"""

from __future__ import annotations

import io
import platform
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

DISPLAY_PREVIEW_COLOR_SPACE = 'sRGB'
DISPLAY_PROFILE_DIRS = (
    '/Library/ColorSync/Profiles/Displays',
    str(Path.home() / 'Library/ColorSync/Profiles/Displays'),
)


def normalized_image_data(image: np.ndarray) -> np.ndarray:
    if np.issubdtype(image.dtype, np.floating):
        return np.clip(image, 0.0, 1.0)
    if np.issubdtype(image.dtype, np.integer):
        max_value = np.iinfo(image.dtype).max
        if max_value == 0:
            return image.astype(np.float32)
        return image.astype(np.float32) / max_value
    return image.astype(np.float32)


def apply_white_padding(image_data: np.ndarray, padding_pixels: float) -> np.ndarray:
    padding = max(0, int(round(padding_pixels)))
    if padding == 0:
        return np.asarray(image_data)

    image = np.asarray(image_data)
    if image.ndim < 2:
        return image

    fill_value = np.iinfo(image.dtype).max if np.issubdtype(image.dtype, np.integer) else 1.0
    pad_width = [(padding, padding), (padding, padding)]
    pad_width.extend((0, 0) for _ in range(image.ndim - 2))
    return np.pad(image, pad_width, mode='constant', constant_values=fill_value)


def padding_pixels_for_image(image_data: np.ndarray, padding_fraction: float) -> int:
    image = np.asarray(image_data)
    if image.ndim < 2:
        return 0

    padding_fraction = max(0.0, float(padding_fraction))
    long_edge = max(int(image.shape[0]), int(image.shape[1]))
    return int(np.floor(long_edge * padding_fraction))


def display_profile_name(display_profile: object, *, imagecms_module: Any) -> str:
    try:
        profile_name = imagecms_module.getProfileName(display_profile)
    except (AttributeError, OSError, ValueError, TypeError, imagecms_module.PyCMSError):
        profile_name = None

    if isinstance(profile_name, str):
        cleaned_name = profile_name.replace('\x00', ' ').strip()
        if cleaned_name:
            return ' '.join(cleaned_name.split())

    profile_filename = getattr(display_profile, 'filename', None)
    if isinstance(profile_filename, str) and profile_filename.strip():
        return Path(profile_filename).stem

    return type(display_profile).__name__


@lru_cache(maxsize=1)
def _macos_main_display_model() -> str:
    """读取主显示器型号（system_profiler），失败时返回空串。"""
    if platform.system() != 'Darwin':
        return ''
    try:
        completed = subprocess.run(
            ['system_profiler', 'SPDisplaysDataType'],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ''
    model = ''
    for line in completed.stdout.splitlines():
        text = line.strip()
        if line.startswith(' ' * 8) and not line.startswith(' ' * 9) and text.endswith(':'):
            model = text[:-1]
            continue
        if model and text.startswith('Main Display:') and 'Yes' in text:
            return model
    return ''


@lru_cache(maxsize=1)
def _macos_display_profile_bytes() -> bytes | None:
    """macOS 上 Pillow 拿不到显示器 ICC，于是按主显示器型号匹配 ColorSync 里的配置。"""
    model = _macos_main_display_model()
    if not model:
        return None
    candidates: list[Path] = []
    for folder in DISPLAY_PROFILE_DIRS:
        try:
            entries = tuple(Path(folder).iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.suffix.lower() != '.icc':
                continue
            if entry.name.startswith(f'{model}-'):
                candidates.append(entry)
    if not candidates:
        return None
    try:
        newest = max(candidates, key=lambda path: path.stat().st_mtime)
        return newest.read_bytes()
    except OSError:
        return None


def _system_display_profile(*, imagecms_module: Any) -> object | None:
    try:
        profile = imagecms_module.get_display_profile()
    except (AttributeError, OSError, ValueError, TypeError, imagecms_module.PyCMSError):
        profile = None
    if profile is not None:
        return profile

    profile_factory = getattr(imagecms_module, 'ImageCmsProfile', None)
    raw = _macos_display_profile_bytes()
    if profile_factory is None or raw is None:
        return None
    try:
        return profile_factory(io.BytesIO(raw))
    except (AttributeError, OSError, ValueError, TypeError, imagecms_module.PyCMSError):
        return None


def display_profile_details(*, imagecms_module: Any) -> tuple[object | None, str | None]:
    display_profile = _system_display_profile(imagecms_module=imagecms_module)
    if display_profile is None:
        return None, None
    return display_profile, display_profile_name(display_profile, imagecms_module=imagecms_module)


def display_profile_available(*, imagecms_module: Any) -> bool:
    return _system_display_profile(imagecms_module=imagecms_module) is not None


def display_transform_status_message(enabled: bool, *, imagecms_module: Any) -> str:
    if not enabled:
        return '显示变换：已关闭'
    display_profile, profile_name = display_profile_details(imagecms_module=imagecms_module)
    if display_profile is None:
        return '显示变换：未找到显示器色彩描述文件，使用原始预览'
    return f'显示变换：已找到显示器色彩描述文件（{profile_name}）'


def prepare_input_color_preview_image(
    image_data: np.ndarray,
    *,
    input_color_space: str,
    apply_cctf_decoding: bool,
    colour_module: Any,
) -> np.ndarray:
    normalized_image = normalized_image_data(np.asarray(image_data)[..., :3])
    try:
        srgb_preview = colour_module.RGB_to_RGB(
            normalized_image,
            input_color_space,
            DISPLAY_PREVIEW_COLOR_SPACE,
            apply_cctf_decoding=apply_cctf_decoding,
            apply_cctf_encoding=True,
        )
    except (AttributeError, LookupError, RuntimeError, TypeError, ValueError):
        return np.asarray(np.clip(normalized_image, 0.0, 1.0), dtype=np.float32)
    return np.asarray(np.clip(srgb_preview, 0.0, 1.0), dtype=np.float32)


def apply_display_transform(
    image_data: np.ndarray,
    *,
    output_color_space: str,
    colour_module: Any,
    imagecms_module: Any,
    pil_image_module: Any,
) -> tuple[np.ndarray, str]:
    display_profile, profile_name = display_profile_details(imagecms_module=imagecms_module)
    if display_profile is None:
        return np.uint8(np.clip(image_data, 0.0, 1.0) * 255), '显示变换：未找到显示器色彩描述文件，使用原始预览'

    srgb_preview = colour_module.RGB_to_RGB(
        image_data,
        output_color_space,
        DISPLAY_PREVIEW_COLOR_SPACE,
        apply_cctf_decoding=True,
        apply_cctf_encoding=True,
    )
    srgb_preview_uint8 = np.uint8(np.clip(srgb_preview, 0.0, 1.0) * 255)
    source_profile = imagecms_module.createProfile(DISPLAY_PREVIEW_COLOR_SPACE)
    source_image = pil_image_module.fromarray(srgb_preview_uint8, mode='RGB')
    transformed_image = imagecms_module.profileToProfile(source_image, source_profile, display_profile, outputMode='RGB')
    return np.asarray(transformed_image, dtype=np.uint8), f'显示变换：已启用（{profile_name}）'


def prepare_output_display_image(
    image_data: np.ndarray,
    *,
    output_color_space: str,
    use_display_transform: bool,
    padding_pixels: float = 0.0,
    imagecms_module: Any,
    colour_module: Any,
    pil_image_module: Any,
) -> tuple[np.ndarray, str]:
    del padding_pixels
    normalized_image = normalized_image_data(np.asarray(image_data)[..., :3])
    preview_image = np.uint8(np.clip(normalized_image, 0.0, 1.0) * 255)
    if not use_display_transform:
        return preview_image, display_transform_status_message(False, imagecms_module=imagecms_module)
    try:
        transformed_image, status = apply_display_transform(
            normalized_image,
            output_color_space=output_color_space,
            colour_module=colour_module,
            imagecms_module=imagecms_module,
            pil_image_module=pil_image_module,
        )
        return transformed_image, status
    except (OSError, ValueError, TypeError, imagecms_module.PyCMSError):
        return preview_image, '显示变换：转换失败，使用原始预览'


__all__ = [
    'DISPLAY_PREVIEW_COLOR_SPACE',
    'DISPLAY_PROFILE_DIRS',
    'apply_display_transform',
    'apply_white_padding',
    'display_profile_available',
    'display_profile_details',
    'display_profile_name',
    'display_transform_status_message',
    'normalized_image_data',
    'padding_pixels_for_image',
    'prepare_input_color_preview_image',
    'prepare_output_display_image',
]
