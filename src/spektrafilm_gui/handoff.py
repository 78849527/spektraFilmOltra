"""调色台交接图：路径、显影指纹与 LibraryItem.state 里的 grade 小节。

交接图是第三步调色台的输入，第二步只负责生成与缓存它：

- 16-bit TIFF / ProPhoto RGB / 线性（不写 CCTF）/ 内嵌 ICC
- 全尺寸显影结果，不经过预览缩放
- 指纹只包含会改变显影结果的参数，显示/预览/保存偏好不参与
"""

from __future__ import annotations

import copy
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping

from spektrafilm_gui import app_paths
from spektrafilm_gui.grade_recipe import GradeRecipe

SCHEMA_VERSION = 1
HANDOFF_VERSION = 2
HANDOFF_FORMAT = 'tiff16-prophoto-linear'
HANDOFF_FILENAME = 'handoff.tif'

# 这些键只影响显示、预览或导出，不改变交接图本身。
_IGNORED_KEYS = frozenset({
    'display',
    'quick',
    'grade',
    'auto_preview',
    'saving_color_space',
    'saving_cctf_encoding',
})


def handoff_path(item_id: str) -> Path:
    return (
        app_paths.app_data_dir()
        / 'library'
        / 'projects'
        / str(item_id)
        / HANDOFF_FILENAME
    )


def _stripped(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _stripped(item)
            for key, item in value.items()
            if str(key) not in _IGNORED_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_stripped(item) for item in value]
    return value


def handoff_fingerprint(state_data: Mapping[str, Any] | None) -> str:
    """只对会改变显影结果的字段取哈希，用于判断交接图是否过期。"""
    payload = _stripped(state_data or {})
    encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha1(encoded.encode('utf-8')).hexdigest()


def _grade_section(state_data: Mapping[str, Any] | None) -> dict[str, Any]:
    grade = state_data.get('grade') if isinstance(state_data, Mapping) else None
    return dict(grade) if isinstance(grade, Mapping) else {}


def _grade_schema(grade: Mapping[str, Any]) -> int:
    try:
        return max(int(grade.get('schema') or 0), SCHEMA_VERSION)
    except (TypeError, ValueError):
        return SCHEMA_VERSION


def read_handoff(state_data: Mapping[str, Any] | None) -> dict[str, Any] | None:
    handoff = _grade_section(state_data).get('handoff')
    return dict(handoff) if isinstance(handoff, Mapping) else None


def handoff_is_current(state_data: Mapping[str, Any] | None, fingerprint: str) -> bool:
    handoff = read_handoff(state_data)
    if not handoff:
        return False
    try:
        version = int(handoff.get('version') or 0)
    except (TypeError, ValueError):
        version = 0
    if version != HANDOFF_VERSION:
        return False
    if str(handoff.get('fingerprint') or '') != str(fingerprint):
        return False
    path = Path(str(handoff.get('path') or ''))
    return bool(str(path)) and path.is_file()


def write_handoff(
    state_data: Mapping[str, Any] | None,
    *,
    path: str | Path,
    fingerprint: str,
    width: int = 0,
    height: int = 0,
) -> dict[str, Any]:
    """把交接图信息合并进 state['grade']，保留已有的调色配方。"""
    data = copy.deepcopy(dict(state_data)) if isinstance(state_data, Mapping) else {}
    grade = _grade_section(data)
    grade['schema'] = _grade_schema(grade)
    grade['handoff'] = {
        'version': HANDOFF_VERSION,
        'path': str(path),
        'fingerprint': str(fingerprint),
        'width': int(width),
        'height': int(height),
        'format': HANDOFF_FORMAT,
    }
    grade['updated_at'] = time.time()
    data['grade'] = grade
    return data


def has_grade_recipe(state_data: Mapping[str, Any] | None) -> bool:
    """工程是否已有调色配方；只生成交接图不算“已调色”。"""
    recipe = _grade_section(state_data).get('recipe')
    return isinstance(recipe, Mapping) and bool(recipe)


def read_grade_recipe(state_data: Mapping[str, Any] | None) -> GradeRecipe:
    """读取配方；缺失或损坏时回退到全中性配方。"""
    recipe = _grade_section(state_data).get('recipe')
    return GradeRecipe.from_dict(recipe) if isinstance(recipe, Mapping) else GradeRecipe()


def write_grade_recipe(
    state_data: Mapping[str, Any] | None,
    recipe: GradeRecipe,
    *,
    preset_id: str = '',
) -> dict[str, Any]:
    """把配方合并进 state['grade']，保留 handoff 信息。"""
    data = copy.deepcopy(dict(state_data)) if isinstance(state_data, Mapping) else {}
    grade = _grade_section(data)
    grade['schema'] = _grade_schema(grade)
    grade['recipe'] = recipe.to_dict()
    grade['preset_id'] = str(preset_id or '')
    grade['updated_at'] = time.time()
    data['grade'] = grade
    return data


__all__ = [
    'HANDOFF_FILENAME',
    'HANDOFF_FORMAT',
    'HANDOFF_VERSION',
    'SCHEMA_VERSION',
    'handoff_fingerprint',
    'handoff_is_current',
    'handoff_path',
    'has_grade_recipe',
    'read_grade_recipe',
    'read_handoff',
    'write_grade_recipe',
    'write_handoff',
]
