from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
from qtpy import QtGui, QtTest, QtWidgets

from spektrafilm_gui import editor_page as editor_module
from spektrafilm_gui import inspector_simple as inspector_module
from spektrafilm_gui import library_store as store_module
from spektrafilm_gui import preset_rail as rail_module
from spektrafilm_gui.library_thumbs import ThumbnailService
from spektrafilm_gui.widgets import create_widget_bundle


def _app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class _Controller:
    def __init__(self) -> None:
        self.preview_calls = 0
        self.profile_calls: list[str] = []
        self.export_calls = 0
        self.reset_calls = 0

    def request_auto_preview(self, *_args) -> None:
        self.preview_calls += 1

    def apply_profile_defaults(self, value: str) -> None:
        self.profile_calls.append(value)

    def restore_factory_default(self) -> None:
        self.reset_calls += 1

    def request_export(self) -> None:
        self.export_calls += 1


def _png(path: Path, color: str = '#808080', size: int = 48) -> Path:
    image = QtGui.QImage(size, size, QtGui.QImage.Format_RGB888)
    image.fill(QtGui.QColor(color))
    assert image.save(str(path), 'PNG')
    return path


def test_inspector_basic_rows_write_back_to_source_editors(tmp_path: Path) -> None:
    _app()
    widgets = create_widget_bundle()
    controller = _Controller()
    panel = inspector_module.InspectorPanel(widgets, controller, SimpleNamespace(window=None))
    panel.resize(320, 700)

    brightness = panel.row('print_exposure')
    assert isinstance(brightness, inspector_module.FloatRow)
    brightness.spin.setValue(1.6)
    assert abs(float(widgets.simulation._editors['print_exposure'].value) - 1.6) < 1e-6
    assert controller.preview_calls >= 1

    panel.row('scan_film').toggle.setChecked(True)
    assert widgets.simulation._editors['scan_film'].value is True

    panel.set_mode('professional')
    assert panel._stack.currentIndex() == 1
    panel.set_mode('basic')
    assert panel._stack.currentIndex() == 0

    panel.deleteLater()


def test_inspector_histogram_accepts_rgb_array() -> None:
    _app()
    widgets = create_widget_bundle()
    panel = inspector_module.InspectorPanel(widgets, _Controller(), SimpleNamespace(window=None))
    data = np.zeros((32, 48, 3), dtype=np.uint8)
    data[..., 0] = 120
    panel.set_histogram(data)
    assert panel.histogram._histograms is not None
    panel.deleteLater()


def test_preset_rail_lists_all_films_and_papers(tmp_path: Path) -> None:
    _app()
    rail = rail_module.PresetRail()
    assert len(rail._cards) == 20
    assert '20' in rail._film_tab.text()

    rail._set_tab('paper')
    assert len(rail._cards) == 8
    assert '8' in rail._paper_tab.text()

    rail._set_brand('柯达')
    assert len(rail._cards) >= 1
    assert rail._brand == '柯达'

    rail.deleteLater()


def test_preset_rail_brand_search_and_selection() -> None:
    _app()
    rail = rail_module.PresetRail()
    selected: list[str] = []
    rail.film_selected.connect(selected.append)

    rail._set_brand('富士')
    assert all('fujifilm' in raw for raw in rail._cards)

    rail._search_box.setText('c200')
    assert list(rail._cards) == ['fujifilm_c200']

    rail._on_card_selected('fujifilm_c200')
    assert selected == ['fujifilm_c200']
    assert rail._cards['fujifilm_c200'].property('selected') == 'true'

    rail.set_current('', 'kodak_2383')
    rail._set_tab('paper')
    assert rail._cards['kodak_2383'].property('selected') == 'true'

    rail.deleteLater()


def test_editor_page_wires_top_bar_and_filmstrip(tmp_path: Path) -> None:
    _app()
    store = store_module.LibraryStore(tmp_path / 'library')
    item = store.add_photo(_png(tmp_path / 'a.png'))
    assert item is not None
    store.update_item(item.id, film_stock='kodak_portra_400', print_paper='kodak_supra_endura')
    item = store.item(item.id)
    assert item is not None

    widgets = create_widget_bundle()
    controller = _Controller()
    service = ThumbnailService(store, max_threads=1)
    page = editor_module.EditorPage(
        SimpleNamespace(window=None),
        QtWidgets.QWidget(),
        widgets,
        controller,
        thumbnails=service,
    )
    page.resize(1400, 900)
    page.set_photo(item, [item])
    QtTest.QTest.qWait(100)
    _app().processEvents()

    assert page.top_bar._name.full_text() == 'a.png'
    assert '柯达 Portra 400' in page.top_bar._meta.text()
    assert item.id in page.filmstrip._thumbs
    assert page.preset_rail._current_film == 'kodak_portra_400'

    graded: list[bool] = []
    page.grade_requested.connect(lambda: graded.append(True))
    page.set_grade_ready(True)
    page.top_bar._grade_button.click()
    assert graded == [True]

    page.set_simulation_busy(True)
    assert page.top_bar._grade_button.isEnabled() is False
    assert '显影完成后再调色' in page.top_bar._grade_button.toolTip()
    page.set_simulation_busy(False)
    assert page.top_bar._grade_button.isEnabled() is True

    page.set_grade_recipe(True)
    assert page.top_bar._grade_dot.isHidden() is False
    page.set_grade_recipe(False)
    assert page.top_bar._grade_dot.isHidden() is True

    page.top_bar._favorite.setChecked(True)
    _app().processEvents()

    page.deleteLater()
    service.wait_for_idle(1000)
