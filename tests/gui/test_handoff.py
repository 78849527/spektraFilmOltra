from __future__ import annotations

import copy
from pathlib import Path

import pytest

from spektrafilm_gui import handoff as handoff_module
from spektrafilm_gui.handoff import (
    HANDOFF_FORMAT,
    handoff_fingerprint,
    handoff_is_current,
    handoff_path,
    has_grade_recipe,
    read_handoff,
    write_handoff,
)


def _state() -> dict:
    return {
        'camera': {'exposure_compensation_ev': 0.0},
        'simulation': {
            'film_stock': 'kodak_portra_400',
            'print_paper': 'kodak_supra_endura',
            'auto_preview': True,
            'saving_color_space': 'sRGB',
            'enlarger': {'print_exposure': 1.0},
            'io': {'scan_film': False, 'output_color_space': 'sRGB'},
        },
        'display': {'preview_max_size': 640},
        'quick': {'schema': 1, 'intent': {'camera_exposure': 0.0}},
    }


def test_fingerprint_ignores_display_and_saving_preferences() -> None:
    base = _state()
    changed = copy.deepcopy(base)
    changed['display']['preview_max_size'] = 1920
    changed['simulation']['auto_preview'] = False
    changed['simulation']['saving_color_space'] = 'ProPhoto RGB'
    changed['quick']['intent']['camera_exposure'] = 2.0

    assert handoff_fingerprint(base) == handoff_fingerprint(changed)


@pytest.mark.parametrize(
    ('section', 'key', 'value'),
    [
        ('camera', 'exposure_compensation_ev', 1.5),
        ('simulation', 'film_stock', 'kodak_gold_200'),
        ('simulation', 'print_paper', 'fujifilm_crystal_archive'),
        ('simulation', 'io', {'scan_film': True, 'output_color_space': 'sRGB'}),
    ],
)
def test_fingerprint_changes_with_develop_settings(section: str, key: str, value) -> None:
    base = _state()
    changed = copy.deepcopy(base)
    changed[section][key] = value
    assert handoff_fingerprint(base) != handoff_fingerprint(changed)


def test_handoff_path_lives_under_project_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(handoff_module.app_paths, 'app_data_dir', lambda: tmp_path)
    path = handoff_path('item-1')
    assert path == tmp_path / 'library' / 'projects' / 'item-1' / 'handoff.tif'


def test_write_handoff_merges_and_preserves_recipe(tmp_path: Path) -> None:
    recipe = {'schema': 1, 'basic': {'exposure': 0.5}}
    state = _state()
    state['grade'] = {'schema': 1, 'recipe': recipe}
    target = tmp_path / 'handoff.tif'
    target.write_bytes(b'x')

    updated = write_handoff(state, path=target, fingerprint='abc', width=640, height=480)
    handoff = read_handoff(updated)

    assert updated['grade']['recipe'] == recipe
    assert handoff == {
        'path': str(target),
        'fingerprint': 'abc',
        'width': 640,
        'height': 480,
        'format': HANDOFF_FORMAT,
    }
    assert has_grade_recipe(updated) is True


def test_handoff_is_current_checks_fingerprint_and_file(tmp_path: Path) -> None:
    target = tmp_path / 'handoff.tif'
    state = write_handoff(_state(), path=target, fingerprint='abc')

    assert handoff_is_current(state, 'abc') is False  # 文件还没写

    target.write_bytes(b'x')
    assert handoff_is_current(state, 'abc') is True
    assert handoff_is_current(state, 'other') is False
    assert handoff_is_current(_state(), 'abc') is False


def test_handoff_alone_is_not_a_grade_recipe() -> None:
    state = write_handoff(_state(), path='/tmp/handoff.tif', fingerprint='abc')
    assert has_grade_recipe(state) is False
    assert has_grade_recipe(None) is False
