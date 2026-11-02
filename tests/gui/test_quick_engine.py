from __future__ import annotations

import json

import pytest

from spektrafilm_gui.quick_controls import AXES, empty_intent, expected_values
from spektrafilm_gui.quick_engine import (
    QuickEngine,
    STATUS_CUSTOM,
    STATUS_NORMAL,
)
from spektrafilm_gui.state import GuiState, PROJECT_DEFAULT_GUI_STATE, clone_gui_state


def _state() -> GuiState:
    return clone_gui_state(PROJECT_DEFAULT_GUI_STATE)


def test_zero_intent_is_identity_for_every_axis() -> None:
    state = _state()
    engine = QuickEngine()
    engine.capture(state)
    assert engine.apply_intents(state) == state


def test_each_axis_writes_only_its_owned_paths() -> None:
    state = _state()
    engine = QuickEngine()
    engine.capture(state)
    for name, axis in AXES.items():
        expected_paths = set(axis.owned)
        other_paths = {
            path
            for other_name, other_axis in AXES.items()
            if other_name != name
            for path in other_axis.owned
        }
        engine.intent = empty_intent()
        engine.intent[name] = 50.0
        result = engine.apply_intents(state)
        for path in other_paths - expected_paths:
            assert _read(result, path) == _read(state, path), f'{name} touched {path}'


def _read(root, path: str):
    value = root
    for part in path.split('.'):
        value = getattr(value, part)
    return value


def test_expected_values_cover_all_axes_at_zero() -> None:
    state = _state()
    engine = QuickEngine()
    engine.capture(state)
    for name, axis in AXES.items():
        values = expected_values(axis, 0.0, engine.baseline[name])
        assert set(values) == set(axis.owned)
        for path, value in values.items():
            assert value == _read(state, path)


def test_axis_mapping_examples() -> None:
    state = _state()
    engine = QuickEngine()
    engine.capture(state)

    assert engine.set_axis(state, 'camera_exposure', 1.0).camera.exposure_compensation_ev == pytest.approx(1.0)
    assert engine.set_axis(state, 'camera_exposure', 1.0).simulation.enlarger.print_exposure_compensation is False
    assert engine.set_axis(state, 'print_brightness', 1.0).simulation.enlarger.print_exposure == pytest.approx(0.5)

    contrast = engine.set_axis(state, 'tonal_contrast', 50.0)
    assert contrast.chemistry.gamma_factor == pytest.approx(1.175)
    assert contrast.chemistry.active is True

    balance = engine.set_axis(state, 'print_balance_y', 50.0)
    assert balance.simulation.enlarger.y_filter_shift == pytest.approx(30.0)

    density = engine.set_axis(state, 'color_density', 50.0)
    assert density.couplers.inhibition_interlayer == pytest.approx(1.25)

    grain = engine.set_axis(state, 'grain_amount', 50.0)
    assert grain.grain.density_min == pytest.approx((0.0435, 0.0435, 0.0435))
    assert grain.grain.uniformity == pytest.approx((0.94, 0.96, 0.94))

    size = engine.set_axis(state, 'grain_size', 50.0)
    assert size.grain.particle_area_um2 == pytest.approx(0.2 * 2 ** 0.45)
    assert size.grain.blur == pytest.approx(0.65 * 1.125)

    halation = engine.set_axis(state, 'halation_amount', 50.0)
    assert halation.halation.halation_amount == pytest.approx(1.6)

    diffusion = engine.set_axis(state, 'diffusion', 50.0)
    assert diffusion.camera_diffusion.active is True
    assert diffusion.camera_diffusion.strength == pytest.approx(1.25)

    sharp = engine.set_axis(state, 'scanner_clarity', 50.0)
    assert sharp.scanner.unsharp_mask == pytest.approx((0.7, 1.25))
    soft = engine.set_axis(state, 'scanner_clarity', -50.0)
    assert soft.scanner.unsharp_mask == pytest.approx((0.7, 0.7))
    assert soft.scanner.lens_blur == pytest.approx(0.3)


def test_extremes_are_clamped() -> None:
    state = _state()
    engine = QuickEngine()
    engine.capture(state)

    grain = engine.set_axis(state, 'grain_amount', -100.0)
    assert grain.grain.active is False

    halation = engine.set_axis(state, 'halation_amount', 100.0)
    assert halation.halation.halation_amount == pytest.approx(2.0)

    blur = engine.set_axis(state, 'scanner_clarity', -100.0)
    assert blur.scanner.lens_blur == pytest.approx(0.6)


def test_camera_exposure_restores_compensation_at_zero() -> None:
    state = _state()
    enabled = clone_gui_state(state)
    enabled.simulation.enlarger.print_exposure_compensation = True
    engine = QuickEngine()
    engine.capture(enabled)

    moved = engine.set_axis(enabled, 'camera_exposure', -1.0)
    assert moved.camera.exposure_compensation_ev == pytest.approx(-1.0)
    assert moved.simulation.enlarger.print_exposure_compensation is False

    returned = engine.set_axis(moved, 'camera_exposure', 0.0)
    assert returned.camera.exposure_compensation_ev == pytest.approx(
        enabled.camera.exposure_compensation_ev
    )
    assert returned.simulation.enlarger.print_exposure_compensation is True


def test_zero_restores_baseline_outside_mapping_clamp() -> None:
    state = _state()
    state.couplers.inhibition_interlayer = 0.0
    state.grain.particle_area_um2 = 1.0
    engine = QuickEngine()
    engine.capture(state)

    for name in ('color_density', 'grain_size'):
        values = expected_values(AXES[name], 0.0, engine.baseline[name])
        for path, value in values.items():
            assert value == _read(state, path)
        assert engine.status(state, name) == STATUS_NORMAL


def test_custom_status_detects_professional_edit() -> None:
    state = _state()
    engine = QuickEngine()
    engine.capture(state)
    assert engine.status(state, 'scanner_clarity') == STATUS_NORMAL

    edited = clone_gui_state(state)
    edited.scanner.unsharp_mask = (0.7, 1.4)
    assert engine.status(edited, 'scanner_clarity') == STATUS_CUSTOM

    engine.intent['scanner_clarity'] = 0.0
    repaired = engine.set_axis(edited, 'scanner_clarity', 0.0)
    assert engine.status(repaired, 'scanner_clarity') == STATUS_NORMAL


def test_native_summary_lists_every_owned_path() -> None:
    state = _state()
    engine = QuickEngine()
    engine.capture(state)
    for name, axis in AXES.items():
        summary = engine.native_summary(state, name)
        assert summary
        for path in axis.owned:
            assert f'{path} =' in summary, f'{name} missing {path}'


def test_persistence_roundtrip() -> None:
    state = _state()
    engine = QuickEngine()
    engine.load(None, state)
    engine.intent['print_brightness'] = 1.5
    engine.intent['color_density'] = -25.0
    raw = json.loads(json.dumps(engine.to_dict()))

    restored = QuickEngine()
    restored.load(raw, state)
    assert restored.intent == engine.intent
    assert restored.baseline['scanner_clarity'] == engine.baseline['scanner_clarity']
    assert restored.status(state, 'print_brightness') == STATUS_CUSTOM


def test_profile_change_rebases_and_keeps_intent() -> None:
    state = _state()
    engine = QuickEngine()
    engine.capture(state)
    engine.intent['print_brightness'] = 1.0

    changed = clone_gui_state(state)
    changed.simulation.selection.film_stock = 'kodak_ektachrome_100'
    changed.simulation.selection.print_paper = 'kodak_supra_endura'
    rebound = engine.rebase(changed)
    assert engine.intent['print_brightness'] == pytest.approx(1.0)
    assert engine.profile == ('kodak_ektachrome_100', 'kodak_supra_endura')
    assert rebound.simulation.enlarger.print_exposure == pytest.approx(0.5)


def test_repeated_profile_switches_do_not_accumulate_intent() -> None:
    checks = {
        'camera_exposure': 1.0,
        'print_brightness': 0.5,
        'tonal_contrast': 1.175,
        'print_balance_y': 30.0,
        'scanner_clarity': (0.7, 1.25),
    }
    for axis, expected in checks.items():
        state = _state()
        engine = QuickEngine()
        engine.capture(state)
        state = engine.set_axis(state, axis, 1.0 if axis in {'camera_exposure', 'print_brightness'} else 50.0)
        for _ in range(5):
            state = engine.rebase(state)
        if axis == 'camera_exposure':
            actual = state.camera.exposure_compensation_ev
        elif axis == 'print_brightness':
            actual = state.simulation.enlarger.print_exposure
        elif axis == 'tonal_contrast':
            actual = state.chemistry.gamma_factor
        elif axis == 'print_balance_y':
            actual = state.simulation.enlarger.y_filter_shift
        else:
            actual = tuple(state.scanner.unsharp_mask)
        assert actual == pytest.approx(expected), axis


def test_rebase_preserves_custom_edit_on_zero_intent_axis() -> None:
    state = _state()
    engine = QuickEngine()
    engine.capture(state)
    edited = clone_gui_state(state)
    edited.scanner.unsharp_mask = (0.7, 1.4)

    rebound = engine.rebase(edited)

    assert rebound.scanner.unsharp_mask == pytest.approx((0.7, 1.4))


def test_restore_baseline_clears_intent() -> None:
    state = _state()
    engine = QuickEngine()
    engine.capture(state)
    engine.intent['tonal_contrast'] = 40.0
    applied = engine.apply_intents(state)
    assert applied.chemistry.gamma_factor != state.chemistry.gamma_factor

    restored = engine.restore_baseline(applied)
    assert restored.chemistry.gamma_factor == pytest.approx(state.chemistry.gamma_factor)
    assert engine.intent['tonal_contrast'] == 0.0
