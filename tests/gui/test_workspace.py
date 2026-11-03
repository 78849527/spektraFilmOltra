from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from qtpy import QtGui, QtTest, QtWidgets

from spektrafilm_gui import library_store as store_module
from spektrafilm_gui import workspace as workspace_module
from spektrafilm_gui.state import PROJECT_DEFAULT_GUI_STATE
from spektrafilm_gui.widgets import create_widget_bundle
from spektrafilm.utils.io import save_image_oiio


def _app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _png(path: Path, color: str = '#808080', size: int = 48) -> Path:
    image = QtGui.QImage(size, size, QtGui.QImage.Format_RGB888)
    image.fill(QtGui.QColor(color))
    assert image.save(str(path), 'PNG')
    return path


class _FakeQtWindow:
    def __init__(self, central: QtWidgets.QWidget) -> None:
        self._central = central

    def takeCentralWidget(self):  # noqa: N802 - Qt API name
        return self._central

    def menuBar(self):  # noqa: N802 - Qt API name
        return None


class _FakeController:
    def __init__(self) -> None:
        self.simulating = False
        self.callbacks = []
        self.loaded: list[str] = []
        self.loaded_input: list[str] = []
        self.loaded_raw: list[str] = []
        self.export_calls = 0
        self.direct_export_calls = 0
        self.handoff_calls: list[str] = []
        self.graded_export_calls: list[tuple[tuple[int, ...], bool]] = []
        self.preview_calls = 0
        self.profile_calls: list[str] = []
        self.restore_calls = 0

    def add_simulation_finished_callback(self, callback) -> None:
        self.callbacks.append(callback)

    def is_simulating(self) -> bool:
        return self.simulating

    def load_input_image(self, path: str) -> None:
        self.loaded.append(path)
        self.loaded_input.append(path)
        self._current_input_path = path

    def load_raw_image(self, path: str) -> None:
        self.loaded.append(path)
        self.loaded_raw.append(path)
        self._current_input_path = path

    def current_input_size(self):
        return (1200, 800)

    def request_auto_preview(self, *_args) -> None:
        self.preview_calls += 1

    def apply_profile_defaults(self, value: str) -> None:
        self.profile_calls.append(value)

    def restore_factory_default(self) -> None:
        self.restore_calls += 1

    def request_export(self) -> None:
        self.export_calls += 1

    def request_direct_export(self) -> None:
        self.direct_export_calls += 1

    def current_output_display_image(self):
        return np.zeros((6, 8, 3), dtype=np.uint8)

    def start_handoff(self, path: str, callback=None, *, fingerprint: str | None = None) -> bool:
        self.handoff_calls.append(path)
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        image = np.full((12, 9, 3), 0.4, dtype=np.float32)
        save_image_oiio(
            str(target),
            image,
            bit_depth=16,
            color_space='ProPhoto RGB',
            cctf_encoding=False,
        )
        if callback is not None:
            callback(SimpleNamespace(float_image=image), None)
        return True

    def export_graded_image(self, image, *, direct: bool = False) -> None:
        self.graded_export_calls.append((tuple(np.asarray(image).shape), bool(direct)))

    def save_output_layer(self) -> None:
        return

    def run_preview(self) -> None:
        return

    def run_scan(self) -> None:
        return

    def rotate_input_image_clockwise(self) -> None:
        return

    def rotate_input_image_counterclockwise(self) -> None:
        return


def _window(tmp_path: Path) -> tuple[workspace_module.WorkspaceWindow, store_module.LibraryStore, _FakeController]:
    _app()
    store = store_module.LibraryStore(tmp_path / 'library')
    item = store.add_photo(_png(tmp_path / 'a.png'))
    assert item is not None
    widgets = create_widget_bundle()
    controller = _FakeController()
    viewer = SimpleNamespace(
        window=SimpleNamespace(
            _qt_window=_FakeQtWindow(QtWidgets.QWidget()),
            _qt_viewer=None,
        ),
        layers=None,
        camera=None,
        reset_view=lambda: None,
    )
    window = workspace_module.WorkspaceWindow(
        viewer=viewer,
        widgets=widgets,
        controller=controller,
        store=store,
    )
    window.resize(1400, 900)
    window.show()
    QtTest.QTest.qWait(200)
    _app().processEvents()
    return window, store, controller


def test_workspace_starts_on_library_and_opens_editor(tmp_path: Path) -> None:
    window, store, controller = _window(tmp_path)
    item = store.all_items()[0]

    assert window._stack.currentIndex() == 0
    window._widgets.display.preview_max_size.value = 640
    window.open_item(item.id)
    _app().processEvents()

    assert window._stack.currentIndex() == 1
    assert controller.loaded == [item.path]
    assert window.editor_page.top_bar._name.full_text() == 'a.png'
    assert window._widgets.display.preview_max_size.value == 640
    saved = store.item(item.id)
    assert saved is not None and saved.adjusted is False

    window.close()


def test_workspace_repairs_stale_raw_flag_for_png(tmp_path: Path) -> None:
    window, store, controller = _window(tmp_path)
    item = store.all_items()[0]
    store.update_item(item.id, is_raw=True)

    window.open_item(item.id)
    _app().processEvents()

    assert controller.loaded_raw == []
    assert controller.loaded_input == [item.path]
    repaired = store.item(item.id)
    assert repaired is not None and repaired.is_raw is False

    window.close()


def test_workspace_remembers_per_photo_adjustments(tmp_path: Path) -> None:
    window, store, controller = _window(tmp_path)
    item = store.all_items()[0]
    window.open_item(item.id)
    _app().processEvents()

    window._widgets.simulation._editors['print_exposure'].value = 2.0
    window._persist_active_state()
    saved = store.item(item.id)
    assert saved is not None and saved.state is not None
    assert saved.adjusted is True

    window.show_library()
    _app().processEvents()
    assert window._stack.currentIndex() == 0

    window.open_item(item.id)
    _app().processEvents()
    assert abs(float(window._widgets.simulation._editors['print_exposure'].value) - 2.0) < 1e-6

    window.close()


def test_workspace_persists_quick_intent(tmp_path: Path) -> None:
    window, store, _controller = _window(tmp_path)
    item = store.all_items()[0]
    window.open_item(item.id)
    _app().processEvents()

    deck = window.editor_page.inspector
    deck._mode_tabs.set_current(0)
    row = deck._quick_panel.row('camera_exposure')
    row.set_value(1.0)
    row._commit()
    window._persist_active_state()

    saved = store.item(item.id)
    assert saved is not None and saved.state is not None
    assert saved.state['quick']['intent']['camera_exposure'] == pytest.approx(1.0)

    window.show_library()
    _app().processEvents()
    window.open_item(item.id)
    _app().processEvents()
    assert deck._quick_panel.row('camera_exposure').value() == pytest.approx(1.0)
    assert window._widgets.camera.exposure_compensation_ev.value == pytest.approx(1.0)

    window.close()


def test_workspace_direct_export_and_favorite(tmp_path: Path) -> None:
    window, store, controller = _window(tmp_path)
    item = store.all_items()[0]
    window.open_item(item.id)
    _app().processEvents()

    menu = window.editor_page.top_bar._export_menu.menu()
    menu.actions()[0].trigger()
    assert controller.direct_export_calls == 1

    window.editor_page.top_bar._favorite.setChecked(True)
    _app().processEvents()
    assert store.item(item.id).favorite is True

    window._on_film_selected('kodak_portra_400')
    assert window._widgets.simulation.film_stock.value == 'kodak_portra_400'
    assert controller.profile_calls == ['kodak_portra_400']

    window.close()


def test_workspace_generates_handoff_and_enters_grade_page(tmp_path: Path, monkeypatch) -> None:
    handoff_root = tmp_path / 'projects'
    monkeypatch.setattr(
        workspace_module,
        'handoff_path',
        lambda item_id: handoff_root / item_id / 'handoff.tif',
    )
    window, store, controller = _window(tmp_path)
    item = store.all_items()[0]
    window.open_item(item.id)
    _app().processEvents()

    window._on_grade_requested()
    _app().processEvents()

    assert window._stack.currentIndex() == 2
    assert controller.handoff_calls == [str(handoff_root / item.id / 'handoff.tif')]
    saved = store.item(item.id)
    assert saved is not None and saved.state is not None
    handoff = saved.state['grade']['handoff']
    assert handoff['format'] == 'tiff16-prophoto-linear'
    assert handoff['width'] == 9
    assert handoff['height'] == 12

    window.grade_page.back_requested.emit()
    _app().processEvents()
    assert window._stack.currentIndex() == 1

    window.close()


def test_workspace_persists_grade_recipe_and_exports(tmp_path: Path, monkeypatch) -> None:
    handoff_root = tmp_path / 'projects'
    monkeypatch.setattr(
        workspace_module,
        'handoff_path',
        lambda item_id: handoff_root / item_id / 'handoff.tif',
    )
    window, store, controller = _window(tmp_path)
    item = store.all_items()[0]
    window.open_item(item.id)
    _app().processEvents()
    window._on_grade_requested()
    _app().processEvents()
    assert window._stack.currentIndex() == 2

    row = window.grade_page.deck._rows[('light', 'exposure')]
    row.set_value_silent(1.0)
    row.valueChanged.emit(1.0)
    window._flush_grade_recipe()

    saved = store.item(item.id)
    assert saved is not None and saved.state is not None
    recipe = saved.state['grade']['recipe']
    assert recipe['light']['exposure'] == pytest.approx(1.0)

    window.show_editor()
    _app().processEvents()
    assert window._stack.currentIndex() == 1

    window._on_grade_requested()
    _app().processEvents()
    assert window._stack.currentIndex() == 2
    assert window.grade_page.recipe().light.exposure == pytest.approx(1.0)

    window.grade_page.grade_image_ready.emit(np.zeros((12, 9, 3), dtype=np.float32), True)
    assert controller.graded_export_calls == [((12, 9, 3), True)]

    window.close()


def test_workspace_keeps_grade_page_when_handoff_is_corrupt(tmp_path: Path) -> None:
    window, store, _controller = _window(tmp_path)
    item = store.all_items()[0]
    broken = tmp_path / 'broken.tif'
    broken.write_bytes(b'not a tiff')
    updated = store.update_item(
        item.id,
        state={
            'grade': {
                'schema': 1,
                'handoff': {'path': str(broken), 'format': 'tiff16-prophoto-linear'},
            },
        },
    )
    assert updated is not None

    window._open_grade_page(updated)
    _app().processEvents()

    assert window._stack.currentIndex() == 2
    assert '读取失败' in window.grade_page.canvas._message

    window.close()


def test_workspace_blocks_switching_while_simulating(tmp_path: Path) -> None:
    window, store, controller = _window(tmp_path)
    item = store.all_items()[0]
    window.open_item(item.id)
    _app().processEvents()

    controller.simulating = True
    window.show_library()
    _app().processEvents()
    assert window._stack.currentIndex() == 1
    controller.simulating = False

    window.close()


def test_workspace_persists_and_restores_frame_state(tmp_path: Path) -> None:
    window, store, controller = _window(tmp_path)
    item = store.all_items()[0]
    window.open_item(item.id)
    _app().processEvents()

    window.editor_page.set_frame_state({'enabled': False, 'preset': 'film_135'})
    window._on_frame_changed()
    window._persist_active_state()

    saved = store.item(item.id)
    assert saved is not None
    assert saved.state['frame'] == {'enabled': False, 'preset': 'film_135'}

    window.show_library()
    window.editor_page.set_frame_state(None)
    window.open_item(item.id)
    _app().processEvents()

    assert window.editor_page.frame_state_dict() == {'enabled': False, 'preset': 'film_135'}
    window.close()


def test_reset_restores_photo_defaults_without_touching_global_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(workspace_module, 'load_default_gui_state', lambda: PROJECT_DEFAULT_GUI_STATE)
    window, store, controller = _window(tmp_path)
    item = store.all_items()[0]
    window.open_item(item.id)
    _app().processEvents()

    window._widgets.simulation._editors['print_exposure'].value = 2.0
    window._on_reset()

    default_value = PROJECT_DEFAULT_GUI_STATE.simulation.enlarger.print_exposure
    assert abs(float(window._widgets.simulation._editors['print_exposure'].value) - default_value) < 1e-6
    assert controller.restore_calls == 0

    window.close()
