from __future__ import annotations

import json
from pathlib import Path

from spektrafilm_gui.grade_presets import BUILTIN_PRESETS, GradePresetStore
from spektrafilm_gui.grade_recipe import GradeRecipe


def test_builtin_presets_are_available_and_read_only(tmp_path: Path) -> None:
    store = GradePresetStore(tmp_path / 'presets.json')
    names = [preset.name for preset in BUILTIN_PRESETS]
    assert names == ['中性', '清透', '暖调', '冷夜', '黑白']
    assert all(preset.builtin for preset in BUILTIN_PRESETS)
    assert store.delete(BUILTIN_PRESETS[0].id) is False
    assert store.rename(BUILTIN_PRESETS[0].id, 'x') is None


def test_save_rename_delete_roundtrip(tmp_path: Path) -> None:
    store = GradePresetStore(tmp_path / 'presets.json')
    recipe = GradeRecipe.from_dict({'light': {'exposure': 1.0}})
    preset = store.save('我的预设', recipe)
    assert preset.id.startswith('user:')
    assert store.get(preset.id) is not None
    assert preset.recipe.light.exposure == 1.0

    reloaded = GradePresetStore(tmp_path / 'presets.json')
    assert reloaded.get(preset.id) is not None

    renamed = store.rename(preset.id, '新名字')
    assert renamed is not None and renamed.name == '新名字'
    assert store.delete(preset.id) is True
    assert store.get(preset.id) is None
    assert GradePresetStore(tmp_path / 'presets.json').all() == list(BUILTIN_PRESETS)


def test_duplicate_names_get_suffix(tmp_path: Path) -> None:
    store = GradePresetStore(tmp_path / 'presets.json')
    first = store.save('重复', GradeRecipe())
    second = store.save('重复', GradeRecipe())
    assert first.name == '重复'
    assert second.name == '重复 2'


def test_import_and_export_preset_file(tmp_path: Path) -> None:
    store = GradePresetStore(tmp_path / 'presets.json')
    recipe = GradeRecipe.from_dict({'color': {'temperature': 12.0}})
    preset = store.save('导出测试', recipe)
    exported = tmp_path / 'exported.json'
    assert store.export_file(preset.id, exported) is True
    payload = json.loads(exported.read_text(encoding='utf-8'))
    assert payload['schema'] == 1
    assert payload['presets'][0]['name'] == '导出测试'

    imported = store.import_file(exported)
    assert imported is not None
    assert imported.recipe.color.temperature == 12.0

    single = tmp_path / 'single.json'
    single.write_text(
        json.dumps({'name': '单条', 'recipe': recipe.to_dict()}),
        encoding='utf-8',
    )
    imported_single = store.import_file(single)
    assert imported_single is not None
    assert imported_single.name == '单条'
