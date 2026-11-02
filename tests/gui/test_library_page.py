from __future__ import annotations

from pathlib import Path

from qtpy import QtCore, QtGui, QtTest, QtWidgets

from spektrafilm_gui import library_page as page_module
from spektrafilm_gui import library_store as store_module
from spektrafilm_gui.library_thumbs import ThumbnailService


def _app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _png(path: Path, color: str = '#808080', size: int = 64) -> Path:
    image = QtGui.QImage(size, size, QtGui.QImage.Format_RGB888)
    image.fill(QtGui.QColor(color))
    assert image.save(str(path), 'PNG')
    return path


def _page(tmp_path: Path, count: int = 3) -> tuple[page_module.LibraryPage, store_module.LibraryStore]:
    _app()
    store = store_module.LibraryStore(tmp_path / 'library')
    for index in range(count):
        store.add_photo(_png(tmp_path / f'photo_{index}.png', '#{:02X}8080'.format(40 + index * 30)))
    service = ThumbnailService(store, max_threads=1)
    page = page_module.LibraryPage(store, thumbnails=service)
    page.resize(1100, 760)
    QtTest.QTest.qWait(120)
    _app().processEvents()
    return page, store


def test_library_page_lists_photos_and_stats(tmp_path: Path) -> None:
    page, store = _page(tmp_path)

    assert len(page._cards) == 3
    assert page._content_stack.currentIndex() == 0
    assert '3 张照片' in page._section_count.text()
    assert '0 个文件夹' in page._subtitle.text()

    page.deleteLater()


def test_favorite_filter_shows_only_favorites(tmp_path: Path) -> None:
    page, store = _page(tmp_path)
    favorite = store.all_items()[0]
    store.set_favorite(favorite.id, True)

    page._set_filter('favorite')
    _app().processEvents()

    assert len(page._cards) == 1
    assert favorite.id in page._cards
    assert page._section_title.text() == '收藏'

    page.deleteLater()


def test_color_filter_and_search(tmp_path: Path) -> None:
    page, store = _page(tmp_path)
    items = store.all_items()
    store.set_color(items[0].id, 'red')
    page._set_filter('red')
    _app().processEvents()
    assert list(page._cards) == [items[0].id]

    page._set_filter('all')
    page._search.setText('photo_2')
    QtTest.QTest.qWait(250)
    _app().processEvents()
    assert len(page._cards) == 1

    page.deleteLater()


def test_list_view_uses_rows(tmp_path: Path) -> None:
    page, _store = _page(tmp_path)

    page._set_view_mode('list')
    _app().processEvents()

    assert page._content_stack.currentIndex() == 1
    assert all(isinstance(card, page_module.PhotoRow) for card in page._cards.values())

    page._set_view_mode('grid')
    _app().processEvents()
    assert all(isinstance(card, page_module.PhotoCard) for card in page._cards.values())

    page.deleteLater()


def test_folder_import_and_filter(tmp_path: Path) -> None:
    page, store = _page(tmp_path, count=0)
    folder_dir = tmp_path / 'shoot'
    folder_dir.mkdir()
    _png(folder_dir / 'a.png')
    _png(folder_dir / 'b.png')

    page.import_paths([str(folder_dir)])
    QtTest.QTest.qWait(150)
    _app().processEvents()

    assert store.folder_count() == 1
    assert len(page._cards) == 2
    folder_id = next(folder_id for folder_id in page._folder_cards if folder_id)
    page._set_folder_filter(folder_id)
    _app().processEvents()
    assert len(page._cards) == 2
    assert page._section_title.text() == 'shoot'

    page._set_folder_filter('')
    _app().processEvents()
    assert len(page._cards) == 2

    page.deleteLater()


def test_remove_item_only_removes_from_library(tmp_path: Path) -> None:
    page, store = _page(tmp_path, count=1)
    item = store.all_items()[0]
    source = Path(item.path)

    page._on_remove_requested(item.id)
    _app().processEvents()

    assert store.item(item.id) is None
    assert source.exists()
    assert not page._cards

    page.deleteLater()


def test_empty_state_switches_between_blank_and_no_results(tmp_path: Path) -> None:
    page, store = _page(tmp_path, count=0)

    assert page._content_stack.currentIndex() == 2
    assert page._empty_title.text() == '照片库还是空的'

    store.add_photo(_png(tmp_path / 'one.png'))
    page.refresh()
    page._search.setText('does-not-exist')
    QtTest.QTest.qWait(250)
    _app().processEvents()

    assert page._empty_title.text() == '没有匹配的照片'
    assert page._empty_buttons.isHidden()

    page.deleteLater()


def test_open_and_favorite_signals(tmp_path: Path) -> None:
    page, store = _page(tmp_path, count=1)
    item = store.all_items()[0]
    opened: list[str] = []
    page.open_item_requested.connect(opened.append)

    page._cards[item.id].opened.emit(item.id)
    assert opened == [item.id]
    assert page._cards[item.id].property('selected') == 'true'

    page._on_favorite_requested(item.id, True)
    _app().processEvents()
    assert store.item(item.id).favorite is True
    assert page._cards[item.id].item.favorite is True

    page.deleteLater()


def test_visible_limit_shows_more_button(tmp_path: Path) -> None:
    page, store = _page(tmp_path, count=5)
    page._visible_limit = 2
    page.refresh()
    _app().processEvents()

    assert len(page._cards) == 2
    assert not page._more_button.isHidden()
    assert '还有 3 张' in page._more_button.text()

    page._show_more()
    _app().processEvents()
    assert len(page._cards) == 5
    assert page._more_button.isHidden()

    page.deleteLater()
