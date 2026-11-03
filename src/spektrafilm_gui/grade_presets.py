"""调色预设库：内置配方 + 用户预设，JSON 原子读写。

内置预设不可删除/重命名；用户预设保存在 AppData 的 grade_presets.json。
导入/导出使用同一份 ``{"schema": 1, "presets": [...]}`` 结构。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from spektrafilm_gui import app_paths
from spektrafilm_gui.grade_recipe import GradeRecipe

SCHEMA_VERSION = 1
PRESET_FILENAME = 'grade_presets.json'


@dataclass(slots=True)
class GradePreset:
    id: str
    name: str
    recipe: GradeRecipe
    builtin: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'recipe': self.recipe.to_dict(),
        }


def default_preset_path() -> Path:
    return app_paths.app_data_dir() / PRESET_FILENAME


def _builtin(preset_id: str, name: str, data: Mapping[str, Any]) -> GradePreset:
    return GradePreset(
        id=f'builtin:{preset_id}',
        name=name,
        recipe=GradeRecipe.from_dict(data),
        builtin=True,
    )


BUILTIN_PRESETS: tuple[GradePreset, ...] = (
    _builtin('neutral', '中性', {}),
    _builtin(
        'clean',
        '清透',
        {
            'light': {'contrast': 8.0, 'shadows': 10.0, 'blacks': -6.0},
            'transparency': {'tonal': 18.0},
            'quality': {'clarity': 8.0, 'sharpen_amount': 12.0},
        },
    ),
    _builtin(
        'warm',
        '暖调',
        {
            'light': {'contrast': 6.0, 'highlights': -8.0},
            'color': {
                'temperature': 12.0,
                'vibrance': 8.0,
                'grading': {
                    'highlights': {'hue': 40.0, 'saturation': 18.0},
                    'shadows': {'hue': 30.0, 'saturation': 8.0},
                },
            },
            'transparency': {'tonal': 10.0},
        },
    ),
    _builtin(
        'cool-night',
        '冷夜',
        {
            'light': {'exposure': -0.25, 'contrast': 10.0, 'blacks': -8.0},
            'color': {
                'temperature': -12.0,
                'saturation': -6.0,
                'grading': {
                    'shadows': {'hue': 225.0, 'saturation': 22.0},
                    'highlights': {'hue': 210.0, 'saturation': 8.0},
                },
            },
            'quality': {'clarity': 6.0},
        },
    ),
    _builtin(
        'mono',
        '黑白',
        {
            'light': {'contrast': 10.0, 'blacks': -6.0},
            'color': {'saturation': -100.0},
            'quality': {'clarity': 10.0},
        },
    ),
)


class GradePresetStore:
    def __init__(self, path: str | Path | None = None):
        self._path = Path(path) if path is not None else default_preset_path()
        self._user: list[GradePreset] = []
        self.load()

    @property
    def path(self) -> Path:
        return self._path

    def all(self) -> list[GradePreset]:
        return list(BUILTIN_PRESETS) + list(self._user)

    def get(self, preset_id: str) -> GradePreset | None:
        for preset in self.all():
            if preset.id == preset_id:
                return preset
        return None

    def load(self) -> None:
        self._user = []
        if not self._path.exists():
            return
        try:
            with self._path.open('r', encoding='utf-8') as handle:
                data = json.load(handle)
        except (OSError, ValueError, TypeError):
            return
        entries = data.get('presets') if isinstance(data, Mapping) else None
        if not isinstance(entries, list):
            return
        for entry in entries:
            preset = self._preset_from_entry(entry)
            if preset is not None:
                self._user.append(preset)

    def save(self, name: str, recipe: GradeRecipe) -> GradePreset:
        clean_name = self._unique_name(str(name).strip() or '未命名预设')
        preset = GradePreset(
            id=f'user:{uuid.uuid4().hex[:12]}',
            name=clean_name,
            recipe=recipe.clone(),
            builtin=False,
        )
        self._user.append(preset)
        self._write()
        return preset

    def rename(self, preset_id: str, name: str) -> GradePreset | None:
        preset = self.get(preset_id)
        if preset is None or preset.builtin:
            return None
        clean_name = str(name).strip()
        if not clean_name:
            return None
        updated = replace(preset, name=self._unique_name(clean_name, exclude=preset.id))
        self._replace_user(updated)
        self._write()
        return updated

    def delete(self, preset_id: str) -> bool:
        preset = self.get(preset_id)
        if preset is None or preset.builtin:
            return False
        self._user = [item for item in self._user if item.id != preset_id]
        self._write()
        return True

    def import_file(self, path: str | Path) -> GradePreset | None:
        source_path = Path(path)
        try:
            with source_path.open('r', encoding='utf-8') as handle:
                data = json.load(handle)
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(data, Mapping):
            return None

        entries = data.get('presets')
        if isinstance(entries, list) and entries:
            entry = entries[0]
            recipe = GradeRecipe.from_dict(
                entry.get('recipe') if isinstance(entry, Mapping) else entry,
            )
            name = str(entry.get('name') or source_path.stem) if isinstance(entry, Mapping) else source_path.stem
        elif isinstance(data.get('recipe'), Mapping):
            recipe = GradeRecipe.from_dict(data['recipe'])
            name = str(data.get('name') or source_path.stem)
        else:
            recipe = GradeRecipe.from_dict(data)
            name = source_path.stem
        return self.save(name, recipe)

    def export_file(self, preset_id: str, path: str | Path) -> bool:
        preset = self.get(preset_id)
        if preset is None:
            return False
        payload = {
            'schema': SCHEMA_VERSION,
            'presets': [preset.to_dict()],
        }
        try:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f'{target.name}.tmp')
            with temporary.open('w', encoding='utf-8') as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            os.replace(temporary, target)
        except OSError:
            return False
        return True

    # ── 内部 ────────────────────────────────────────────────────
    def _preset_from_entry(self, entry: Any) -> GradePreset | None:
        if not isinstance(entry, Mapping):
            return None
        preset_id = str(entry.get('id') or '')
        if not preset_id.startswith('user:'):
            return None
        name = str(entry.get('name') or '').strip()
        if not name:
            return None
        recipe = GradeRecipe.from_dict(entry.get('recipe'))
        return GradePreset(id=preset_id, name=name, recipe=recipe, builtin=False)

    def _replace_user(self, preset: GradePreset) -> None:
        self._user = [preset if item.id == preset.id else item for item in self._user]

    def _unique_name(self, name: str, *, exclude: str = '') -> str:
        existing = {item.name for item in self.all() if item.id != exclude}
        if name not in existing:
            return name
        index = 2
        while f'{name} {index}' in existing:
            index += 1
        return f'{name} {index}'

    def _write(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'schema': SCHEMA_VERSION,
            'presets': [
                {
                    'id': preset.id,
                    'name': preset.name,
                    'recipe': preset.recipe.to_dict(),
                    'updated_at': time.time(),
                }
                for preset in self._user
            ],
        }
        temporary = self._path.with_name(f'{self._path.name}.tmp')
        with temporary.open('w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, self._path)


__all__ = [
    'BUILTIN_PRESETS',
    'GradePreset',
    'GradePresetStore',
    'PRESET_FILENAME',
    'SCHEMA_VERSION',
    'default_preset_path',
]
