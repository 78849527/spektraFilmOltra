"""缩略图生成：不依赖 Qt，直接写 JPEG 缓存。"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image

from spektrafilm_gui.library_store import is_raw_image

THUMB_MAX_SIZE = 512
THUMB_QUALITY = 88


def generate_thumbnail(source: str | Path, target: str | Path) -> tuple[int, int]:
    image_path = Path(source)
    if is_raw_image(image_path):
        image, width, height = _read_raw(image_path)
    else:
        image, width, height = _read_rgb(image_path)

    if max(image.width, image.height) > THUMB_MAX_SIZE:
        image = image.copy()
        image.thumbnail((THUMB_MAX_SIZE, THUMB_MAX_SIZE), Image.Resampling.LANCZOS)

    target_path = Path(target)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    image.convert('RGB').save(target_path, 'JPEG', quality=THUMB_QUALITY)
    return int(width), int(height)


def _read_raw(path: Path) -> tuple[Image.Image, int, int]:
    import rawpy

    with rawpy.imread(str(path)) as raw:
        width = int(getattr(raw.sizes, 'width', 0) or 0)
        height = int(getattr(raw.sizes, 'height', 0) or 0)
        try:
            thumb = raw.extract_thumb()
        except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError, AttributeError):
            thumb = None
        if thumb is not None:
            image = Image.open(io.BytesIO(thumb.data))
            image = _exif_transpose(image)
            if width and height:
                return image, width, height
            return image, image.width, image.height

        array = raw.postprocess(half_size=True, use_camera_wb=True, no_auto_bright=False)
        flip = int(getattr(raw.sizes, 'flip', 0) or 0)
        image = _apply_raw_flip(Image.fromarray(array), flip)
        if not width or not height:
            width, height = image.width, image.height
        return image, int(width), int(height)


def _read_rgb(path: Path) -> tuple[Image.Image, int, int]:
    try:
        with Image.open(path) as image:
            image = _exif_transpose(image)
            width, height = image.size
            copy = image.copy()
        return copy, int(width), int(height)
    except Exception:  # noqa: BLE001 - EXR 等格式交给 OIIO
        from spektrafilm.utils.io import load_image_oiio

        array = np.asarray(load_image_oiio(str(path)))[..., :3]
        if array.dtype.kind == 'f':
            array = np.clip(array, 0.0, 1.0) ** (1.0 / 2.2)
        array = np.uint8(np.clip(array, 0.0, 1.0) * 255.0)
        image = Image.fromarray(array, mode='RGB')
        return image, int(image.width), int(image.height)


def _exif_transpose(image: Image.Image) -> Image.Image:
    from PIL import ImageOps

    return ImageOps.exif_transpose(image)


def _apply_raw_flip(image: Image.Image, flip: int) -> Image.Image:
    if flip == 3:
        return image.rotate(180, expand=True)
    if flip == 5:
        return image.transpose(Image.Transpose.FLIP_LEFT_RIGHT).rotate(90, expand=True)
    if flip == 6:
        return image.rotate(270, expand=True)
    return image


__all__ = ['THUMB_MAX_SIZE', 'generate_thumbnail']
