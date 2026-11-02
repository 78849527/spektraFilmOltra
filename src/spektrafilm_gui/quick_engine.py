"""快速模式的会话状态：基线捕获、映射写入、Custom 判定与持久化。

一次工程会话里，每个轴记录两样东西：
- ``baseline``：进入工程时该轴拥有的原生字段值（含 bool/tuple）。
- ``intent``：用户在快速面板上的 q 值，0 表示保持 baseline。

专业模式改字段后，用 ``intent`` + ``baseline`` 计算期望值；与实际值不一致
就标记 ``custom``。快速面板不会在用户未操作时覆盖专业参数。
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any, Mapping

from spektrafilm_gui.quick_controls import AXES, empty_intent, expected_values
from spektrafilm_gui.state import GuiState, clone_gui_state


SCHEMA_VERSION = 1
STATUS_NORMAL = 'normal'
STATUS_CUSTOM = 'custom'
_EPS = 1e-9


def _read_path(root: Any, path: str) -> Any:
    value = root
    for part in path.split('.'):
        value = getattr(value, part)
    return value


def _is_frozen(value: Any) -> bool:
    params = getattr(value, '__dataclass_params__', None)
    return bool(params and params.frozen)


def _set_path(root: Any, parts: list[str], value: Any) -> Any:
    name = parts[0]
    if len(parts) == 1:
        if _is_frozen(root):
            return replace(root, **{name: value})
        setattr(root, name, value)
        return root
    child = getattr(root, name)
    new_child = _set_path(child, parts[1:], value)
    if new_child is child:
        return root
    if _is_frozen(root):
        return replace(root, **{name: new_child})
    setattr(root, name, new_child)
    return root


def _write_path(root: Any, path: str, value: Any) -> Any:
    """写入点路径；遇到 frozen dataclass 时返回替换后的新对象。"""
    return _set_path(root, path.split('.'), value)


def profile_signature(state: GuiState) -> tuple[str, str]:
    return (
        str(getattr(state.selection, 'film_stock', '') or ''),
        str(getattr(state.selection, 'print_paper', '') or ''),
    )


def _freeze(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _same_value(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return bool(actual) is expected
    if isinstance(expected, tuple):
        try:
            actual_values = tuple(actual)
        except TypeError:
            return False
        if len(actual_values) != len(expected):
            return False
        return all(_same_number(a, e) for a, e in zip(actual_values, expected))
    try:
        return _same_number(actual, expected)
    except (TypeError, ValueError):
        return actual == expected


def _same_number(actual: Any, expected: Any) -> bool:
    a = float(actual)
    e = float(expected)
    tolerance = max(1e-6, abs(e) * 1e-4)
    return abs(a - e) <= tolerance


def _validate_baseline(raw: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    baseline: dict[str, dict[str, Any]] = {}
    for name, axis in AXES.items():
        entry = raw.get(name)
        if not isinstance(entry, Mapping):
            continue
        values: dict[str, Any] = {}
        for path in axis.owned:
            if path in entry:
                values[path] = _freeze(entry[path])
        if values:
            baseline[name] = values
    return baseline


class QuickEngine:
    """单个工程的快速模式状态。"""

    def __init__(self) -> None:
        self.baseline: dict[str, dict[str, Any]] = {}
        self.intent: dict[str, float] = empty_intent()
        self.profile: tuple[str, str] | None = None

    # ── 基线 ────────────────────────────────────────────────
    def capture(self, state: GuiState, *, clear_intent: bool = False) -> None:
        self.baseline = {
            name: {path: _freeze(_read_path(state, path)) for path in axis.owned}
            for name, axis in AXES.items()
        }
        self.profile = profile_signature(state)
        if clear_intent:
            self.intent = empty_intent()

    def has_baseline(self) -> bool:
        return all(
            name in self.baseline and all(path in self.baseline[name] for path in axis.owned)
            for name, axis in AXES.items()
        )

    def ensure_baseline(self, state: GuiState) -> None:
        if not self.has_baseline():
            self.capture(state)

    def profile_changed(self, state: GuiState) -> bool:
        return self.profile is not None and self.profile != profile_signature(state)

    # ── 读写 ────────────────────────────────────────────────
    def set_axis(self, state: GuiState, name: str, q: float) -> GuiState:
        axis = AXES[name]
        q = max(axis.lo, min(axis.hi, float(q)))
        self.intent[name] = q
        self.ensure_baseline(state)
        new_state = clone_gui_state(state)
        for path, value in expected_values(axis, q, self.baseline[name]).items():
            new_state = _write_path(new_state, path, value)
        return new_state

    def apply_intents(self, state: GuiState) -> GuiState:
        self.ensure_baseline(state)
        new_state = clone_gui_state(state)
        for name, axis in AXES.items():
            q = float(self.intent.get(name, 0.0))
            if abs(q) <= _EPS:
                continue
            for path, value in expected_values(axis, q, self.baseline[name]).items():
                new_state = _write_path(new_state, path, value)
        return new_state

    def restore_baseline(self, state: GuiState) -> GuiState:
        self.ensure_baseline(state)
        new_state = clone_gui_state(state)
        for name, axis in AXES.items():
            for path, value in self.baseline.get(name, {}).items():
                new_state = _write_path(new_state, path, value)
        self.intent = empty_intent()
        return new_state

    def rebase(self, state: GuiState) -> GuiState:
        """胶片/相纸切换后，先撤销旧的快速意图，再重捕基线并套回一次。

        否则会把「已叠加过一次的当前值」当作新基线，再叠加一次意图，
        连续换片时参数会一路漂移。
        """
        if not self.has_baseline():
            self.capture(state)
            return self.apply_intents(state)

        intent = dict(self.intent)
        for name, axis in AXES.items():
            if abs(float(intent.get(name, 0.0))) <= _EPS:
                continue
            entry = self.baseline.get(name, {})
            for path in axis.owned:
                if path in entry:
                    state = _write_path(state, path, entry[path])
        self.capture(state)
        self.intent = intent
        return self.apply_intents(state)

    # ── 状态 ────────────────────────────────────────────────
    def status(self, state: GuiState, name: str) -> str:
        axis = AXES[name]
        self.ensure_baseline(state)
        q = float(self.intent.get(name, 0.0))
        try:
            expected = expected_values(axis, q, self.baseline[name])
        except KeyError:
            return STATUS_CUSTOM
        for path, value in expected.items():
            if not _same_value(_read_path(state, path), value):
                return STATUS_CUSTOM
        return STATUS_NORMAL

    def statuses(self, state: GuiState) -> dict[str, str]:
        return {name: self.status(state, name) for name in AXES}

    def native_summary(self, state: GuiState, name: str) -> str:
        """该轴拥有的原生字段当前值，供快速面板 tooltip 显示。"""
        axis = AXES[name]
        lines = []
        for path in axis.owned:
            value = _read_path(state, path)
            if isinstance(value, bool):
                text = '开' if value else '关'
            elif isinstance(value, tuple):
                text = '[' + ', '.join(f'{float(item):.3g}' for item in value) + ']'
            elif isinstance(value, (int, float)):
                text = f'{float(value):.3g}'
            else:
                text = str(value)
            lines.append(f'{path} = {text}')
        return '\n'.join(lines)

    def dirty_count(self) -> int:
        return sum(1 for value in self.intent.values() if abs(float(value)) > _EPS)

    # ── 持久化 ──────────────────────────────────────────────
    def load(self, raw: Any, state: GuiState) -> None:
        self.baseline = {}
        self.intent = empty_intent()
        if isinstance(raw, Mapping) and raw.get('schema') == SCHEMA_VERSION:
            baseline_raw = raw.get('baseline')
            if isinstance(baseline_raw, Mapping):
                self.baseline = _validate_baseline(baseline_raw)
            intent_raw = raw.get('intent')
            if isinstance(intent_raw, Mapping):
                for name, axis in AXES.items():
                    try:
                        value = float(intent_raw.get(name, 0.0))
                    except (TypeError, ValueError):
                        value = 0.0
                    self.intent[name] = max(axis.lo, min(axis.hi, value))
        # 旧工程或缺失字段：用当前原生值补齐，避免任何字段被 map 到 0。
        if not self.baseline:
            self.capture(state)
        for name, axis in AXES.items():
            entry = self.baseline.setdefault(name, {})
            for path in axis.owned:
                if path not in entry:
                    entry[path] = _freeze(_read_path(state, path))
        self.profile = profile_signature(state)

    def to_dict(self) -> dict[str, Any]:
        return {
            'schema': SCHEMA_VERSION,
            'baseline': {
                name: {path: _thaw(value) for path, value in values.items()}
                for name, values in self.baseline.items()
            },
            'intent': {name: float(value) for name, value in self.intent.items()},
            'updated_at': time.time(),
        }


__all__ = [
    'QuickEngine',
    'SCHEMA_VERSION',
    'STATUS_CUSTOM',
    'STATUS_NORMAL',
    'profile_signature',
]
