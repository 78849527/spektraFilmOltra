from __future__ import annotations

import numpy as np
import pytest
from qtpy import QtWidgets

from spektrafilm_gui.controller import GuiController
from spektrafilm_gui.parameter_deck import ParameterDeck, PRO_PAGE_LABEL
from spektrafilm_gui.state import PROJECT_DEFAULT_GUI_STATE
from spektrafilm_gui.state_bridge import apply_gui_state, collect_gui_state, GUI_STATE_SECTION_NAMES
from spektrafilm_gui.widgets import create_widget_bundle


@pytest.fixture()
def deck_bundle():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    widgets = create_widget_bundle()
    apply_gui_state(PROJECT_DEFAULT_GUI_STATE, widgets=widgets)
    controller = GuiController(viewer=object(), widgets=widgets)
    deck = ParameterDeck(widgets, controller)
    return app, widgets, controller, deck


def test_deck_exposes_every_editable_parameter(deck_bundle) -> None:
    _app, widgets, _controller, deck = deck_bundle
    missing = []
    for section in GUI_STATE_SECTION_NAMES:
        holder = getattr(widgets, section)
        editors = getattr(holder, '_editors', None) or {}
        for leaf in editors:
            if (section, leaf) not in deck._rows:
                missing.append((section, leaf))
    for leaf in ('white_balance', 'temperature', 'tint', 'lens_correction'):
        if ('load_raw', leaf) not in deck._rows:
            missing.append(('load_raw', leaf))
    assert missing == [('display', 'preview_max_size')]


def test_deck_has_input_and_professional_tabs(deck_bundle) -> None:
    _app, _widgets, _controller, deck = deck_bundle
    labels = list(deck._tabs._labels)
    assert '输入' in labels
    assert PRO_PAGE_LABEL in labels


def test_deck_film_selection_applies_profile_defaults(deck_bundle) -> None:
    _app, widgets, _controller, deck = deck_bundle
    widgets.simulation.bottom_auto_preview.setChecked(False)
    widgets.simulation._editors['saving_color_space'].value = 'Display P3'
    events: list[tuple[str, str]] = []
    deck.profile_changed.connect(lambda leaf, raw: events.append((leaf, raw)))
    row = deck.row('film_stock', section='simulation')
    index = row.combo.findData('kodak_ektachrome_100')
    assert index >= 0
    row.combo.setCurrentIndex(index)
    row.combo.textActivated.emit(row.combo.currentText())
    _app.processEvents()
    state = collect_gui_state(widgets=widgets)
    assert state.simulation.selection.film_stock == 'kodak_ektachrome_100'
    assert state.simulation.io.scan_film is True
    assert state.simulation.workflow.auto_preview is False
    assert state.simulation.workflow.saving_color_space == 'Display P3'
    assert events == [('film_stock', 'kodak_ektachrome_100')]


def test_deck_profile_switch_disables_print_quick_axes(deck_bundle) -> None:
    _app, widgets, _controller, deck = deck_bundle
    deck._mode_tabs.set_current(0)
    assert deck._quick_panel.row('print_brightness').slider.isEnabled() is True

    row = deck.row('film_stock', section='simulation')
    index = row.combo.findData('fujifilm_provia_100f')
    assert index >= 0
    row.combo.setCurrentIndex(index)
    row.combo.textActivated.emit(row.combo.currentText())
    _app.processEvents()

    state = collect_gui_state(widgets=widgets)
    assert state.simulation.io.scan_film is True
    assert deck._quick_panel.row('print_brightness').slider.isEnabled() is False
    assert deck._quick_panel._pad.isEnabled() is False


def test_deck_conditions_disable_dependents(deck_bundle) -> None:
    _app, _widgets, _controller, deck = deck_bundle
    grain = deck.row('active', section='grain')
    particle = deck.row('particle_area_um2', section='grain')
    grain.switch.setChecked(False)
    assert particle.isEnabled() is False
    grain.switch.setChecked(True)
    assert particle.isEnabled() is True


def test_deck_number_and_vector_rows_write_state(deck_bundle) -> None:
    _app, widgets, _controller, deck = deck_bundle
    particle = deck.row('particle_area_um2', section='grain')
    particle.slider.setValue(particle._to_position(0.5))
    particle.slider.sliderReleased.emit()
    state = collect_gui_state(widgets=widgets)
    assert state.grain.particle_area_um2 == pytest.approx(0.5)

    crop = deck.row('crop_center', section='input_image')
    crop._component_spins[0].setValue(0.25)
    state = collect_gui_state(widgets=widgets)
    assert state.input_image.io.crop_center[0] == pytest.approx(0.25)
