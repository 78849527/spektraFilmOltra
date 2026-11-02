from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageCms

from spektrafilm_gui import input_color
from spektrafilm_gui.controller import GuiController


def _saved_srgb_jpeg(path) -> None:
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
    Image.new('RGB', (4, 4), (120, 120, 120)).save(
        path,
        'JPEG',
        icc_profile=profile.tobytes(),
    )


def test_detects_srgb_from_embedded_icc(tmp_path) -> None:
    path = tmp_path / 'photo.jpg'
    _saved_srgb_jpeg(path)
    assert input_color.detect_input_color_space(path) == ('sRGB', True)


def test_maps_rec709_icc_to_srgb(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(input_color, '_icc_profile_description', lambda _path: 'Pu-erh Lab Rec.709 Gamma 2.2')
    path = tmp_path / 'reference.jpg'
    path.write_bytes(b'')
    assert input_color.detect_input_color_space(path) == ('sRGB', True)


def test_maps_linear_suffixes_to_aces(monkeypatch, tmp_path) -> None:
    path = tmp_path / 'beauty.exr'
    assert input_color.detect_input_color_space(path) == ('ACES2065-1', False)


def test_maps_raw_suffixes_to_linear_prophoto(tmp_path) -> None:
    path = tmp_path / 'shot.dng'
    assert input_color.detect_input_color_space(path) == ('ProPhoto RGB', False)


def test_falls_back_to_encoded_srgb_without_icc(tmp_path) -> None:
    path = tmp_path / 'plain.png'
    Image.new('RGB', (4, 4), (80, 90, 100)).save(path, 'PNG')
    assert input_color.detect_input_color_space(path) == ('sRGB', True)


class _ValueEditor:
    def __init__(self) -> None:
        self.value = None


def test_load_input_image_applies_detected_color_space(monkeypatch) -> None:
    color_editor = _ValueEditor()
    decode_editor = _ValueEditor()
    widgets = SimpleNamespace(
        input_image=SimpleNamespace(
            _editors={
                'input_color_space': color_editor,
                'input_cctf_decoding': decode_editor,
            },
        ),
    )
    controller = GuiController(viewer=object(), widgets=widgets)
    monkeypatch.setattr(input_color, 'detect_input_color_space', lambda _path: ('Display P3', True))
    monkeypatch.setattr('spektrafilm_gui.controller.detect_input_color_space', lambda _path: ('Display P3', True))
    monkeypatch.setattr('spektrafilm_gui.controller.load_image_oiio', lambda _path: np.zeros((2, 2, 3)))
    monkeypatch.setattr(controller, '_set_or_add_input_stack', lambda _image: None)
    monkeypatch.setattr(controller, '_request_auto_preview_if_enabled', lambda: None)

    controller.load_input_image('photo.jpg')

    assert color_editor.value == 'Display P3'
    assert decode_editor.value is True
