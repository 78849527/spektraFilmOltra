"""打开输入、缩放、显示编码与导出的纯函数。

这一层只调用现有引擎与 I/O，不重写任何算法。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import colour
import numpy as np

from spektrafilm.utils.io import (
    load_image_oiio,
    read_image_metadata,
    save_image_oiio,
    write_image_metadata,
)
from spektrafilm.utils.preview import resize_for_preview
from spektrafilm.utils.raw_file_processor import load_and_process_raw_file
from spektrafilm_gui.display_pixels import prepare_input_color_preview_image
from spektrafilm_gui.export_settings import ExportSettings
from spektrafilm_gui.input_color import detect_input_color_space

PREVIEW_MAX_EDGE = 1920
DISPLAY_PREVIEW_MAX_EDGE = 1600
PREVIEW_SCALES = (1.0, 0.5, 0.25)
HANDOFF_COLOR_SPACE = 'ProPhoto RGB'

_RAW_SUFFIXES = frozenset({
    '.cr2', '.cr3', '.nef', '.arw', '.dng', '.raf', '.orf', '.rw2', '.pef',
    '.srw', '.3fr', '.iiq', '.x3f', '.erf', '.mef', '.mos', '.mrw', '.nrw',
    '.rwl', '.srf', '.sr2',
})


@dataclass(frozen=True, slots=True)
class LoadedInput:
    image: np.ndarray
    color_space: str
    cctf_decoding: bool
    is_raw: bool
    lens_summary: str
    metadata: Any


def is_raw_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in _RAW_SUFFIXES


def load_input(path: str, load_raw: dict[str, Any]) -> LoadedInput:
    """按后缀分流：RAW 走 LibRaw，其余走 OpenImageIO。"""
    suffix = Path(path).suffix.lower()
    if suffix in _RAW_SUFFIXES:
        lens_info: dict[str, str] = {}
        image = load_and_process_raw_file(
            path,
            white_balance=str(load_raw.get('white_balance') or 'as_shot'),
            temperature=float(load_raw.get('temperature') or 5500.0),
            tint=float(load_raw.get('tint') or 1.0),
            lens_correction=bool(load_raw.get('lens_correction')),
            output_colorspace='ProPhoto RGB',
            output_cctf_encoding=False,
            lens_info_out=lens_info,
        )
        return LoadedInput(
            image=np.asarray(image),
            color_space='ProPhoto RGB',
            cctf_decoding=False,
            is_raw=True,
            lens_summary=str(lens_info.get('summary') or ''),
            metadata=_read_metadata(path),
        )

    color_space, decode = detect_input_color_space(path)
    image = np.asarray(load_image_oiio(path))[..., :3]
    return LoadedInput(
        image=image,
        color_space=color_space,
        cctf_decoding=decode,
        is_raw=False,
        lens_summary='',
        metadata=_read_metadata(path),
    )


def _read_metadata(path: str) -> Any:
    try:
        return read_image_metadata(path)
    except Exception:  # noqa: BLE001 - 元数据失败不影响载入
        return None


def display_preview_array(image: np.ndarray, color_space: str, cctf_decoding: bool) -> np.ndarray:
    source = resize_for_preview(image, max_size=DISPLAY_PREVIEW_MAX_EDGE)
    return prepare_input_color_preview_image(
        source,
        input_color_space=color_space,
        apply_cctf_decoding=cctf_decoding,
        colour_module=colour,
    )


def preview_source(image: np.ndarray, scale: float) -> np.ndarray:
    long_edge = max(int(image.shape[0]), int(image.shape[1]))
    target = min(max(1, int(round(long_edge * float(scale)))), PREVIEW_MAX_EDGE)
    if target >= long_edge:
        return np.asarray(image)
    return resize_for_preview(image, max_size=target)


def output_to_display_rgb(image: np.ndarray, output_color_space: str) -> np.ndarray:
    data = np.asarray(image, dtype=np.float32)[..., :3]
    if output_color_space != 'sRGB':
        data = np.asarray(
            colour.RGB_to_RGB(
                data,
                output_color_space,
                'sRGB',
                apply_cctf_decoding=True,
                apply_cctf_encoding=True,
            ),
            dtype=np.float32,
        )
    return np.uint8(np.clip(data, 0.0, 1.0) * 255)


def save_display_png(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    save_image_oiio(
        str(path),
        np.asarray(rgb, dtype=np.uint8),
        bit_depth=8,
        color_space='sRGB',
        cctf_encoding=True,
    )


def save_original_png(path: Path, image: np.ndarray) -> None:
    save_image_oiio(
        str(path),
        np.asarray(image, dtype=np.float32),
        bit_depth=8,
        color_space='sRGB',
        cctf_encoding=True,
    )


def convert_to_saving_space(
    image: np.ndarray,
    *,
    source_color_space: str,
    source_cctf_encoding: bool,
    saving_color_space: str,
    saving_cctf_encoding: bool,
) -> np.ndarray:
    if source_color_space == saving_color_space and source_cctf_encoding == saving_cctf_encoding:
        return np.asarray(image)
    return np.asarray(
        colour.RGB_to_RGB(
            np.asarray(image),
            source_color_space,
            saving_color_space,
            apply_cctf_decoding=bool(source_cctf_encoding),
            apply_cctf_encoding=bool(saving_cctf_encoding),
        )
    )


def export_image(
    image: np.ndarray,
    settings: ExportSettings,
    *,
    color_space: str,
    cctf_encoding: bool,
    source_path: str,
    film_stock: str,
    print_paper: str,
    metadata: Any,
) -> Path:
    settings = settings.normalized()
    data = np.asarray(image)
    if settings.long_edge > 0 and max(data.shape[:2]) > settings.long_edge:
        data = resize_for_preview(data, max_size=settings.long_edge)

    target = export_target_path(
        settings,
        source_path=source_path,
        film_stock=film_stock,
        print_paper=print_paper,
    )
    save_export_file(target, data, settings, color_space=color_space, cctf_encoding=cctf_encoding)
    if metadata is not None:
        try:
            write_image_metadata(
                str(target),
                metadata,
                saving_color_space=color_space,
                saving_cctf_encoding=cctf_encoding,
            )
        except Exception:  # noqa: BLE001 - 元数据失败不阻断导出
            pass
    return target


def export_target_path(
    settings: ExportSettings,
    *,
    source_path: str,
    film_stock: str,
    print_paper: str,
) -> Path:
    source = Path(source_path) if source_path else None
    if settings.directory:
        directory = Path(settings.directory).expanduser()
    elif source is not None:
        directory = source.parent
    else:
        directory = Path.home() / 'Pictures'
    directory.mkdir(parents=True, exist_ok=True)

    values = {
        'name': source.stem if source is not None else 'output',
        'film': film_stock or '',
        'paper': print_paper or '',
    }
    try:
        stem = settings.filename_template.format(**values)
    except (KeyError, ValueError):
        stem = f"{values['name']}_spektrafilm"
    stem = sanitize_filename(stem) or f"{values['name']}_spektrafilm"

    path = directory / f'{stem}.{settings.extension}'
    if not path.exists():
        return path
    for index in range(1, 1000):
        candidate = path.with_name(f'{path.stem}-{index}{path.suffix}')
        if not candidate.exists():
            return candidate
    return path


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', '-', str(value)).strip(' .-')
    return cleaned[:180]


def save_export_file(
    path: Path,
    data: np.ndarray,
    settings: ExportSettings,
    *,
    color_space: str,
    cctf_encoding: bool,
) -> None:
    suffix = path.suffix.lower()
    bit_depth = 16
    quality = None
    compression = None
    if suffix in {'.tif', '.tiff'}:
        bit_depth = settings.bit_depth if settings.bit_depth in {8, 16, 32} else 16
        compression = settings.tiff_compression
    elif suffix == '.exr':
        bit_depth = settings.bit_depth if settings.bit_depth in {16, 32} else 16
        compression = settings.exr_compression
    elif suffix == '.png':
        compression = settings.png_compression
    elif suffix in {'.jpg', '.jpeg'}:
        quality = settings.jpeg_quality
    save_image_oiio(
        str(path),
        data,
        bit_depth=bit_depth,
        color_space=color_space,
        cctf_encoding=cctf_encoding,
        quality=quality,
        compression=compression,
    )


def write_handoff(path: Path, image: np.ndarray, source_color_space: str) -> None:
    """线性显影输出 → ProPhoto 线性 16-bit 交接图。"""
    data = np.asarray(image)
    if source_color_space != HANDOFF_COLOR_SPACE:
        data = np.asarray(
            colour.RGB_to_RGB(
                data,
                source_color_space,
                HANDOFF_COLOR_SPACE,
                apply_cctf_decoding=False,
                apply_cctf_encoding=False,
            ),
            dtype=np.float32,
        )
    save_image_oiio(
        str(path),
        data,
        bit_depth=16,
        color_space=HANDOFF_COLOR_SPACE,
        cctf_encoding=False,
    )


__all__ = [
    'DISPLAY_PREVIEW_MAX_EDGE',
    'HANDOFF_COLOR_SPACE',
    'LoadedInput',
    'PREVIEW_MAX_EDGE',
    'PREVIEW_SCALES',
    'convert_to_saving_space',
    'display_preview_array',
    'export_image',
    'export_target_path',
    'is_raw_path',
    'load_input',
    'output_to_display_rgb',
    'preview_source',
    'sanitize_filename',
    'save_display_png',
    'save_export_file',
    'save_original_png',
    'write_handoff',
]
