from __future__ import annotations

from spektrafilm_gui.grade_recipe import (
    ColorRecipe,
    GradeRecipe,
    HslBand,
    LightRecipe,
    LutRecipe,
)


def test_default_recipe_is_identity() -> None:
    recipe = GradeRecipe()
    assert recipe.is_identity()
    assert recipe.dirty_count() == 0
    assert recipe.lut.path == ''
    assert recipe.lut.strength == 100.0


def test_recipe_roundtrip_preserves_every_field() -> None:
    recipe = GradeRecipe(
        light=LightRecipe(
            exposure=1.25,
            contrast=42.0,
            highlights=-18.0,
            shadows=30.0,
            whites=12.0,
            blacks=-9.0,
            midtones=8.0,
            highlight_rolloff=25.0,
            curve_highlights=4.0,
            curve_lights=-6.0,
            curve_darks=3.0,
            curve_shadows=-2.0,
        ),
        lut=LutRecipe(path='/tmp/example.cube', strength=64.0),
    )
    recipe.color.temperature = 18.0
    recipe.color.tint = -12.0
    recipe.color.vibrance = 20.0
    recipe.color.saturation = -8.0
    recipe.color.hue_shift = 15.0
    recipe.color.color_density = 40.0
    recipe.color.hsl[2] = HslBand(hue=10.0, saturation=-25.0, luminance=15.0)
    recipe.color.grading.shadows.hue = 210.0
    recipe.color.grading.shadows.saturation = 35.0
    recipe.color.grading.highlights.luminance = -10.0
    recipe.transparency.tonal = 60.0
    recipe.transparency.color = 30.0
    recipe.quality.clarity = -20.0
    recipe.quality.texture = 15.0
    recipe.quality.dehaze = 22.0
    recipe.quality.sharpen_amount = 44.0
    recipe.quality.sharpen_radius = 1.8
    recipe.quality.sharpen_threshold = 12.0
    recipe.quality.noise_luminance = 18.0
    recipe.quality.noise_color = 10.0
    recipe.optics.vignette_amount = -35.0
    recipe.optics.vignette_midpoint = 40.0
    recipe.optics.vignette_roundness = 20.0
    recipe.optics.vignette_feather = 70.0
    recipe.optics.grain_amount = 12.0
    recipe.optics.grain_size = 60.0
    recipe.optics.grain_roughness = 30.0
    recipe.optics.chromatic_aberration = 8.0

    restored = GradeRecipe.from_dict(recipe.to_dict())
    assert restored.to_dict() == recipe.to_dict()
    assert not restored.is_identity()
    assert restored.dirty_count() > 0


def test_from_dict_clamps_out_of_range_and_falls_back_on_bad_types() -> None:
    recipe = GradeRecipe.from_dict(
        {
            'light': {'exposure': 99.0, 'contrast': -1_000.0, 'shadows': 'oops'},
            'color': {'temperature': None, 'hsl': [{'hue': 500.0}]},
            'quality': {'sharpen_radius': 0.1},
            'optics': {'vignette_amount': -900.0, 'grain_amount': 'bad'},
            'lut': {'strength': 500.0, 'path': 12345},
            'unknown': {'x': 1},
        },
    )
    assert recipe.light.exposure == 5.0
    assert recipe.light.contrast == -100.0
    assert recipe.light.shadows == 0.0
    assert recipe.color.temperature == 0.0
    assert recipe.color.hsl[0].hue == 100.0
    assert len(recipe.color.hsl) == 8
    assert recipe.quality.sharpen_radius == 0.5
    assert recipe.optics.vignette_amount == -100.0
    assert recipe.optics.grain_amount == 0.0
    assert recipe.lut.strength == 100.0
    assert recipe.lut.path == ''


def test_from_dict_pads_and_truncates_hsl_bands() -> None:
    short = GradeRecipe.from_dict({'color': {'hsl': [{'hue': 5.0}]}})
    assert len(short.color.hsl) == 8
    assert short.color.hsl[0].hue == 5.0
    assert short.color.hsl[7].hue == 0.0

    long = GradeRecipe.from_dict(
        {'color': {'hsl': [{'saturation': 1.0} for _ in range(12)]}},
    )
    assert len(long.color.hsl) == 8


def test_recipe_is_identity_only_when_everything_neutral() -> None:
    recipe = GradeRecipe()
    recipe.color = ColorRecipe(saturation=1.0)
    assert not recipe.is_identity()
    assert recipe.dirty_count() == 1


def test_point_curve_roundtrip_and_identity() -> None:
    recipe = GradeRecipe.from_dict(
        {'light': {'curve': [{'x': 0, 'y': 0}, {'x': 0.5, 'y': 0.6}, {'x': 1, 'y': 1}]}}
    )
    assert recipe.light.curve == ((0.0, 0.0), (0.5, 0.6), (1.0, 1.0))
    assert recipe.to_dict()['light']['curve'] == [
        {'x': 0.0, 'y': 0.0},
        {'x': 0.5, 'y': 0.6},
        {'x': 1.0, 'y': 1.0},
    ]
    assert not recipe.is_identity()
    assert recipe.dirty_count() >= 1


def test_point_curve_accepts_pairs_and_rejects_invalid() -> None:
    pairs = GradeRecipe.from_dict({'light': {'curve': [[0, 0], [1, 1]]}})
    assert pairs.light.curve == ((0.0, 0.0), (1.0, 1.0))

    assert GradeRecipe.from_dict({'light': {'curve': [[0, 0]]}}).light.curve is None
    assert GradeRecipe.from_dict({'light': {'curve': [[0, 0], [2, 1]]}}).light.curve is None
    assert GradeRecipe.from_dict({'light': {'curve': 'nope'}}).light.curve is None