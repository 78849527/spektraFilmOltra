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
    'EXPORT_FORMATS',
    'ExportSettings',
    'export_settings_path',
    'load_export_settings',
    'save_export_settings',
]
