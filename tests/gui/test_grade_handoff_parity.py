"""显影台 → 调色台的交接一致性回归。

两条不变量：

1. 交接图（16-bit / ProPhoto / 线性）走中性调色后，与显影台导出的 8-bit sRGB
   逐像素差不超过 1 LSB —— 即「显影台导出的 PNG」和「输入调色台的图像」同源。
2. 调色台导出使用与显影台导出相同的保存色彩空间/编码，不再写死 sRGB。
"""

from __future__ import annotations

import numpy as np
import pytest

from spektrafilm_gui import controller as controller_module
from spektrafilm_gui.controller import GuiController, HANDOFF_COLOR_SPACE
from spektrafilm_gui.grade_engine import load_handoff_image, prepare_source, srgb_encode

from .helpers import make_test_controller_gui_state


pytestmark = pytest.mark.integration


def _synthetic_linear_image() -> np.ndarray:
    """覆盖 0 → 1 的线性 sRGB 图，含暗部与高光边界值。"""
    values = np.array(
        [0.0, 0.002, 0.02, 0.18, 0.5, 0.8, 0.98, 1.0],
        dtype=np.float32,
    )
    image = np.zeros((8, 8, 3), dtype=np.float32)
    image[..., 0] = values[:, None]
    image[..., 1] = values[None, :]
    image[..., 2] = (values[:, None] + values[None, :]) / 2.0
    return image


def _to_srgb_uint8(linear_srgb: np.ndarray) -> np.ndarray:
    """显影台导出链的等价式：编码 → clip → 8-bit。"""
    return np.uint8(np.clip(srgb_encode(linear_srgb), 0.0, 1.0) * 255.0)


def test_neutral_grade_matches_develop_export_bits(tmp_path) -> None:
    linear_srgb = _synthetic_linear_image()
    expected = _to_srgb_uint8(linear_srgb)

    prophoto_linear = np.asarray(
        controller_module.colour.RGB_to_RGB(
            linear_srgb,
            'sRGB',
            HANDOFF_COLOR_SPACE,
            apply_cctf_decoding=False,
            apply_cctf_encoding=False,
        ),
        dtype=np.float32,
    )
    handoff_path = tmp_path / 'handoff.tif'
    controller_module.save_image_oiio(
        str(handoff_path),
        prophoto_linear,
        bit_depth=16,
        color_space=HANDOFF_COLOR_SPACE,
        cctf_encoding=False,
    )

    graded_source = prepare_source(load_handoff_image(handoff_path))
    actual = _to_srgb_uint8(graded_source)

    difference = np.abs(actual.astype(np.int16) - expected.astype(np.int16))
    assert int(difference.max()) <= 1, f'交接图往返偏差过大：max={difference.max()}'
    assert float(difference.mean()) < 0.5


def _stub_controller(monkeypatch, gui_state) -> tuple[GuiController, dict[str, object]]:
    controller = GuiController(viewer=object(), widgets=object())
    captured: dict[str, object] = {}
    monkeypatch.setattr(controller_module, 'collect_gui_state', lambda *, widgets: gui_state)
    monkeypatch.setattr(
        controller,
        '_export_with_settings',
        lambda settings, *, payload=None, with_frame=True: captured.setdefault('payload', payload),
    )
    return controller, captured


def test_graded_export_identity_in_srgb(monkeypatch) -> None:
    gui_state = make_test_controller_gui_state()
    gui_state.simulation.workflow.saving_color_space = 'sRGB'
    gui_state.simulation.workflow.saving_cctf_encoding = True
    controller, captured = _stub_controller(monkeypatch, gui_state)

    def fail_rgb_to_rgb(*args, **kwargs):
        raise AssertionError('sRGB 默认路径不应再做色彩转换')

    monkeypatch.setattr(controller_module.colour, 'RGB_to_RGB', fail_rgb_to_rgb)

    image = np.full((4, 4, 3), 0.25, dtype=np.float32)
    controller.export_graded_image(image)

    data, color_space, cctf_encoding, _metadata = captured['payload']
    assert color_space == 'sRGB'
    assert cctf_encoding is True
    np.testing.assert_allclose(data, image)


def test_graded_export_honours_saving_color_space(monkeypatch) -> None:
    gui_state = make_test_controller_gui_state()
    gui_state.simulation.workflow.saving_color_space = 'Display P3'
    gui_state.simulation.workflow.saving_cctf_encoding = True
    controller, captured = _stub_controller(monkeypatch, gui_state)

    calls: dict[str, object] = {}

    def fake_rgb_to_rgb(image_data, input_color_space, output_color_space, apply_cctf_decoding, apply_cctf_encoding):
        calls['input_space'] = input_color_space
        calls['output_space'] = output_color_space
        calls['decoding'] = apply_cctf_decoding
        calls['encoding'] = apply_cctf_encoding
        return image_data + 0.1

    monkeypatch.setattr(controller_module.colour, 'RGB_to_RGB', fake_rgb_to_rgb)

    image = np.full((4, 4, 3), 0.25, dtype=np.float32)
    controller.export_graded_image(image)

    data, color_space, cctf_encoding, _metadata = captured['payload']
    assert color_space == 'Display P3'
    assert cctf_encoding is True
    assert calls == {
        'input_space': 'sRGB',
        'output_space': 'Display P3',
        'decoding': True,
        'encoding': True,
    }
    np.testing.assert_allclose(data, image + 0.1)
