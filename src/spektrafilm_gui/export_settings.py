"""导出设置：格式、画质/压缩、目录、文件名与长边尺寸。

设置落在应用配置目录的 export_settings.json，与 GUI 默认状态同处一室；
读取失败一律回退默认值，不影响导出。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from spektrafilm_gui import app_paths


EXPORT_FORMATS = ('JPEG', 'PNG', 'TIFF', 'EXR')
TEMP_SUFFIX = '{name}_spektrafilm'
DIRECT_EXPORT_LONG_EDGE_RATIO = 0.9
DIRECT_EXPORT_PNG_COMPRESSION = 9


@dataclass(frozen=True, slots=True)
class DirectExportSettings:
    """箭头菜单「直接导出」的固定配置，与完整导出面板互不覆盖。

    PNG 没有「质量」参数，这里用 90% 长边 + 最高压缩表达「90% 质量」。
    """

    format: str = 'PNG'
    png_compression: int = DIRECT_EXPORT_PNG_COMPRESSION
    bit_depth: int = 8
    long_edge_ratio: float = DIRECT_EXPORT_LONG_EDGE_RATIO
    filename_template: str = TEMP_SUFFIX

    def to_export_settings(self, image_long_edge: int) -> ExportSettings:
        long_edge = 0
        if int(image_long_edge) > 0:
            long_edge = max(1, int(round(int(image_long_edge) * self.long_edge_ratio)))
        return ExportSettings(
            format=self.format,
            png_compression=self.png_compression,
            bit_depth=self.bit_depth,
            long_edge=long_edge,
            directory='',
            filename_template=self.filename_template,
        ).normalized()


@dataclass(slots=True)
class ExportSettings:
    format: str = 'JPEG'
    jpeg_quality: int = 92
    png_compression: int = 6
    tiff_compression: str = 'zip'
    exr_compression: str = 'zip'
    bit_depth: int = 16
    long_edge: int = 0
    directory: str = ''
    filename_template: str = TEMP_SUFFIX

    @property
    def extension(self) -> str:
        return {
            'JPEG': 'jpg',
            'PNG': 'png',
            'TIFF': 'tif',
            'EXR': 'exr',
        }.get(self.format, 'jpg')

    def normalized(self) -> 'ExportSettings':
        return replace(
            self,
            format=self.format if self.format in EXPORT_FORMATS else 'JPEG',
            jpeg_quality=max(1, min(100, int(self.jpeg_quality))),
            png_compression=max(0, min(9, int(self.png_compression))),
            tiff_compression=self.tiff_compression if self.tiff_compression in {'none', 'zip', 'lzw'} else 'zip',
            exr_compression=self.exr_compression if self.exr_compression in {'zip', 'piz', 'rle'} else 'zip',
            bit_depth=self.bit_depth if self.bit_depth in {8, 16, 32} else 16,
            long_edge=max(0, int(self.long_edge)),
            directory=str(self.directory).strip(),
            filename_template=self.filename_template.strip() or TEMP_SUFFIX,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self.normalized())

    @classmethod
    def from_dict(cls, data: object) -> 'ExportSettings':
        if not isinstance(data, dict):
            return cls()
        defaults = cls()
        fields = {field_name for field_name in defaults.__dataclass_fields__}
        values = {name: data[name] for name in fields if name in data}
        try:
            return replace(defaults, **values).normalized()
        except (TypeError, ValueError):
            return cls()


def export_settings_path() -> Path:
    return app_paths.app_config_dir() / 'export_settings.json'


def load_export_settings() -> ExportSettings:
    path = export_settings_path()
    if not path.exists():
        return ExportSettings()
    try:
        with path.open('r', encoding='utf-8') as handle:
            return ExportSettings.from_dict(json.load(handle))
    except (OSError, ValueError, TypeError):
        return ExportSettings()


def save_export_settings(settings: ExportSettings) -> None:
    path = export_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        json.dump(settings.to_dict(), handle, indent=2)


__all__ = [
    'DIRECT_EXPORT_LONG_EDGE_RATIO',
    'DIRECT_EXPORT_PNG_COMPRESSION',
    'DirectExportSettings',
    'EXPORT_FORMATS',
    'ExportSettings',
    'export_settings_path',
    'load_export_settings',
    'save_export_settings',
]
