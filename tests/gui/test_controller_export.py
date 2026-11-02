from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from qtpy import QtWidgets

from spektrafilm_gui import controller as controller_module
from spektrafilm_gui.controller import GuiController


def _app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class _Layer:
    def __init__(self, data):
        self.data = data
        self.metadata = {}


def _result(mode_label: str = 'Scan') -> SimpleNamespace:
    return SimpleNamespace(
        display_image=np.zeros((4, 4, 3), dtype=np.uint8),
        float_image=np.zeros((4, 4, 3), dtype=np.float32),
        output_color_space='sRGB',
        use_display_transform=False,
        mode_label=mode_label,
        status_message='ok',
    )


def test_current_input_size_and_output_image(monkeypatch) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    controller._current_input_image = np.zeros((8, 12, 3), dtype=np.float32)
    assert controller.current_input_size() == (12, 8)

    controller._output_layer = lambda: _Layer(np.full((4, 5, 3), 7, dtype=np.uint8))
    image = controller.current_output_display_image()
    assert image is not None and image.shape == (4, 5, 3)


def test_request_export_runs_scan_and_flags(monkeypatch) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    calls: list[str] = []

    def fake_scan() -> None:
        calls.append('scan')
        controller._active_simulation_worker = object()

    monkeypatch.setattr(controller, 'run_scan', fake_scan)

    controller.request_export()

    assert calls == ['scan']
    assert controller._export_after_scan is True


def test_request_export_clears_flag_when_scan_cannot_start(monkeypatch) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    monkeypatch.setattr(controller, 'run_scan', lambda: None)

    controller.request_export()

    assert controller._export_after_scan is False


def test_finished_callback_and_export_save(monkeypatch) -> None:
    app = _app()
    controller = GuiController(viewer=object(), widgets=object())
    received: list[object] = []
    saved: list[bool] = []
    controller.add_simulation_finished_callback(received.append)
    monkeypatch.setattr(controller, '_set_or_add_output_layer', lambda *args, **kwargs: None)
    monkeypatch.setattr(controller, '_set_simulation_controls_enabled', lambda _enabled: None)
    monkeypatch.setattr(controller, '_replay_pending_auto_preview', lambda: None)
    monkeypatch.setattr(controller_module, 'set_status', lambda *args, **kwargs: None)
    monkeypatch.setattr(controller, 'export_now', lambda: saved.append(True))
    controller._export_after_scan = True

    result = _result('Scan')
    controller._on_simulation_finished(result)
    app.processEvents()

    assert received == [result]
    assert saved == [True]
    assert controller._export_after_scan is False


def test_preview_does_not_trigger_export(monkeypatch) -> None:
    app = _app()
    controller = GuiController(viewer=object(), widgets=object())
    saved: list[bool] = []
    monkeypatch.setattr(controller, '_set_or_add_output_layer', lambda *args, **kwargs: None)
    monkeypatch.setattr(controller, '_set_simulation_controls_enabled', lambda _enabled: None)
    monkeypatch.setattr(controller, '_replay_pending_auto_preview', lambda: None)
    monkeypatch.setattr(controller_module, 'set_status', lambda *args, **kwargs: None)
    monkeypatch.setattr(controller, 'export_now', lambda: saved.append(True))
    controller._export_after_scan = True

    controller._on_simulation_finished(_result('Preview'))
    app.processEvents()

    assert saved == []
    assert controller._export_after_scan is True


def test_failure_resets_export_flag(monkeypatch) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    monkeypatch.setattr(controller, '_set_simulation_controls_enabled', lambda _enabled: None)
    monkeypatch.setattr(controller, '_replay_pending_auto_preview', lambda: None)
    monkeypatch.setattr(controller_module, 'set_status', lambda *args, **kwargs: None)
    monkeypatch.setattr(controller_module.QMessageBox, 'critical', lambda *args, **kwargs: None)
    controller._export_after_scan = True

    controller._on_simulation_failed('boom')

    assert controller._export_after_scan is False


def test_request_export_queues_when_simulation_active(monkeypatch) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    controller._active_simulation_worker = object()
    monkeypatch.setattr(controller_module, 'set_status', lambda *args, **kwargs: None)

    controller.request_export()

    assert controller._export_pending_after_simulation is True
    assert controller._export_after_scan is False


def test_pending_export_exports_after_full_size_preview(monkeypatch) -> None:
    app = _app()
    controller = GuiController(viewer=object(), widgets=object())
    controller._current_input_image = np.zeros((4, 4, 3), dtype=np.float32)
    controller._export_pending_after_simulation = True
    saved: list[bool] = []

    monkeypatch.setattr(controller, '_set_or_add_output_layer', lambda *args, **kwargs: None)
    monkeypatch.setattr(controller, '_set_simulation_controls_enabled', lambda _enabled: None)
    monkeypatch.setattr(controller, '_replay_pending_auto_preview', lambda: None)
    monkeypatch.setattr(controller_module, 'set_status', lambda *args, **kwargs: None)
    monkeypatch.setattr(controller, 'export_now', lambda: saved.append(True))

    controller._on_simulation_finished(_result('Preview'))
    app.processEvents()

    assert saved == [True]
    assert controller._export_pending_after_simulation is False


def test_pending_export_scans_when_preview_is_partial(monkeypatch) -> None:
    app = _app()
    controller = GuiController(viewer=object(), widgets=object())
    controller._current_input_image = np.zeros((4, 4, 3), dtype=np.float32)
    controller._export_pending_after_simulation = True
    scans: list[bool] = []

    monkeypatch.setattr(controller, '_set_or_add_output_layer', lambda *args, **kwargs: None)
    monkeypatch.setattr(controller, '_set_simulation_controls_enabled', lambda _enabled: None)
    monkeypatch.setattr(controller, '_replay_pending_auto_preview', lambda: None)
    monkeypatch.setattr(controller_module, 'set_status', lambda *args, **kwargs: None)

    def fake_scan() -> None:
        scans.append(True)
        controller._export_after_scan = True

    monkeypatch.setattr(controller, '_start_export_scan', fake_scan)

    result = _result('Preview')
    result.display_image = np.zeros((2, 2, 3), dtype=np.uint8)
    controller._on_simulation_finished(result)
    app.processEvents()

    assert scans == [True]
    assert controller._export_after_scan is True
