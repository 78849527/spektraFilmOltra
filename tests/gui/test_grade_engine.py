from __future__ import annotations

from pathlib import Path

import numpy as np

from spektrafilm_gui.grade_engine import (
    analyze_tone,
    apply_lut,
    downsample_linear,
    parse_cube,
    prepare_source,
    render,
    srgb_encode,
)
from spektrafilm_gui.grade_recipe import GradeRecipe, HslBand, LightRecipe


def _source(seed: int = 0, shape: tuple[int, int] = (64, 96)) -> np.ndarray:
    rng = np.random.default_rng(seed)
    image = rng.random((*shape, 3)).astype(np.float32) * 0.6
    return prepare_source(image)


def _mean(image: np.ndarray) -> float:
    return float(np.mean(image))


def test_prepare_source_matches_develop_colour_conversion() -> None:
    import colour

    prophoto = np.random.default_rng(10).random((32, 32, 3)).astype(np.float32)
    ours = prepare_source(prophoto)
    reference = np.asarray(
        colour.RGB_to_RGB(
            prophoto,
            'ProPhoto RGB',
            'sRGB',
            apply_cctf_decoding=False,
            apply_cctf_encoding=False,
        ),
        dtype=np.float32,
    )
    assert np.allclose(ours, reference, atol=1e-5)


def test_downsample_linear_resizes_large_images_and_preserves_color() -> None:
    image = np.zeros((1800, 2400, 3), dtype=np.float32)
    image[..., 0] = 0.6
    image[..., 1] = 0.3
    image[..., 2] = 0.1

    result = downsample_linear(image, 1600)

    assert result.shape == (1200, 1600, 3)
    assert result.dtype == np.float32
    assert np.allclose(result[..., 0], 0.6, atol=0.01)
    assert np.allclose(result[..., 1], 0.3, atol=0.01)
    assert np.allclose(result[..., 2], 0.1, atol=0.01)


def test_downsample_linear_keeps_small_images_untouched() -> None:
    image = np.zeros((120, 160, 3), dtype=np.float32)
    result = downsample_linear(image, 1600)
    assert result.shape == image.shape
    assert np.array_equal(result, image)


def test_default_recipe_matches_plain_color_conversion() -> None:
    source = _source()
    rendered, analysis = render(source, GradeRecipe())
    expected = np.clip(srgb_encode(source), 0.0, 1.0)
    assert rendered.dtype == np.float32
    assert np.allclose(rendered, expected, atol=1e-6)
    assert analysis.summary
    assert '黑场' in analysis.summary
    assert '白场' in analysis.summary


def test_exposure_moves_brightness_in_both_directions() -> None:
    source = _source(1)
    base, _ = render(source, GradeRecipe())
    brighter, _ = render(source, GradeRecipe.from_dict({'light': {'exposure': 1.0}}))
    darker, _ = render(source, GradeRecipe.from_dict({'light': {'exposure': -1.0}}))
    assert _mean(brighter) > _mean(base) > _mean(darker)


def test_contrast_and_tone_extremes_stay_finite() -> None:
    source = _source(2)
    for value in (-100.0, 100.0):
        recipe = GradeRecipe.from_dict(
            {
                'light': {
                    'contrast': value,
                    'highlights': value,
                    'shadows': -value,
                    'whites': value,
                    'blacks': -value,
                    'midtones': value,
                    'highlight_rolloff': 100.0,
                    'curve_highlights': value,
                    'curve_lights': value,
                    'curve_darks': value,
                    'curve_shadows': value,
                },
            },
        )
        rendered, _ = render(source, recipe)
        assert np.isfinite(rendered).all()
        assert float(rendered.min()) >= 0.0
        assert float(rendered.max()) <= 1.0


def test_tone_masks_keep_pure_black_and_white_at_the_ends() -> None:
    image = np.zeros((32, 48, 3), dtype=np.float32)
    image[:, 24:] = 1.0
    source = prepare_source(image)
    recipe = GradeRecipe.from_dict(
        {
            'light': {
                'shadows': 100.0,
                'blacks': 100.0,
                'highlights': -100.0,
                'whites': -100.0,
                'midtones': 100.0,
            },
        },
    )
    rendered, _ = render(source, recipe)
    assert float(rendered[:, :24].max()) <= 1e-3
    assert float(rendered[:, 24:].min()) >= 1.0 - 1e-3


def test_saturation_minus_one_hundred_produces_gray() -> None:
    source = _source(3)
    rendered, _ = render(source, GradeRecipe.from_dict({'color': {'saturation': -100.0}}))
    assert np.max(np.abs(rendered[..., 0] - rendered[..., 1])) < 1e-5
    assert np.max(np.abs(rendered[..., 1] - rendered[..., 2])) < 1e-5


def test_hsl_band_and_grading_are_finite() -> None:
    recipe = GradeRecipe()
    recipe.color.hsl[1] = HslBand(hue=40.0, saturation=50.0, luminance=-20.0)
    recipe.color.grading.shadows.hue = 210.0
    recipe.color.grading.shadows.saturation = 60.0
    recipe.color.grading.highlights.hue = 40.0
    recipe.color.grading.highlights.saturation = 25.0
    rendered, _ = render(_source(4), recipe)
    assert rendered.dtype == np.float32
    assert np.isfinite(rendered).all()


def test_tonal_transparency_increases_contrast() -> None:
    source = _source(5)
    base, _ = render(source, GradeRecipe())
    toned, analysis = render(source, GradeRecipe.from_dict({'transparency': {'tonal': 50.0}}))
    assert 0.0 <= analysis.black_point <= analysis.white_point <= 1.0
    base_std = float(base.std())
    toned_std = float(toned.std())
    assert toned_std > base_std


def test_color_transparency_neutralises_yellow_highlights_and_green_shadows() -> None:
    height, width = 48, 64
    image = np.zeros((height, width, 3), dtype=np.float32)
    image[: height // 2] = (0.75, 0.70, 0.35)
    image[height // 2 :] = (0.20, 0.30, 0.18)
    source = prepare_source(image)
    rendered, analysis = render(
        source,
        GradeRecipe.from_dict({'transparency': {'color': 100.0}}),
    )
    top = rendered[: height // 2]
    bottom = rendered[height // 2 :]
    assert top[..., 2].mean() > 0.35
    assert bottom[..., 0].mean() > 0.20
    assert analysis.highlight_cast == '偏黄'
    assert analysis.shadow_cast in {'偏绿', '偏色'}


def test_extreme_quality_and_optics_stay_finite() -> None:
    source = _source(6)
    recipe = GradeRecipe.from_dict(
        {
            'quality': {
                'clarity': 100.0,
                'texture': 100.0,
                'dehaze': 100.0,
                'sharpen_amount': 100.0,
                'sharpen_radius': 3.0,
                'sharpen_threshold': 100.0,
                'noise_luminance': 100.0,
                'noise_color': 100.0,
            },
            'optics': {
                'vignette_amount': -100.0,
                'vignette_midpoint': 100.0,
                'vignette_roundness': 100.0,
                'vignette_feather': 0.0,
                'grain_amount': 100.0,
                'grain_size': 100.0,
                'grain_roughness': 100.0,
                'chromatic_aberration': 100.0,
            },
        },
    )
    rendered, _ = render(source, recipe)
    assert np.isfinite(rendered).all()
    assert rendered.dtype == np.float32


def test_analyze_tone_reports_readable_summary() -> None:
    analysis = analyze_tone(_source(7))
    assert analysis.black_point < analysis.white_point
    assert analysis.highlight_cast
    assert analysis.shadow_cast
    assert '高光' in analysis.summary and '阴影' in analysis.summary


def _write_identity_cube(path: Path, size: int = 2) -> Path:
    lines = ['TITLE "identity"', f'LUT_3D_SIZE {size}', 'DOMAIN_MIN 0 0 0', 'DOMAIN_MAX 1 1 1']
    for blue in range(size):
        for green in range(size):
            for red in range(size):
                lines.append(
                    f'{red / (size - 1):.8f} {green / (size - 1):.8f} {blue / (size - 1):.8f}'
                )
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


def test_parse_cube_and_apply_identity_lut(tmp_path: Path) -> None:
    cube = _write_identity_cube(tmp_path / 'identity.cube')
    lut, domain_min, domain_max = parse_cube(cube)
    assert lut.shape == (2, 2, 2, 3)
    assert np.allclose(domain_min, 0.0)
    assert np.allclose(domain_max, 1.0)

    image = _source(8).clip(0.0, 1.0)
    result = apply_lut(image, str(cube), 100.0)
    assert np.allclose(result, image, atol=0.02)


def test_apply_lut_strength_and_missing_file_are_safe(tmp_path: Path) -> None:
    cube = _write_identity_cube(tmp_path / 'identity.cube')
    image = _source(9).clip(0.0, 1.0)
    half = apply_lut(image, str(cube), 50.0)
    assert np.allclose(half, image, atol=0.02)
    missing = apply_lut(image, str(tmp_path / 'missing.cube'), 100.0)
    assert np.array_equal(missing, image)


def test_point_curve_lifts_midtones_without_tinting() -> None:
    from spektrafilm_gui.grade_engine import _apply_parametric_curve

    image = np.full((16, 16, 3), 0.5, dtype=np.float32)
    light = LightRecipe(curve=((0.0, 0.0), (0.5, 0.7), (1.0, 1.0)))
    out = _apply_parametric_curve(image, light)

    assert float(np.mean(out)) > float(np.mean(image))
    assert np.allclose(out[..., 0], out[..., 1], atol=1e-6)
    assert np.allclose(out[..., 1], out[..., 2], atol=1e-6)


def test_point_curve_identity_returns_input() -> None:
    from spektrafilm_gui.grade_engine import _apply_parametric_curve

    image = np.full((8, 8, 3), 0.4, dtype=np.float32)
    out = _apply_parametric_curve(image, LightRecipe(curve=((0.0, 0.0), (1.0, 1.0))))
    assert np.allclose(out, image)

def test_point_curve_lifts_black_from_zero() -> None:
    from spektrafilm_gui.grade_engine import _apply_parametric_curve

    image = np.zeros((8, 8, 3), dtype=np.float32)
    out = _apply_parametric_curve(image, LightRecipe(curve=((0.0, 0.1), (1.0, 1.0))))
    assert np.allclose(out, 0.1, atol=1e-5)