from __future__ import annotations

import numpy as np
from qtpy import QtWidgets

from spektrafilm_gui import controller as controller_module
from spektrafilm_gui.controller import GuiController
from spektrafilm_gui.state import PROJECT_DEFAULT_GUI_STATE, clone_gui_state


def _app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class _Settings:
    long_edge = 0

    def normalized(self):
        return self


def test_framed_display_follows_provider() -> None:
    _app()
    controller = GuiController(viewer=object(), widgets=object())
    image = np.zeros((8, 12, 3), dtype=np.uint8)

    assert controller._frame_settings() == (False, 'none')
    assert controller._framed_display(image).shape == image.shape

    controller.set_frame_provider(lambda: (True, 'paper_white'))
    framed = controller._framed_display(image)
    assert framed.shape[0] > image.shape[0]
    assert framed.shape[1] > image.shape[1]

    controller.set_frame_provider(lambda: (False, 'paper_white'))
    assert controller._framed_display(image).shape == image.shape


def test_export_composites_the_selected_frame(monkeypatch, tmp_path) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    monkeypatch.setattr(
        controller_module,
        'collect_gui_state',
        lambda **_: clone_gui_state(PROJECT_DEFAULT_GUI_STATE),
    )
    controller.set_frame_provider(lambda: (True, 'polaroid'))
    captured: dict[str, tuple[int, ...]] = {}

    monkeypatch.setattr(controller, '_export_target_path', lambda settings: tmp_path / 'out.png')
    monkeypatch.setattr(
        controller,
        '_save_with_settings',
        lambda filepath, image, settings, *, color_space, cctf_encoding: captured.update(
            shape=tuple(np.asarray(image).shape)
        ),
    )

    payload = (np.zeros((8, 12, 3), dtype=np.uint8), 'sRGB', True, None)
    controller._export_with_settings(_Settings(), payload=payload)

    assert captured['shape'][0] > 8
    assert captured['shape'][1] > 12


def test_export_can_skip_the_frame(monkeypatch, tmp_path) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    monkeypatch.setattr(
        controller_module,
        'collect_gui_state',
        lambda **_: clone_gui_state(PROJECT_DEFAULT_GUI_STATE),
    )
    controller.set_frame_provider(lambda: (True, 'film_135'))
    captured: dict[str, tuple[int, ...]] = {}

    monkeypatch.setattr(controller, '_export_target_path', lambda settings: tmp_path / 'out.png')
    monkeypatch.setattr(
        controller,
        '_save_with_settings',
        lambda filepath, image, settings, *, color_space, cctf_encoding: captured.update(
            shape=tuple(np.asarray(image).shape)
        ),
    )

    payload = (np.zeros((8, 12, 3), dtype=np.uint8), 'sRGB', True, None)
    controller._export_with_settings(_Settings(), payload=payload, with_frame=False)

    assert captured['shape'] == (8, 12, 3)


def test_graded_export_never_includes_the_frame(monkeypatch) -> None:
    _app()
    controller = GuiController(viewer=object(), widgets=object())
    monkeypatch.setattr(
        controller_module,
        'collect_gui_state',
        lambda **_: clone_gui_state(PROJECT_DEFAULT_GUI_STATE),
    )
    controller.set_frame_provider(lambda: (True, 'film_135'))
    captured: dict[str, object] = {}

    def fake_export(settings, *, payload=None, with_frame=True) -> None:
        captured['with_frame'] = with_frame
        captured['shape'] = tuple(np.asarray(payload[0]).shape)

    monkeypatch.setattr(controller, '_export_with_settings', fake_export)
    controller.export_graded_image(np.full((8, 12, 3), 0.4, dtype=np.float32))

    assert captured['with_frame'] is False
    assert captured['shape'] == (8, 12, 3)


def test_apply_frame_state_recomposites_without_rerunning(tmp_path) -> None:
    _app()
    controller = GuiController(viewer=object(), widgets=object())
    controller.set_frame_provider(lambda: (True, 'paper_white'))
    source = np.zeros((6, 8, 3), dtype=np.uint8)
    calls: list[tuple[int, ...]] = []

    class _Layer:
        data = source
        metadata = {controller_module.OUTPUT_DISPLAY_IMAGE_KEY: source}
        visible = True

    controller._output_layer = lambda: _Layer()
    controller._output_layer_float_data = lambda: source
    controller._output_layer_render_settings = lambda **_: ('sRGB', True)
    controller._apply_white_border_layout = lambda: None
    controller._set_or_add_output_layer = (
        lambda image, **kwargs: calls.append(tuple(np.asarray(image).shape))
    )

    controller.apply_frame_state()

    assert calls and calls[0][0] > source.shape[0]
