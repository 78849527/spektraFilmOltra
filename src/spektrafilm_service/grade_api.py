"""调色台接口：复用 grade_engine 与调色预设存储。"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from spektrafilm_gui import app_paths
from spektrafilm_gui.export_settings import ExportSettings
from spektrafilm_gui.grade_engine import (
    downsample_linear,
    load_handoff_image,
    prepare_source,
    render,
)
from spektrafilm_gui.grade_presets import GradePresetStore
from spektrafilm_gui.grade_recipe import GradeRecipe

from spektrafilm_service import develop, paths
from spektrafilm_service.jobs import Job, JobQueue

GRADE_PREVIEW_EDGE = 1600
GRADE_EXPORT_TEMPLATE = '{name}_graded'


class GradeApi:
    def __init__(self, queue: JobQueue, source_session) -> None:
        self.queue = queue
        self.presets = GradePresetStore()
        self._session = source_session
        self._source_cache: tuple[str, float, np.ndarray] | None = None

    # ── 预设与 LUT ──────────────────────────────────────────
    def preset_payload(self) -> dict[str, Any]:
        return {
            'presets': [
                {**preset.to_dict(), 'builtin': preset.builtin}
                for preset in self.presets.all()
            ]
        }

    def save_preset(self, name: str, recipe: dict[str, Any]) -> dict[str, Any]:
        preset = self.presets.save(name, GradeRecipe.from_dict(recipe))
        return {'preset': {**preset.to_dict(), 'builtin': False}, **self.preset_payload()}

    def rename_preset(self, preset_id: str, name: str) -> dict[str, Any]:
        preset = self.presets.rename(preset_id, name)
        return {'preset': preset.to_dict() if preset else None, **self.preset_payload()}

    def delete_preset(self, preset_id: str) -> dict[str, Any]:
        deleted = self.presets.delete(preset_id)
        return {'deleted': deleted, **self.preset_payload()}

    def lut_dir(self) -> Path:
        path = app_paths.app_data_dir() / 'luts'
        path.mkdir(parents=True, exist_ok=True)
        return path

    def luts(self) -> dict[str, Any]:
        entries = []
        for path in sorted(self.lut_dir().glob('*.cube')):
            entries.append({'name': path.stem, 'path': str(path)})
        return {'luts': entries}

    def import_lut(self, source: str) -> dict[str, Any]:
        source_path = Path(source).expanduser()
        if source_path.suffix.lower() != '.cube' or not source_path.is_file():
            raise ValueError('只支持 .cube 文件')
        target = self.lut_dir() / source_path.name
        if source_path.resolve() != target.resolve():
            shutil.copy2(source_path, target)
        return {'name': target.stem, 'path': str(target), **self.luts()}

    def remove_lut(self, path: str) -> dict[str, Any]:
        target = Path(path).resolve()
        directory = self.lut_dir().resolve()
        if directory not in target.parents:
            raise ValueError('只能删除 LUT 库内的文件')
        if target.exists():
            target.unlink()
        return self.luts()

    # ── 渲染 ────────────────────────────────────────────────
    def _source(self, handoff_path: str) -> np.ndarray:
        path = Path(handoff_path)
        if not path.is_file():
            raise FileNotFoundError(f'交接图不存在：{path}')
        mtime = path.stat().st_mtime
        cached = self._source_cache
        if cached is not None and cached[0] == str(path) and cached[1] == mtime:
            return cached[2]
        image = load_handoff_image(path)
        source = np.ascontiguousarray(prepare_source(image))
        del image
        self._source_cache = (str(path), mtime, source)
        return source

    def submit_preview(self, handoff_path: str, recipe: dict[str, Any], edge: int = GRADE_PREVIEW_EDGE) -> Job:
        return self.queue.submit(
            'grade_preview',
            lambda job: self.run_preview(job, handoff_path, recipe, edge),
            supersede_kind='grade_preview',
        )

    def run_preview(self, job: Job, handoff_path: str, recipe: dict[str, Any], edge: int) -> dict[str, Any]:
        self.queue.update_progress(job, '载入交接图', 0, 1)
        source = self._source(handoff_path)
        width, height = self._preview_shape(source, edge)
        self.queue.update_progress(job, '渲染调色', 1, 2)
        preview = downsample_linear(source, max(width, height))
        data, analysis = render(preview, GradeRecipe.from_dict(recipe))
        rgb = np.uint8(np.clip(np.asarray(data), 0.0, 1.0) * 255)
        fingerprint = hashlib.sha1(
            json.dumps({'p': handoff_path, 'r': recipe, 'e': edge}, sort_keys=True, default=str).encode('utf-8')
        ).hexdigest()
        target = paths.preview_dir() / f'grade-{fingerprint[:16]}.png'
        develop.save_display_png(target, rgb)
        return {
            'image_path': str(target),
            'width': int(rgb.shape[1]),
            'height': int(rgb.shape[0]),
            'analysis': {
                'black_point': analysis.black_point,
                'white_point': analysis.white_point,
                'highlight_cast': analysis.highlight_cast,
                'shadow_cast': analysis.shadow_cast,
                'summary': analysis.summary,
            },
        }

    @staticmethod
    def _preview_shape(source: np.ndarray, edge: int) -> tuple[int, int]:
        height, width = source.shape[:2]
        long_edge = max(int(height), int(width))
        if long_edge <= edge:
            return width, height
        scale = float(edge) / float(long_edge)
        return max(1, int(round(width * scale))), max(1, int(round(height * scale)))

    def submit_export(self, handoff_path: str, recipe: dict[str, Any], settings: dict[str, Any], name: str) -> Job:
        return self.queue.submit(
            'grade_export',
            lambda job: self.run_export(job, handoff_path, recipe, settings, name),
        )

    def run_export(self, job: Job, handoff_path: str, recipe: dict[str, Any], settings: dict[str, Any], name: str) -> dict[str, Any]:
        self.queue.update_progress(job, '载入交接图', 0, 1)
        source = self._source(handoff_path)
        self.queue.update_progress(job, '渲染全尺寸', 1, 2)
        data, _analysis = render(source, GradeRecipe.from_dict(recipe))

        state = self._session.state.gui_state
        saving_color_space = str(state.simulation.workflow.saving_color_space or 'sRGB')
        saving_cctf = bool(state.simulation.workflow.saving_cctf_encoding)
        payload = np.asarray(data, dtype=np.float32)
        if saving_color_space != 'sRGB' or not saving_cctf:
            payload = develop.convert_to_saving_space(
                payload,
                source_color_space='sRGB',
                source_cctf_encoding=True,
                saving_color_space=saving_color_space,
                saving_cctf_encoding=saving_cctf,
            )

        export_settings = replace(
            ExportSettings.from_dict(settings),
            filename_template=GRADE_EXPORT_TEMPLATE,
        )
        photo = self._session.state.photo
        source_path = photo.path if photo is not None else name
        target = develop.export_image(
            payload,
            export_settings,
            color_space=saving_color_space,
            cctf_encoding=saving_cctf,
            source_path=source_path,
            film_stock=str(state.simulation.selection.film_stock or ''),
            print_paper=str(state.simulation.selection.print_paper or ''),
            metadata=photo.metadata if photo is not None else None,
        )
        return {
            'path': str(target),
            'color_space': saving_color_space,
            'cctf_encoding': saving_cctf,
        }


__all__ = ['GRADE_PREVIEW_EDGE', 'GradeApi']
