from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from qtpy import QtWidgets

from spektrafilm_gui import app_paths
from spektrafilm_gui.grade_page import GradePage, RecipeSliderRow
from spektrafilm_gui.grade_presets import BUILTIN_PRESETS
from spektrafilm_gui.grade_recipe import GradeRecipe
from spektrafilm_gui.grade_worker import GradeRenderTask
from spektrafilm_gui.library_store import LibraryItem
from spektrafilm.utils.io import save_image_oiio


def _app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _wait(app: QtWidgets.QApplication, predicate, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _handoff(path: Path) -> Path:
    rng = np.random.default_rng(0)
    image = (rng.random((120, 160, 3)) * 0.7).astype(np.float32)
    save_image_oiio(
        str(path),
        image,
        bit_depth=16,
        color_space='ProPhoto RGB',
        cctf_encoding=False,
    )
    return path


def _item(width: int = 160, height: int = 120) -> LibraryItem:
    return LibraryItem(
        id='photo',
        path='/tmp/photo.png',
        name='photo.png',
        width=width,
        height=height,
    )


def test_page_builds_and_edits_recipe(tmp_path: Path) -> None:
    _app()
    page = GradePage(preset_path=tmp_path / 'presets.json')
    page.resize(1400, 900)

    row = page.deck._rows[('light', 'exposure')]
    row.set_value_silent(1.25)
    row.valueChanged.emit(1.25)
    assert page.recipe().light.exposure == 1.25
    assert page.deck._badge.text() == '1'

    page.deck._tabs.set_current(1)
    assert page.deck._stack.currentIndex() == 1

    page.deck._band_group.button(1).click()
    band_row = page.deck._band_rows[0]
    band_row.set_value_silent(40.0)
    band_row.valueChanged.emit(40.0)
    assert page.recipe().color.hsl[1].hue == 40.0

    page.deck._zone_tabs.set_current(2)
    zone_row = page.deck._zone_rows[1]
    zone_row.set_value_silent(30.0)
    zone_row.valueChanged.emit(30.0)
    assert page.recipe().color.grading.highlights.saturation == 30.0

    page.deck.reset()
    assert page.recipe().is_identity()
    page.deleteLater()


def test_color_grading_zone_defaults_are_neutral(tmp_path: Path) -> None:
    _app()
    page = GradePage(preset_path=tmp_path / 'presets.json')
    page.deck._zone_tabs.set_current(0)
    assert [row.value() for row in page.deck._zone_rows] == [0.0, 0.0, 0.0]
    page.deck._zone_tabs.set_current(2)
    assert [row.value() for row in page.deck._zone_rows] == [0.0, 0.0, 0.0]
    assert page.recipe().is_identity()
    page.deleteLater()


def test_compare_toggle_switches_canvas_to_original(tmp_path: Path) -> None:
    _app()
    page = GradePage(preset_path=tmp_path / 'presets.json')
    page.canvas.set_image(np.zeros((12, 16, 3), dtype=np.float32))
    page.canvas.set_original(np.ones((12, 16, 3), dtype=np.float32))
    page.top_bar._compare.click()
    assert page.canvas._compare is True
    page.top_bar._compare.click()
    assert page.canvas._compare is False

    page.top_bar._compare.click()
    assert page.load(_item(), None, GradeRecipe()) is False
    assert page.canvas._compare is False
    page.deleteLater()


def test_busy_state_disables_export_controls(tmp_path: Path) -> None:
    _app()
    page = GradePage(preset_path=tmp_path / 'presets.json')
    page._preview_busy = True
    page._sync_busy()
    assert page.top_bar._export.isEnabled() is False
    assert page.top_bar._arrow.isEnabled() is False
    page._preview_busy = False
    page._sync_busy()
    assert page.top_bar._export.isEnabled() is True
    assert page.top_bar._arrow.isEnabled() is True
    page.deleteLater()


def test_reset_syncs_lut_list_selection(tmp_path: Path, monkeypatch) -> None:
    _app()
    app_dir = tmp_path / 'app'
    monkeypatch.setattr(app_paths, 'app_data_dir', lambda: app_dir)
    cube = app_dir / 'luts' / 'identity.cube'
    cube.parent.mkdir(parents=True)
    cube.write_text(
        'LUT_3D_SIZE 2\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n'
        '0 0 0\n1 0 0\n0 1 0\n1 1 0\n0 0 1\n1 0 1\n0 1 1\n1 1 1\n',
        encoding='utf-8',
    )
    page = GradePage(preset_path=tmp_path / 'presets.json')
    page.rail.lut_page.refresh(str(cube))
    page.rail.lut_page._on_selection()
    assert page.recipe().lut.path == str(cube)

    page.deck.reset()
    assert page.recipe().lut.path == ''
    assert page.rail.lut_page._list.currentRow() == 0
    page.deleteLater()


def test_recipe_slider_double_click_resets_default() -> None:
    _app()
    row = RecipeSliderRow('曝光', minimum=-5.0, maximum=5.0, step=0.01, decimals=2)
    row.set_value_silent(2.0)
    events = SimpleNamespace(accept=lambda: None)
    row._reset(events)
    assert row.value() == 0.0


def test_preset_selection_applies_recipe(tmp_path: Path) -> None:
    _app()
    page = GradePage(preset_path=tmp_path / 'presets.json')
    page._on_preset_selected(BUILTIN_PRESETS[1])
    assert page.preset_id() == 'builtin:clean'
    assert page.recipe().transparency.tonal == 18.0
    assert page.recipe().quality.clarity == 8.0
    page.deleteLater()


def test_missing_or_corrupt_handoff_keeps_page_alive(tmp_path: Path) -> None:
    _app()
    page = GradePage(preset_path=tmp_path / 'presets.json')
    bad = tmp_path / 'handoff.tif'
    bad.write_bytes(b'not a tiff')
    loaded = page.load(_item(), bad, GradeRecipe())
    assert loaded is False
    assert '读取失败' in page.canvas._message
    page.deleteLater()


def test_real_handoff_loads_preview_and_exports(tmp_path: Path) -> None:
    app = _app()
    page = GradePage(preset_path=tmp_path / 'presets.json')
    page.resize(1400, 900)
    handoff = _handoff(tmp_path / 'handoff.tif')

    assert page.load(_item(), handoff, GradeRecipe()) is True
    assert _wait(app, lambda: not page.canvas._pixmap.isNull())
    assert page.deck.histogram._histograms is not None
    assert '黑场' in page.deck._analysis_label.text()

    results: list[tuple[np.ndarray, bool]] = []
    requests: list[bool] = []
    page.grade_image_ready.connect(lambda image, direct: results.append((image, direct)))
    page.export_requested.connect(requests.append)
    page._begin_export(True)
    assert requests == [True]
    assert _wait(app, lambda: results, timeout=8.0)
    image, direct = results[0]
    assert direct is True
    assert image.shape[2] == 3
    assert image.dtype == np.float32
    assert np.isfinite(image).all()
    page.deleteLater()


def test_recipe_changes_debounce_into_one_preview(tmp_path: Path) -> None:
    app = _app()
    page = GradePage(preset_path=tmp_path / 'presets.json')
    handoff = _handoff(tmp_path / 'handoff.tif')
    assert page.load(_item(), handoff, GradeRecipe()) is True
    assert _wait(app, lambda: not page.canvas._pixmap.isNull() and not page._preview_busy)

    before = page._generation
    page.deck._rows[('light', 'exposure')].valueChanged.emit(0.5)
    page.deck._rows[('light', 'contrast')].valueChanged.emit(20.0)
    assert page._preview_timer.isActive()
    assert _wait(
        app,
        lambda: page._generation == before + 1 and not page._preview_busy,
        timeout=3.0,
    )
    assert page._generation == before + 1
    page.deleteLater()


def test_render_task_emits_result() -> None:
    _app()
    source = np.full((16, 24, 3), 0.4, dtype=np.float32)
    task = GradeRenderTask(7, source, GradeRecipe())
    results = []
    failures = []
    task.signals.finished.connect(lambda generation, image, analysis: results.append((generation, image, analysis)))
    task.signals.failed.connect(lambda generation, message: failures.append((generation, message)))
    task.run()
    assert failures == []
    assert len(results) == 1
    generation, image, analysis = results[0]
    assert generation == 7
    assert image.dtype == np.float32
    assert analysis.summary


def test_lut_selection_updates_recipe(tmp_path: Path, monkeypatch) -> None:
    _app()
    app_dir = tmp_path / 'app'
    monkeypatch.setattr(app_paths, 'app_data_dir', lambda: app_dir)
    cube = app_dir / 'luts' / 'identity.cube'
    cube.parent.mkdir(parents=True)
    cube.write_text(
        'LUT_3D_SIZE 2\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n'
        '0 0 0\n1 0 0\n0 1 0\n1 1 0\n0 0 1\n1 0 1\n0 1 1\n1 1 1\n',
        encoding='utf-8',
    )
    page = GradePage(preset_path=tmp_path / 'presets.json')
    page.rail.lut_page.refresh(str(cube))
    assert page.rail.lut_page._list.currentRow() == 1
    page.rail.lut_page._on_selection()
    assert page.recipe().lut.path == str(cube)
    page.deleteLater()
