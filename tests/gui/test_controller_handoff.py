from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from qtpy import QtWidgets

from spektrafilm_gui import controller as controller_module
from spektrafilm_gui.controller import GuiController, HANDOFF_MODE_LABEL
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
    assert params.io.output_color_space == 'ProPhoto RGB'
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


def test_start_handoff_refuses_while_simulating(monkeypatch) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    controller._current_input_image = np.zeros((4, 4, 3), dtype=np.float32)
    controller._active_simulation_worker = object()
    monkeypatch.setattr(controller_module, 'set_status', lambda *args, **kwargs: None)

    assert controller.start_handoff('/tmp/handoff.tif') is False


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
