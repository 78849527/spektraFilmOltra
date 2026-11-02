from __future__ import annotations

import json
from pathlib import Path

from qtpy import QtGui

from spektrafilm_gui import library_store as store_module
from spektrafilm_gui import library_thumbs as thumbs_module


def _write_png(path: Path, color: str = '#808080', size: int = 32) -> Path:
    image = QtGui.QImage(size, size, QtGui.QImage.Format_RGB888)
    image.fill(QtGui.QColor(color))
    assert image.save(str(path), 'PNG')
    return path


def test_add_photo_is_idempotent_and_keeps_folder(tmp_path: Path) -> None:
    photo = _write_png(tmp_path / 'a.png')
    store = store_module.LibraryStore(tmp_path / 'library')

    first = store.add_photo(photo)
    second = store.add_photo(photo)

    assert first is not None and second is not None
    assert first.id == second.id
    assert store.item_count() == 1
    assert second.folder_id == store_module.INBOX_FOLDER_ID
    assert second.is_raw is False
    assert second.file_size > 0


def test_add_folder_scans_recursively_and_ignores_unsupported(tmp_path: Path) -> None:
    root = tmp_path / 'shoot'
    (root / 'day1').mkdir(parents=True)
    _write_png(root / 'one.png')
    _write_png(root / 'day1' / 'two.png')
    (root / 'notes.txt').write_text('not an image', encoding='utf-8')

    store = store_module.LibraryStore(tmp_path / 'library')
    folder, added = store.add_folder(root)

    assert folder.name == 'shoot'
    assert len(added) == 2
    assert store.folder_count() == 1
    assert store.item_count() == 2
    assert {item.name for item in store.items_in_folder(folder.id)} == {'one.png', 'two.png'}


def test_favorite_color_and_state_roundtrip(tmp_path: Path) -> None:
    photo = _write_png(tmp_path / 'a.png')
    store = store_module.LibraryStore(tmp_path / 'library')
    item = store.add_photo(photo)
    assert item is not None

    store.set_favorite(item.id, True)
    store.set_color(item.id, 'red')
    store.set_adjustment_state(
        item.id,
        {'simulation': {'selection': {'film_stock': 'kodak_portra_400', 'print_paper': 'kodak_supra_endura'}}},
        film_stock='kodak_portra_400',
        print_paper='kodak_supra_endura',
    )

    reloaded = store_module.LibraryStore(tmp_path / 'library')
    saved = reloaded.item(item.id)
    assert saved is not None
    assert saved.favorite is True
    assert saved.color == 'red'
    assert saved.adjusted is True
    assert saved.film_stock == 'kodak_portra_400'
    assert saved.state is not None


def test_remove_item_never_deletes_source_file(tmp_path: Path) -> None:
    photo = _write_png(tmp_path / 'a.png')
    store = store_module.LibraryStore(tmp_path / 'library')
    item = store.add_photo(photo)
    assert item is not None

    assert store.remove_item(item.id) is True
    assert store.item_count() == 0
    assert photo.exists()


def test_corrupt_index_is_quarantined_not_crashed(tmp_path: Path) -> None:
    root = tmp_path / 'library'
    root.mkdir(parents=True)
    (root / 'library.json').write_text('{ not json', encoding='utf-8')

    store = store_module.LibraryStore(root)

    assert store.item_count() == 0
    assert list(root.glob('library.corrupt-*.json'))


def test_invalid_color_falls_back_to_empty(tmp_path: Path) -> None:
    photo = _write_png(tmp_path / 'a.png')
    store = store_module.LibraryStore(tmp_path / 'library')
    item = store.add_photo(photo)
    assert item is not None

    updated = store.set_color(item.id, 'chartreuse')

    assert updated is not None
    assert updated.color == ''


def test_thumbnail_for_png_is_generated_and_cached(tmp_path: Path) -> None:
    photo = _write_png(tmp_path / 'a.png', size=800)
    store = store_module.LibraryStore(tmp_path / 'library')
    item = store.add_photo(photo)
    assert item is not None

    image, width, height = thumbs_module.generate_thumbnail(photo)

    assert not image.isNull()
    assert width == 800 and height == 800
    assert max(image.width(), image.height()) <= thumbs_module.THUMB_MAX_SIZE

    target = store.thumbnail_path(item)
    target.parent.mkdir(parents=True, exist_ok=True)
    assert image.save(str(target), 'JPG', thumbs_module.THUMB_QUALITY)
    assert store.has_fresh_thumbnail(item)


def test_index_payload_is_compact_json_with_chinese_names(tmp_path: Path) -> None:
    photo = _write_png(tmp_path / '海边的照片.png')
    store = store_module.LibraryStore(tmp_path / 'library')
    store.add_photo(photo)

    payload = json.loads((tmp_path / 'library' / 'library.json').read_text(encoding='utf-8'))

    assert payload['version'] == store_module.LIBRARY_VERSION
    assert payload['items'][0]['name'] == '海边的照片.png'
    assert '海边的照片' in (tmp_path / 'library' / 'library.json').read_text(encoding='utf-8')
