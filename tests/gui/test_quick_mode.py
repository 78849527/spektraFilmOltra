from __future__ import annotations

import pytest
from qtpy import QtWidgets

from spektrafilm_gui.controller import GuiController
from spektrafilm_gui.parameter_deck import ParameterDeck
from spektrafilm_gui.quick_mode import QuickParams, apply_quick_control, quick_from_state
from spektrafilm_gui.state import PROJECT_DEFAULT_GUI_STATE
from spektrafilm_gui.state_bridge import apply_gui_state, collect_gui_state
from spektrafilm_gui.widgets import create_widget_bundle


@pytest.fixture()
def quick_bundle():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    widgets = create_widget_bundle()
    apply_gui_state(PROJECT_DEFAULT_GUI_STATE, widgets=widgets)
    controller = GuiController(viewer=object(), widgets=widgets)
    deck = ParameterDeck(widgets, controller)
    deck._mode_tabs.set_current(0)
    return app, widgets, controller, deck


def _set_quick(deck, name: str, value: float) -> None:
    row = deck._quick_rows[name]
    row.set_value(value)
    row._commit()


def test_quick_mode_has_all_controls(quick_bundle) -> None:
    _app, _widgets, _controller, deck = quick_bundle
    assert set(deck._quick_rows) == {
        'exposure', 'contrast', 'shadows', 'highlights', 'highlight_rolloff',
        'whites', 'blacks', 'saturation', 'temperature', 'tint', 'vibrance',
        'sharpening', 'clarity', 'grain', 'grain_size',
    }
    assert deck._mode == 'quick'


def test_quick_exposure_maps_and_clamps(quick_bundle) -> None:
    _app, widgets, _controller, deck = quick_bundle
    _set_quick(deck, 'exposure', 1.0)
    state = collect_gui_state(widgets=widgets)
    assert state.simulation.enlarger.print_exposure == pytest.approx(0.5)

    _set_quick(deck, 'exposure', 2.0)
    state = collect_gui_state(widgets=widgets)
    assert state.simulation.enlarger.print_exposure == pytest.approx(0.25)

    _set_quick(deck, 'exposure', -2.0)
    state = collect_gui_state(widgets=widgets)
    assert state.simulation.enlarger.print_exposure == pytest.approx(4.0)


def test_quick_contrast_touches_only_its_fields(quick_bundle) -> None:
    _app, widgets, _controller, deck = quick_bundle
    before = collect_gui_state(widgets=widgets)
    before_exposure = before.simulation.enlarger.print_exposure
    _set_quick(deck, 'contrast', 50.0)
    after = collect_gui_state(widgets=widgets)
    assert after.simulation.enlarger.print_exposure == before_exposure
    assert after.chemistry.gamma_factor == pytest.approx(1.13)
    assert after.special.film_render.density_curve_gamma == pytest.approx(1.15)


def test_quick_whites_and_blacks_are_safe(quick_bundle) -> None:
    _app, widgets, _controller, deck = quick_bundle
    _set_quick(deck, 'whites', -100.0)
    state = collect_gui_state(widgets=widgets)
    assert state.scanner.white_correction is True
    assert state.scanner.white_level == pytest.approx(0.75)

    _set_quick(deck, 'blacks', 100.0)
    state = collect_gui_state(widgets=widgets)
    assert state.scanner.black_correction is True
    assert state.scanner.black_level == pytest.approx(0.06)

    _set_quick(deck, 'whites', 0.0)
    state = collect_gui_state(widgets=widgets)
    assert state.scanner.white_correction is False


def test_quick_switching_derives_from_pro_state(quick_bundle) -> None:
    _app, _widgets, _controller, deck = quick_bundle
    deck._mode_tabs.set_current(1)
    deck._mode_tabs.set_current(0)
    assert isinstance(deck._quick_params, QuickParams)
    assert deck._quick_params.exposure == pytest.approx(0.0)
    assert deck._quick_params.contrast == pytest.approx(0.0)


def test_extreme_black_level_is_clamped_on_refresh(quick_bundle) -> None:
    _app, widgets, _controller, deck = quick_bundle
    widgets.scanner.black_level.value = 1.0
    widgets.scanner.black_correction.value = True
    deck.refresh()
    state = collect_gui_state(widgets=widgets)
    assert state.scanner.black_level == pytest.approx(0.08)
    assert widgets.scanner.black_level.value == pytest.approx(0.08)

    widgets.scanner.black_correction.value = False
    state = collect_gui_state(widgets=widgets)
    assert state.scanner.black_correction is False
