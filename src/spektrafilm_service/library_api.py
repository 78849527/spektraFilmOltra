"""照片库接口：直接复用 Qt 版的数据层，只补一个 Qt-free 的缩略图任务。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spektrafilm_gui.library_store import INBOX_FOLDER_ID, LibraryItem, LibraryStore

from spektrafilm_service import thumbs


class LibraryApi:
    def __init__(self) -> None:
        self.store = LibraryStore()

    def snapshot(self) -> dict[str, Any]:
        return {
            'folders': [folder.to_dict() for folder in self.store.all_folders()],
            'items': [item.to_dict() for item in self.store.all_items()],
            'folder_count': self.store.folder_count(),
            'item_count': self.store.item_count(),
            'inbox_id': INBOX_FOLDER_ID,
        }

    def scan(self, path: str) -> dict[str, Any]:
        folder, added = self.store.add_folder(path)
        return {
            'folder': folder.to_dict(),
            'added': [item.to_dict() for item in added],
            **self.snapshot(),
        }

    def add_photos(self, paths: list[str], folder_id: str | None = None) -> dict[str, Any]:
        items = self.store.add_photos(paths, folder_id=folder_id)
        return {'added': [item.to_dict() for item in items], **self.snapshot()}

    def remove(self, item_ids: list[str]) -> dict[str, Any]:
        removed = self.store.remove_items(item_ids)
        return {'removed': removed, **self.snapshot()}

    def mark(self, item_id: str, *, favorite: bool | None = None, color: str | None = None) -> dict[str, Any]:
        if favorite is not None:
            self.store.set_favorite(item_id, favorite)
        if color is not None:
            self.store.set_color(item_id, color)
        item = self.store.item(item_id)
        return {'item': item.to_dict() if item is not None else None}

    def item(self, item_id: str) -> LibraryItem | None:
        return self.store.item(item_id)

    def save_state(self, item_id: str, state: dict[str, Any] | None, *, film_stock: str = '', print_paper: str = '') -> dict[str, Any]:
        item = self.store.set_adjustment_state(
            item_id,
            state,
            film_stock=film_stock,
            print_paper=print_paper,
            adjusted=True,
        )
        return {'item': item.to_dict() if item is not None else None}

    def thumb(self, item_id: str) -> dict[str, Any]:
        item = self.store.item(item_id)
        if item is None:
            raise LookupError('照片不在库中')
        target = self.store.thumbnail_path(item)
        if self.store.has_fresh_thumbnail(item) and target.exists():
            return {'path': str(target), 'width': item.width, 'height': item.height, 'cached': True}
        width, height = thumbs.generate_thumbnail(item.path, target)
        if not item.width or not item.height:
            self.store.update_item(item_id, width=width, height=height)
        return {'path': str(target), 'width': width, 'height': height, 'cached': False}


__all__ = ['LibraryApi']
