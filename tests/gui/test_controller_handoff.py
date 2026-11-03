from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from qtpy import QtWidgets

from spektrafilm_gui import controller as controller_module
from spektrafilm_gui.controller import GuiController, HANDOFF_MODE_LABEL
from spektrafilm_gui.export_settings import ExportSettings
from spektrafilm_gui.grade_engine import prepare_source
from spektrafilm_gui.state import PROJECT_DEFAULT_GUI_STATE, clone_gui_state
from spektrafilm.utils.io import load_image_oiio

import OpenImageIO as oiio


def _app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class _SyncPool:
    def start(self, worker) -> None:
        worker.run()


def test_start_handoff_writes_16bit_prophoto_linear(tmp_path, monkeypatch) -> None:
    _app()
    controller = GuiController(viewer=object(), widgets=object())
    controller._current_input_image = np.full((6, 8, 3), 0.4, dtype=np.float32)
    controller._thread_pool = _SyncPool()
    params = SimpleNamespace(
        io=SimpleNamespace(output_color_space='sRGB', output_cctf_encoding=True),
        settings=SimpleNamespace(preview_mode=True),
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(controller_module, 'collect_gui_state', lambda *, widgets: object())
    monkeypatch.setattr(controller_module, 'build_params_from_state', lambda state: params)

    def fake_process(image, _params, **_kwargs):
        captured['image'] = image.copy()
        return np.full((6, 8, 3), 0.5, dtype=np.float64)

    monkeypatch.setattr(controller, '_process_image_with_runtime', fake_process)
    monkeypatch.setattr(
        controller,
        '_prepare_output_display_image',
        lambda image, **kwargs: (np.zeros((6, 8, 3), dtype=np.uint8), 'ok'),
    )
    monkeypatch.setattr(controller_module, 'set_status', lambda *args, **kwargs: None)

    results: list[object] = []
    errors: list[object] = []
    target = tmp_path / 'handoff.tif'

    started = controller.start_handoff(
        str(target),
        lambda result, error: (results.append(result), errors.append(error)),
    )

    assert started is True
    assert errors == [None]
    assert results and results[0].mode_label == HANDOFF_MODE_LABEL
    assert params.io.output_color_space == 'sRGB'
    assert params.io.output_cctf_encoding is False
    assert params.settings.preview_mode is False

    data = load_image_oiio(str(target))
    assert data.shape[:2] == (6, 8)
    assert float(data.mean()) == pytest.approx(0.5, abs=1e-4)

    image_input = oiio.ImageInput.open(str(target))
    assert image_input is not None
    spec = image_input.spec()
    image_input.close()
    assert spec.format == oiio.UINT16
    assert spec.getattribute('ICCProfile') is not None


def test_handoff_roundtrips_develop_output_colors(tmp_path, monkeypatch) -> None:
    _app()
    controller = GuiController(viewer=object(), widgets=object())
    controller._current_input_image = np.ones((4, 4, 3), dtype=np.float32)
    controller._thread_pool = _SyncPool()
    params = SimpleNamespace(
        io=SimpleNamespace(output_color_space='sRGB', output_cctf_encoding=True),
        settings=SimpleNamespace(preview_mode=True),
    )
    monkeypatch.setattr(controller_module, 'collect_gui_state', lambda *, widgets: object())
    monkeypatch.setattr(controller_module, 'build_params_from_state', lambda state: params)

    color = np.array((0.80, 0.05, 0.02), dtype=np.float32)

    def fake_process(_image, _params, **_kwargs):
        return np.broadcast_to(color, (4, 4, 3)).copy()

    monkeypatch.setattr(controller, '_process_image_with_runtime', fake_process)
    monkeypatch.setattr(
        controller,
        '_prepare_output_display_image',
        lambda image, **kwargs: (np.zeros((4, 4, 3), dtype=np.uint8), 'ok'),
    )
    monkeypatch.setattr(controller_module, 'set_status', lambda *args, **kwargs: None)

    target = tmp_path / 'handoff.tif'
    results: list[object] = []
    errors: list[object] = []
    assert controller.start_handoff(str(target), lambda result, error: (results.append(result), errors.append(error))) is True
    assert errors == [None]
    assert results

    saved = load_image_oiio(str(target))
    recovered = prepare_source(saved)
    assert np.allclose(recovered[0, 0], color, atol=2e-3)


def test_start_handoff_refuses_while_simulating(monkeypatch) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    controller._current_input_image = np.zeros((4, 4, 3), dtype=np.float32)
    controller._active_simulation_worker = object()
    monkeypatch.setattr(controller_module, 'set_status', lambda *args, **kwargs: None)

    assert controller.start_handoff('/tmp/handoff.tif') is False


def test_export_graded_image_uses_srgb_and_graded_filename(tmp_path, monkeypatch) -> None:
    _app()
    controller = GuiController(viewer=object(), widgets=object())
    controller._current_input_path = str(tmp_path / 'source.png')
    controller._export_settings = ExportSettings(format='JPEG')
    captured: dict[str, object] = {}

    gui_state = clone_gui_state(PROJECT_DEFAULT_GUI_STATE)
    gui_state.simulation.workflow.saving_color_space = 'sRGB'
    gui_state.simulation.workflow.saving_cctf_encoding = True
    monkeypatch.setattr(controller_module, 'collect_gui_state', lambda *, widgets: gui_state)

    def fake_export(settings, *, payload=None, with_frame=True):
        captured['settings'] = settings
        captured['payload'] = payload

    monkeypatch.setattr(controller, '_export_with_settings', fake_export)
    image = np.full((12, 16, 3), 0.5, dtype=np.float32)

    controller.export_graded_image(image)
    settings = captured['settings']
    payload = captured['payload']
    assert settings.filename_template == '{name}_graded'
    assert settings.format == 'JPEG'
    assert payload[1] == 'sRGB'
    assert payload[2] is True
    assert np.array_equal(payload[0], image)

    controller.export_graded_image(image, direct=True)
    direct_settings = captured['settings']
    assert direct_settings.format == 'PNG'
    assert direct_settings.png_compression == 9
    assert direct_settings.long_edge == round(16 * 0.9)


def test_start_handoff_reuses_cached_full_size_scan(tmp_path, monkeypatch) -> None:
    """同一状态下的全尺寸显影结果必须被复用：交接图要与显影台导出逐像素同源。"""
    _app()
    controller = GuiController(viewer=object(), widgets=object())
    linear = np.full((4, 4, 3), 0.4, dtype=np.float32)
    controller._current_input_image = linear
    controller._output_scan_fingerprint = 'fp-current'

    encoded = np.asarray(
        controller_module.colour.RGB_to_RGB(
            linear, 'sRGB', 'sRGB',
            apply_cctf_decoding=False, apply_cctf_encoding=True,
        ),
        dtype=np.float32,
    )
    layer = SimpleNamespace(
        data=np.uint8(np.clip(encoded, 0.0, 1.0) * 255),
        metadata={
            controller_module.OUTPUT_FLOAT_DATA_KEY: encoded,
            controller_module.OUTPUT_COLOR_SPACE_KEY: 'sRGB',
            controller_module.OUTPUT_CCTF_ENCODING_KEY: True,
        },
    )
    monkeypatch.setattr(controller, '_output_layer', lambda: layer)
    monkeypatch.setattr(
        controller,
        '_launch_worker',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('不应重跑显影')),
    )
    params = SimpleNamespace(
        io=SimpleNamespace(output_color_space='sRGB', output_cctf_encoding=True),
        settings=SimpleNamespace(preview_mode=True),
    )
    monkeypatch.setattr(controller_module, 'collect_gui_state', lambda *, widgets: object())
    monkeypatch.setattr(controller_module, 'build_params_from_state', lambda state: params)
    monkeypatch.setattr(controller_module, 'set_status', lambda *args, **kwargs: None)

    results: list[object] = []
    errors: list[object] = []
    target = tmp_path / 'handoff.tif'
    assert controller.start_handoff(
        str(target),
        lambda result, error: (results.append(result), errors.append(error)),
        fingerprint='fp-current',
    ) is True

    assert errors == [None]
    assert results and results[0].mode_label == HANDOFF_MODE_LABEL

    saved = prepare_source(load_image_oiio(str(target)))
    assert np.allclose(saved, linear, atol=2e-3)


def test_start_handoff_recomputes_when_fingerprint_changed(tmp_path, monkeypatch) -> None:
    _app()
    controller = GuiController(viewer=object(), widgets=object())
    controller._current_input_image = np.full((4, 4, 3), 0.4, dtype=np.float32)
    controller._output_scan_fingerprint = 'fp-old'
    params = SimpleNamespace(
        io=SimpleNamespace(output_color_space='sRGB', output_cctf_encoding=True),
        settings=SimpleNamespace(preview_mode=True),
    )
    monkeypatch.setattr(controller_module, 'collect_gui_state', lambda *, widgets: object())
    monkeypatch.setattr(controller_module, 'build_params_from_state', lambda state: params)
    launched: list[object] = []
    monkeypatch.setattr(
        controller,
        '_launch_worker',
        lambda request, *, report_status: launched.append(request),
    )

    assert controller.start_handoff(str(tmp_path / 'handoff.tif'), fingerprint='fp-new') is True
    assert launched and launched[0].mode_label == HANDOFF_MODE_LABEL
    assert params.settings.preview_mode is False
    assert params.io.output_cctf_encoding is False


def test_handoff_failure_notifies_callback_without_dialog(monkeypatch) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    controller._active_simulation_label = HANDOFF_MODE_LABEL
    errors: list[object] = []
    controller._handoff_callback = lambda result, error: errors.append(error)
    monkeypatch.setattr(controller, '_set_simulation_controls_enabled', lambda _enabled: None)
    monkeypatch.setattr(
        controller_module.QMessageBox,
        'critical',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('should not show dialog')),
    )

    controller._on_simulation_failed('boom')

    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)
    assert controller._handoff_callback is None
