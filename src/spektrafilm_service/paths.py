"""Electron 服务层使用的缓存目录。

用户资产（照片库、预设、导出）沿用 Qt 版的目录；这里只放可丢弃的渲染缓存。
"""

from __future__ import annotations

from pathlib import Path

from spektrafilm_gui import app_paths


def cache_root() -> Path:
    path = app_paths.app_data_dir() / 'render_cache'
    path.mkdir(parents=True, exist_ok=True)
    return path


def preview_dir() -> Path:
    path = cache_root() / 'preview'
    path.mkdir(parents=True, exist_ok=True)
    return path


def thumb_dir() -> Path:
    path = app_paths.app_data_dir() / 'library' / 'thumbs'
    path.mkdir(parents=True, exist_ok=True)
    return path


def handoff_dir() -> Path:
    path = Path(app_paths.app_data_dir()) / 'library'
    path.mkdir(parents=True, exist_ok=True)
    return path


__all__ = ['cache_root', 'handoff_dir', 'preview_dir', 'thumb_dir']
