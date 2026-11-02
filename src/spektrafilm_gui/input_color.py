"""输入图像的色彩空间识别。

JPEG/PNG/TIFF 这类编码图像默认按 sRGB 解码；如果文件带 ICC，就按 ICC 描述
映射到引擎支持的色彩空间。EXR/HDR 视为线性，RAW 由 rawpy 直接输出线性
ProPhoto。识别失败时一律回退到 sRGB + CCTF 解码，避免把编码值当线性值烧进
显影管线。
"""

from __future__ import annotations

import io
from pathlib import Path

_LINEAR_SUFFIXES = frozenset({'.exr', '.hdr'})
_RAW_SUFFIXES = frozenset({
    '.cr2', '.cr3', '.nef', '.arw', '.dng', '.raf', '.orf', '.rw2', '.pef',
    '.srw', '.3fr', '.iiq', '.x3f', '.erf', '.mef', '.mos', '.mrw', '.nrw',
    '.rwl', '.srf', '.sr2',
})
_ENCODED_SUFFIXES = frozenset({'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.webp'})

_ICC_MAPPINGS = (
    ('display p3', 'Display P3'),
    ('dci-p3', 'DCI-P3'),
    ('adobe rgb', 'Adobe RGB (1998)'),
    ('prophoto', 'ProPhoto RGB'),
    ('romm', 'ProPhoto RGB'),
    ('aces', 'ACES2065-1'),
    ('rec.2020', 'ITU-R BT.2020'),
    ('bt.2020', 'ITU-R BT.2020'),
    ('rec.709', 'sRGB'),
    ('bt.709', 'sRGB'),
    ('srgb', 'sRGB'),
    ('iec61966', 'sRGB'),
)


def _icc_profile_description(path: Path) -> str:
    try:
        from PIL import Image, ImageCms
    except ImportError:
        return ''
    try:
        with Image.open(path) as image:
            icc = image.info.get('icc_profile')
            if not icc:
                return ''
            profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            return str(ImageCms.getProfileDescription(profile) or '')
    except Exception:
        return ''


def detect_input_color_space(path: str | Path) -> tuple[str, bool]:
    """返回 (色彩空间名, 是否需要 CCTF 解码)。"""
    image_path = Path(path)
    suffix = image_path.suffix.lower()
    if suffix in _RAW_SUFFIXES:
        return 'ProPhoto RGB', False
    if suffix in _LINEAR_SUFFIXES:
        return 'ACES2065-1', False
    description = _icc_profile_description(image_path).lower()
    if description:
        for token, color_space in _ICC_MAPPINGS:
            if token in description:
                return color_space, color_space != 'ACES2065-1'
    if suffix in _ENCODED_SUFFIXES:
        return 'sRGB', True
    return 'sRGB', True


__all__ = ['detect_input_color_space']
