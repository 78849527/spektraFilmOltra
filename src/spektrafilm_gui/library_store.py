"""照片库数据层。

只负责“库里有哪些照片、它们属于哪个文件夹、用户给它们打了什么标记、
上次调成什么样”。照片本身 **不复制**，库只记住原文件路径；缩略图单独缓存。
删除照片永远只从库里移出记录，不动磁盘文件。

存储位置与 GUI 默认状态保持一致（``AppConfigLocation`` 下的 ``library/``），
方便打包后跟随应用配置目录走。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

from spektrafilm_gui import app_paths
from spektrafilm_gui.persistence import default_gui_state_path

RAW_SUFFIXES = frozenset({
    '.cr2', '.cr3', '.nef', '.arw', '.dng', '.raf', '.orf', '.rw2', '.pef',
    '.srw', '.3fr', '.iiq', '.x3f', '.erf', '.mef', '.mos', '.mrw', '.nrw',
    '.rwl', '.srf', '.sr2',
})

RGB_SUFFIXES = frozenset({
    '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.webp', '.exr', '.hdr',
})

SUPPORTED_SUFFIXES = RAW_SUFFIXES | RGB_SUFFIXES

COLOR_LABELS = ('red', 'yellow', 'green', 'blue')

COLOR_LABEL_NAMES = {
    'red': '红',
    'yellow': '黄',
    'green': '绿',
    'blue': '蓝',
}

INBOX_FOLDER_ID = 'inbox'
INBOX_FOLDER_NAME = '导入的照片'

LIBRARY_VERSION = 1


def is_supported_image(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_SUFFIXES


def is_raw_image(path: str | Path) -> bool:
    return Path(path).suffix.lower() in RAW_SUFFIXES


def _stable_id(text: str) -> str:
    return hashlib.sha1(text.encode('utf-8', 'surrogateescape')).hexdigest()[:16]


def default_library_root() -> Path:
    return app_paths.app_data_dir() / 'library'


@dataclass(slots=True)
class LibraryFolder:
    id: str
    name: str
    path: str
    added_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'path': self.path,
            'added_at': self.added_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'LibraryFolder':
        return cls(
            id=str(data.get('id') or ''),
            name=str(data.get('name') or ''),
            path=str(data.get('path') or ''),
            added_at=float(data.get('added_at') or 0.0),
        )


@dataclass(slots=True)
class LibraryItem:
    id: str
    path: str
    name: str
    folder_id: str = INBOX_FOLDER_ID
    added_at: float = field(default_factory=time.time)
    favorite: bool = False
    color: str = ''
    adjusted: bool = False
    film_stock: str = ''
    print_paper: str = ''
    width: int = 0
    height: int = 0
    is_raw: bool = False
    file_size: int = 0
    mtime: float = 0.0
    state: dict[str, Any] | None = None

    @property
    def exists(self) -> bool:
        return bool(self.path) and Path(self.path).exists()

    @property
    def suffix(self) -> str:
        return Path(self.path).suffix.lower()

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'path': self.path,
            'name': self.name,
            'folder_id': self.folder_id,
            'added_at': self.added_at,
            'favorite': bool(self.favorite),
            'color': self.color,
            'adjusted': bool(self.adjusted),
            'film_stock': self.film_stock,
            'print_paper': self.print_paper,
            'width': int(self.width),
            'height': int(self.height),
            'is_raw': bool(self.is_raw),
            'file_size': int(self.file_size),
            'mtime': float(self.mtime),
            'state': self.state,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'LibraryItem':
        color = str(data.get('color') or '')
        if color not in COLOR_LABELS:
            color = ''
        state = data.get('state')
        return cls(
            id=str(data.get('id') or ''),
            path=str(data.get('path') or ''),
            name=str(data.get('name') or ''),
            folder_id=str(data.get('folder_id') or INBOX_FOLDER_ID),
            added_at=float(data.get('added_at') or 0.0),
            favorite=bool(data.get('favorite')),
            color=color,
            adjusted=bool(data.get('adjusted')),
            film_stock=str(data.get('film_stock') or ''),
            print_paper=str(data.get('print_paper') or ''),
            width=int(data.get('width') or 0),
            height=int(data.get('height') or 0),
            is_raw=bool(data.get('is_raw')),
            file_size=int(data.get('file_size') or 0),
            mtime=float(data.get('mtime') or 0.0),
            state=state if isinstance(state, dict) else None,
        )


class LibraryStore:
    """JSON 照片目录。所有修改都立即落盘（小文件，写入很快）。"""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root is not None else default_library_root()
        self.index_path = self.root / 'library.json'
        self.thumbs_dir = self.root / 'thumbs'
        self.folders: dict[str, LibraryFolder] = {}
        self.items: dict[str, LibraryItem] = {}
        self._load()

    # ── 读写 ────────────────────────────────────────────────────
    def _load(self) -> None:
        if not self.index_path.exists():
            return
        try:
            with self.index_path.open('r', encoding='utf-8') as handle:
                data = json.load(handle)
        except (OSError, ValueError, TypeError):
            self._quarantine_corrupt_index()
            return
        if not isinstance(data, dict):
            self._quarantine_corrupt_index()
            return
        for folder_data in data.get('folders', []) or []:
            if not isinstance(folder_data, dict):
                continue
            folder = LibraryFolder.from_dict(folder_data)
            if folder.id:
                self.folders[folder.id] = folder
        for item_data in data.get('items', []) or []:
            if not isinstance(item_data, dict):
                continue
            item = LibraryItem.from_dict(item_data)
            if item.id and item.path:
                self.items[item.id] = item
        if any(item.folder_id == INBOX_FOLDER_ID for item in self.items.values()):
            self.ensure_inbox()

    def _quarantine_corrupt_index(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            target = self.index_path.with_suffix(f'.corrupt-{int(time.time())}.json')
            shutil.copy2(self.index_path, target)
        except OSError:
            pass

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            'version': LIBRARY_VERSION,
            'folders': [folder.to_dict() for folder in self._sorted_folders()],
            'items': [item.to_dict() for item in self._sorted_items()],
        }
        temp_path = self.index_path.with_suffix('.json.tmp')
        with temp_path.open('w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(',', ':'))
        os.replace(temp_path, self.index_path)

    # ── 查询 ────────────────────────────────────────────────────
    def _sorted_folders(self) -> list[LibraryFolder]:
        return sorted(self.folders.values(), key=lambda folder: (folder.name.lower(), folder.id))

    def _sorted_items(self) -> list[LibraryItem]:
        return sorted(self.items.values(), key=lambda item: (-item.added_at, item.name.lower()))

    def all_items(self) -> list[LibraryItem]:
        return self._sorted_items()

    def all_folders(self) -> list[LibraryFolder]:
        return self._sorted_folders()

    def item(self, item_id: str) -> LibraryItem | None:
        return self.items.get(item_id)

    def item_by_path(self, path: str | Path) -> LibraryItem | None:
        resolved = str(Path(path).expanduser().resolve())
        for item in self.items.values():
            if item.path == resolved:
                return item
        return None

    def folder(self, folder_id: str) -> LibraryFolder | None:
        return self.folders.get(folder_id)

    def items_in_folder(self, folder_id: str) -> list[LibraryItem]:
        return [item for item in self._sorted_items() if item.folder_id == folder_id]

    def folder_count(self) -> int:
        # “导入的照片”不算一个文件夹，避免统计虚高
        return len([folder for folder in self.folders.values() if folder.id != INBOX_FOLDER_ID])

    def item_count(self) -> int:
        return len(self.items)

    # ── 修改 ────────────────────────────────────────────────────
    def add_folder(self, path: str | Path, *, recursive: bool = True) -> tuple[LibraryFolder, list[LibraryItem]]:
        folder_path = Path(path).expanduser().resolve()
        if not folder_path.is_dir():
            raise NotADirectoryError(str(folder_path))
        folder_id = _stable_id(str(folder_path))
        folder = self.folders.get(folder_id)
        is_new = folder is None
        if folder is None:
            folder = LibraryFolder(
                id=folder_id,
                name=folder_path.name or str(folder_path),
                path=str(folder_path),
            )
            self.folders[folder_id] = folder

        paths = list(iter_image_paths(folder_path, recursive=recursive))
        if not paths and is_new:
            # 空文件夹不留一张空卡片；等真有照片时再导入
            self.folders.pop(folder_id, None)
            self.save()
            return folder, []
        added: list[LibraryItem] = []
        for image_path in paths:
            item = self.add_photo(image_path, folder_id=folder_id, save=False)
            if item is not None:
                added.append(item)
        self.save()
        return folder, added

    def ensure_inbox(self) -> LibraryFolder:
        folder = self.folders.get(INBOX_FOLDER_ID)
        if folder is None:
            folder = LibraryFolder(id=INBOX_FOLDER_ID, name=INBOX_FOLDER_NAME, path='')
            self.folders[INBOX_FOLDER_ID] = folder
        return folder

    def add_photo(
        self,
        path: str | Path,
        *,
        folder_id: str | None = None,
        save: bool = True,
    ) -> LibraryItem | None:
        image_path = Path(path).expanduser().resolve()
        if not image_path.is_file() or not is_supported_image(image_path):
            return None
        try:
            stat = image_path.stat()
        except OSError:
            return None

        item_id = _stable_id(str(image_path))
        existing = self.items.get(item_id)
        target_folder = folder_id or (existing.folder_id if existing is not None else INBOX_FOLDER_ID)
        if target_folder != INBOX_FOLDER_ID and target_folder not in self.folders:
            target_folder = INBOX_FOLDER_ID
        if target_folder == INBOX_FOLDER_ID:
            self.ensure_inbox()

        if existing is None:
            item = LibraryItem(
                id=item_id,
                path=str(image_path),
                name=image_path.name,
                folder_id=target_folder,
                is_raw=is_raw_image(image_path),
                file_size=int(stat.st_size),
                mtime=float(stat.st_mtime),
            )
            self.items[item_id] = item
        else:
            item = replace(
                existing,
                name=image_path.name,
                folder_id=target_folder,
                is_raw=is_raw_image(image_path),
                file_size=int(stat.st_size),
                mtime=float(stat.st_mtime),
            )
            self.items[item_id] = item

        if save:
            self.save()
        return item

    def add_photos(self, paths: Iterable[str | Path], *, folder_id: str | None = None) -> list[LibraryItem]:
        added = [item for path in paths if (item := self.add_photo(path, folder_id=folder_id, save=False)) is not None]
        self.save()
        return added

    def update_item(self, item_id: str, *, save: bool = True, **fields: Any) -> LibraryItem | None:
        item = self.items.get(item_id)
        if item is None:
            return None
        allowed = {field_name for field_name in LibraryItem.__dataclass_fields__ if field_name != 'id'}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return item
        updated = replace(item, **updates)
        self.items[item_id] = updated
        if save:
            self.save()
        return updated

    def set_favorite(self, item_id: str, favorite: bool) -> LibraryItem | None:
        return self.update_item(item_id, favorite=bool(favorite))

    def set_color(self, item_id: str, color: str) -> LibraryItem | None:
        return self.update_item(item_id, color=color if color in COLOR_LABELS else '')

    def set_adjustment_state(
        self,
        item_id: str,
        state: dict[str, Any] | None,
        *,
        film_stock: str = '',
        print_paper: str = '',
        adjusted: bool = True,
    ) -> LibraryItem | None:
        return self.update_item(
            item_id,
            state=state,
            film_stock=film_stock,
            print_paper=print_paper,
            adjusted=bool(adjusted),
        )

    def remove_item(self, item_id: str) -> bool:
        """只移出库，不删除磁盘文件。"""
        if item_id not in self.items:
            return False
        del self.items[item_id]
        self.save()
        return True

    def remove_items(self, item_ids: Iterable[str]) -> int:
        removed = 0
        for item_id in list(item_ids):
            if item_id in self.items:
                del self.items[item_id]
                removed += 1
        if removed:
            self.save()
        return removed

    # ── 缩略图路径 ──────────────────────────────────────────────
    def thumbnail_path(self, item: LibraryItem) -> Path:
        return self.thumbs_dir / f'{item.id}.jpg'

    def has_fresh_thumbnail(self, item: LibraryItem) -> bool:
        thumb_path = self.thumbnail_path(item)
        if not thumb_path.exists():
            return False
        try:
            thumb_mtime = thumb_path.stat().st_mtime
            return item.mtime <= 0 or thumb_mtime >= item.mtime
        except OSError:
            return False


def iter_image_paths(root: Path, *, recursive: bool = True) -> Iterable[Path]:
    if recursive:
        walker = os.walk(root)
    else:
        walker = [(str(root), [], [path.name for path in root.iterdir() if path.is_file()])]
    for directory, _dirnames, filenames in walker:
        for filename in sorted(filenames):
            path = Path(directory) / filename
            if path.name.startswith('.'):
                continue
            if is_supported_image(path):
                yield path
