"""启动时下发给前端的目录与选项。

单一来源：胶片/相纸信息从 profile JSON 读取，快速轴与选项直接引用 GUI 侧定义。
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

from spektrafilm.model.illuminants import Illuminants
from spektrafilm.model.stocks import FilmStocks, PrintPapers
from spektrafilm_gui import options, ui_names
from spektrafilm_gui.export_settings import load_export_settings
from spektrafilm_gui.persistence import gui_state_to_dict
from spektrafilm_gui.quick_controls import AXES, PAD_CC_FULL_SCALE, QUICK_LAYOUT
from spektrafilm_gui.state import PROJECT_DEFAULT_GUI_STATE


def _read_profile_info(stock: str) -> dict[str, Any]:
    resource = resources.files('spektrafilm.data.profiles').joinpath(f'{stock}.json')
    with resource.open('r', encoding='utf-8') as handle:
        payload = json.load(handle)
    info = payload.get('info') or {}
    return {
        'stock': str(info.get('stock') or stock),
        'name': str(info.get('name') or stock),
        'type': str(info.get('type') or 'negative'),
        'support': str(info.get('support') or 'film'),
        'target_print': info.get('target_print'),
    }


@lru_cache(maxsize=1)
def _films() -> tuple[dict[str, Any], ...]:
    entries = []
    for member in FilmStocks:
        info = _read_profile_info(member.value)
        kind = 'cinema' if 'vision3' in member.value else info['type']
        entries.append({
            **info,
            'id': member.value,
            'kind': kind,
            'display_name': ui_names.film_display_name(member.value),
        })
    return tuple(entries)


@lru_cache(maxsize=1)
def _papers() -> tuple[dict[str, Any], ...]:
    entries = []
    for member in PrintPapers:
        info = _read_profile_info(member.value)
        entries.append({
            **info,
            'id': member.value,
            'kind': 'paper',
            'display_name': ui_names.paper_display_name(member.value),
        })
    return tuple(entries)


def _axis(name: str) -> dict[str, Any]:
    axis = AXES[name]
    return {
        'id': axis.name,
        'label': axis.label,
        'lo': axis.lo,
        'hi': axis.hi,
        'step': axis.step,
        'decimals': axis.decimals,
        'suffix': axis.suffix,
        'tooltip': axis.tooltip,
    }


def quick_layout() -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for title, entries in QUICK_LAYOUT:
        items: list[dict[str, Any]] = []
        for entry in entries:
            if entry[0] == 'axis':
                items.append({'kind': 'axis', 'axis': _axis(entry[1])})
            elif entry[0] == 'pad':
                items.append({
                    'kind': 'pad',
                    'title': entry[1],
                    'axes': [_axis(entry[2][0]), _axis(entry[2][1])],
                    'full_scale': PAD_CC_FULL_SCALE,
                })
        groups.append({'title': title, 'items': items})
    return groups


def _enum_values(enum_cls: type) -> list[str]:
    return [str(member.value) for member in enum_cls]


def option_catalog() -> dict[str, Any]:
    return {
        'color_spaces': _enum_values(options.RGBColorSpaces),
        'rgb_to_raw_methods': _enum_values(options.RGBtoRAWMethod),
        'raw_white_balance': _enum_values(options.RawWhiteBalance),
        'auto_exposure_methods': _enum_values(options.AutoExposureMethods),
        'diffusion_families': _enum_values(options.DiffusionFilterFamilies),
        'input_gamut_compress': _enum_values(options.InputGamutCompressAlgorithms),
        'output_gamut_compress': _enum_values(options.OutputGamutCompressAlgorithms),
        'illuminants': _enum_values(Illuminants),
    }


def bootstrap() -> dict[str, Any]:
    from spektrafilm_gui.grade_recipe import GradeRecipe

    return {
        'films': list(_films()),
        'papers': list(_papers()),
        'quick_layout': quick_layout(),
        'options': option_catalog(),
        'state': gui_state_to_dict(PROJECT_DEFAULT_GUI_STATE),
        'export_settings': load_export_settings().to_dict(),
        'grade_recipe': GradeRecipe().to_dict(),
    }


__all__ = ['bootstrap', 'option_catalog', 'quick_layout']
