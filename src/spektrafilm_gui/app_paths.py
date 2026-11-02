"""应用数据目录：不依赖 QCoreApplication 的当前名字。

napari 在创建 Viewer 时会把 ``QCoreApplication.applicationName`` 改成
``napari``，于是任何走 ``QStandardPaths`` 的默认路径都会跑到
``.../napari/napari/`` 下面。这里改成按固定的产品名直接算路径，
路径与进程状态无关，换启动方式也不会漂移。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = 'Spektrafilm'


def _base_dir(env_var: str, macos_folder: str, linux_default: Path) -> Path:
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / macos_folder / APP_NAME
    override = os.environ.get(env_var)
    if override:
        return Path(override) / APP_NAME
    if os.name == 'nt':
        appdata = os.environ.get('APPDATA') or str(Path.home() / 'AppData' / 'Roaming')
        return Path(appdata) / APP_NAME
    return linux_default / APP_NAME


def app_data_dir() -> Path:
    """可写数据目录：照片库、缩略图缓存。"""
    return _base_dir('XDG_DATA_HOME', 'Application Support', Path.home() / '.local' / 'share')


def app_config_dir() -> Path:
    """配置目录：界面默认状态。"""
    return _base_dir('XDG_CONFIG_HOME', 'Preferences', Path.home() / '.config')


def legacy_napari_data_dir() -> Path:
    """旧版本误落在 napari 名下的数据目录，仅用于一次性迁移。"""
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'napari' / 'napari'
    if os.name == 'nt':
        appdata = os.environ.get('APPDATA') or str(Path.home() / 'AppData' / 'Roaming')
        return Path(appdata) / 'napari' / 'napari'
    return Path.home() / '.local' / 'share' / 'napari' / 'napari'
