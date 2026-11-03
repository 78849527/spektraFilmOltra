from __future__ import annotations

import numpy as np

from spektrafilm_gui.film_frame import DEFAULT_FRAME_PRESET, FRAME_PRESETS, apply_frame, preset_by_key


def _image(dtype=np.uint8) -> np.ndarray:
    image = np.zeros((120, 180, 3), dtype=dtype)
    image[...] = 40 if dtype == np.uint8 else 0.15
    return image


def test_none_preset_keeps_original_pixels() -> None:
    image = _image()
    framed = apply_frame(image, 'none')
    assert framed.shape == image.shape
    assert np.array_equal(framed, image)


def test_unknown_preset_falls_back_to_default() -> None:
    assert preset_by_key('not-a-preset').key == DEFAULT_FRAME_PRESET
    assert DEFAULT_FRAME_PRESET == 'paper_white'


def test_paper_white_adds_uniform_margin() -> None:
    image = _image()
    framed = apply_frame(image, 'paper_white', padding=0.05)
    margin = int(round(min(image.shape[:2]) * 0.05))
    assert framed.shape == (120 + margin * 2, 180 + margin * 2, 3)
    # 四角是相纸色，中央仍是原图。
    assert framed[0, 0].tolist() != image[0, 0].tolist()
    assert np.array_equal(framed[margin:margin + 120, margin:margin + 180], image)


def test_frame_preserves_dtype_and_works_for_float() -> None:
    for dtype in (np.uint8, np.uint16, np.float32):
        source = _image(dtype)
        framed = apply_frame(source, 'film_135')
        assert framed.dtype == source.dtype


def test_film_135_draws_sprocket_holes_on_both_edges() -> None:
    framed = apply_frame(_image(), 'film_135')
    margin = int(round(120 * 0.075))
    top_row = framed[:margin]
    bottom_row = framed[framed.shape[0] - margin:]
    assert len(np.unique(top_row.reshape(-1, 3), axis=0)) > 1
    assert len(np.unique(bottom_row.reshape(-1, 3), axis=0)) > 1


def test_polaroid_has_wider_bottom_border() -> None:
    framed = apply_frame(_image(), 'polaroid')
    margin = int(round(120 * 0.04))
    top_border = margin
    bottom_border = framed.shape[0] - margin - 120
    assert bottom_border > top_border


def test_all_presets_are_available_for_the_rail() -> None:
    keys = [preset.key for preset in FRAME_PRESETS]
    assert keys[0] == 'none'
    assert 'paper_white' in keys
    assert len(keys) == len(set(keys)) == 6
