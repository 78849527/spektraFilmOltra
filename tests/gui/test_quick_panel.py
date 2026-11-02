from __future__ import annotations

import json

import pytest
from qtpy import QtWidgets

from spektrafilm_gui.controller import GuiController
from spektrafilm_gui.parameter_deck import ParameterDeck
from spektrafilm_gui.quick_controls import AXES
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
    deck._quick_engine.capture(collect_gui_state(widgets=widgets))
    deck._quick_panel.set_intents(deck._quick_engine.intent)
    return app, widgets, controller, deck


def test_quick_panel_axis_count() -> None:
    pad_axes = {'print_balance_y', 'print_balance_m'}
    assert len(AXES) == 12
    assert len(AXES) - len(pad_axes) == 10


def test_quick_panel_rows_and_pad(quick_bundle) -> None:
    _app, _widgets, _controller, deck = quick_bundle
    panel = deck._quick_panel
    expected_rows = set(AXES) - {'print_balance_y', 'print_balance_m'}
    assert set(panel._rows) == expected_rows
    assert panel._pad is not None
    assert deck._mode == 'quick'


def test_slider_commit_writes_native_field(quick_bundle) -> None:
    _app, widgets, _controller, deck = quick_bundle
    row = deck._quick_panel.row('camera_exposure')
    row.set_value(1.0)
    row._commit()
    state = collect_gui_state(widgets=widgets)
    assert state.camera.exposure_compensation_ev == pytest.approx(1.0)
    assert state.simulation.enlarger.print_exposure_compensation is False
    assert deck._quick_engine.intent['camera_exposure'] == pytest.approx(1.0)


def test_color_pad_writes_both_filter_shifts(quick_bundle) -> None:
    _app, widgets, _controller, deck = quick_bundle
    pad = deck._quick_panel._pad
    pad.set_values(30.0, -20.0)
    pad._commit()
    state = collect_gui_state(widgets=widgets)
    assert state.simulation.enlarger.y_filter_shift == pytest.approx(18.0)
    assert state.simulation.enlarger.m_filter_shift == pytest.approx(-12.0)


def test_professional_edit_marks_custom(quick_bundle) -> None:
    _app, widgets, _controller, deck = quick_bundle
    widgets.scanner.unsharp_mask.value = (0.7, 1.4)
    deck._on_change()
    dot = deck._quick_panel.row('scanner_clarity')._dot
    assert dot.isHidden() is False


def test_all_quick_rows_apply_without_error(quick_bundle) -> None:
    _app, widgets, _controller, deck = quick_bundle
    for name, row in deck._quick_panel._rows.items():
        row.set_value(50.0)
        row._commit()
        state = collect_gui_state(widgets=widgets)
        assert state is not None, name

    pad = deck._quick_panel._pad
    pad.set_values(50.0, 50.0)
    pad._commit()
    state = collect_gui_state(widgets=widgets)
    assert state.simulation.enlarger.y_filter_shift == pytest.approx(30.0)
    assert state.simulation.enlarger.m_filter_shift == pytest.approx(30.0)
    assert deck._quick_engine.dirty_count() == len(AXES)


def test_quick_state_roundtrip_through_json(quick_bundle) -> None:
    _app, _widgets, _controller, deck = quick_bundle
    row = deck._quick_panel.row('print_brightness')
    row.set_value(1.0)
    row._commit()
    raw = json.loads(json.dumps(deck.quick_state_dict()))

    deck.set_quick_state(raw)
    assert deck._quick_panel.row('print_brightness').value() == pytest.approx(1.0)
    assert deck._quick_engine.intent['print_brightness'] == pytest.approx(1.0)


def test_reset_quick_restores_baseline(quick_bundle) -> None:
    _app, widgets, _controller, deck = quick_bundle
    before = collect_gui_state(widgets=widgets)
    row = deck._quick_panel.row('tonal_contrast')
    row.set_value(50.0)
    row._commit()
    assert collect_gui_state(widgets=widgets).chemistry.gamma_factor != before.chemistry.gamma_factor

    deck._reset_quick()
    after = collect_gui_state(widgets=widgets)
    assert after.chemistry.gamma_factor == pytest.approx(before.chemistry.gamma_factor)
    assert deck._quick_panel.row('tonal_contrast').value() == 0.0


def test_color_pad_readouts_show_actual_cc(quick_bundle) -> None:
    _app, _widgets, _controller, deck = quick_bundle
    panel = deck._quick_panel
    panel._pad.set_values(50.0, -25.0)
    panel._update_pad_readouts(50.0, -25.0)

    assert panel._pad_readouts['print_balance_y'].text() == '冷暖 +30 CC'
    assert panel._pad_readouts['print_balance_m'].text() == '品红 -15 CC'


def test_quick_tooltips_expose_native_values(quick_bundle) -> None:
    _app, _widgets, _controller, deck = quick_bundle
    deck.refresh()

    row_tip = deck._quick_panel.row('print_brightness').toolTip()
    assert '当前原生值' in row_tip
    assert 'simulation.enlarger.print_exposure =' in row_tip

    pad_tip = deck._quick_panel._pad.toolTip()
    assert 'simulation.enlarger.y_filter_shift =' in pad_tip
    assert 'simulation.enlarger.m_filter_shift =' in pad_tip


def test_scan_film_disables_print_axes_and_pad(quick_bundle) -> None:
    _app, widgets, _controller, deck = quick_bundle
    widgets.simulation.set_scan_film_value(True)
    deck._refresh_quick_availability()

    panel = deck._quick_panel
    for name in ('print_brightness', 'tonal_contrast'):
        row = panel.row(name)
        assert row.slider.isEnabled() is False
        assert '印相阶段' in row.toolTip()
    assert panel._pad.isEnabled() is False
    assert panel.row('camera_exposure').slider.isEnabled() is True

    widgets.simulation.set_scan_film_value(False)
    deck._refresh_quick_availability()
    assert panel.row('print_brightness').slider.isEnabled() is True
    assert panel._pad.isEnabled() is True


def test_slider_ignores_wheel(quick_bundle) -> None:
    _app, _widgets, _controller, deck = quick_bundle

    class _WheelEvent:
        def __init__(self) -> None:
            self.ignored = False

        def ignore(self) -> None:
            self.ignored = True

    for name in ('camera_exposure', 'print_brightness'):
        slider = deck._quick_panel.row(name).slider
        before = slider.value()
        event = _WheelEvent()
        slider.wheelEvent(event)
        assert event.ignored is True
        assert slider.value() == before

    pro_slider = deck._rows[('simulation', 'print_exposure')].slider
    before = pro_slider.value()
    event = _WheelEvent()
    pro_slider.wheelEvent(event)
    assert event.ignored is True
    assert pro_slider.value() == before
