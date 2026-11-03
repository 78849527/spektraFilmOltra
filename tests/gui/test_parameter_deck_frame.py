from __future__ import annotations

import pytest
from qtpy import QtWidgets

from spektrafilm_gui.controller import GuiController
from spektrafilm_gui.parameter_deck import ParameterDeck
from spektrafilm_gui.state import PROJECT_DEFAULT_GUI_STATE
from spektrafilm_gui.state_bridge import apply_gui_state
from spektrafilm_gui.widgets import create_widget_bundle


@pytest.fixture()
def deck() -> ParameterDeck:
    _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    widgets = create_widget_bundle()
    apply_gui_state(PROJECT_DEFAULT_GUI_STATE, widgets=widgets)
    controller = GuiController(viewer=object(), widgets=widgets)
    return ParameterDeck(widgets, controller)


def test_frame_toggle_defaults_to_enabled(deck: ParameterDeck) -> None:
    assert deck.frame_state() == (True, 'paper_white')
    assert deck._frame_switch.isChecked() is True


def test_set_frame_state_is_silent(deck: ParameterDeck) -> None:
    emitted: list[int] = []
    deck.frame_changed.connect(lambda: emitted.append(1))
    deck.set_frame_state({'enabled': False, 'preset': 'film_135'})
    assert deck.frame_state() == (False, 'film_135')
    assert emitted == []


def test_set_frame_state_ignores_unknown_values(deck: ParameterDeck) -> None:
    deck.set_frame_state({'enabled': True, 'preset': 'not-a-preset'})
    deck.set_frame_state(None)
    assert deck.frame_state() == (True, 'paper_white')


def test_toggle_emits_frame_changed(deck: ParameterDeck) -> None:
    emitted: list[int] = []
    deck.frame_changed.connect(lambda: emitted.append(1))
    deck._frame_switch.setChecked(False)
    assert emitted == [1]
    assert deck.frame_state()[0] is False


def test_frame_row_sits_below_the_parameter_stack(deck: ParameterDeck) -> None:
    body = deck._mode_stack.parentWidget()
    layout = body.layout()
    last = layout.itemAt(layout.count() - 1).widget()
    assert last.objectName() == 'deckFrameRow'
