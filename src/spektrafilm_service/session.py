"""一次会话内的照片、状态与渲染缓存。"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from spektrafilm.runtime.api import digest_params
from spektrafilm.runtime.process import Simulator
from spektrafilm_gui import app_paths
from spektrafilm_gui.export_settings import ExportSettings
from spektrafilm_gui.params_mapper import build_params_from_state
from spektrafilm_gui.persistence import gui_state_from_dict
from spektrafilm_gui.quick_controls import AXES, disabled_axes
from spektrafilm_gui.quick_engine import QuickEngine
from spektrafilm_gui.runtime_guard import SIMULATION_LOCK
from spektrafilm_gui.state import PROJECT_DEFAULT_GUI_STATE, GuiState, clone_gui_state

from spektrafilm_service import develop, lut_preview, paths
from spektrafilm_service.jobs import Job, JobCancelled, JobQueue


@dataclass
class PreviewResult:
    fingerprint: str
    path: Path
    width: int
    height: int
    output_color_space: str
    elapsed_ms: int
    timings: dict[str, float]
    status: str


@dataclass
class FullRender:
    fingerprint: str
    image: np.ndarray
    output_color_space: str
    cctf_encoding: bool


def exif_payload(metadata: Any) -> dict[str, str]:
    """把 EXIF 里的机身、镜头与曝光参数整理成前端可直接显示的字段。"""
    exif = getattr(metadata, 'exif', None) if metadata is not None else None
    if exif is None:
        return {}

    data: dict[str, str] = {}
    for item in exif:
        try:
            key = item.key()
            text = str(item)
        except Exception:
            continue
        prefix = key + ': '
        if text.startswith(prefix):
            text = text[len(prefix):]
        data[key] = text.strip()

    def value(key: str) -> str:
        return data.get(key, '').strip()

    return {
        'make': value('Exif.Image.Make'),
        'model': value('Exif.Image.Model'),
        'lens': value('Exif.Photo.LensModel'),
        'exposure': value('Exif.Photo.ExposureTime').replace(' s', '').strip(),
        'aperture': value('Exif.Photo.FNumber').lstrip('Ff').strip(),
        'iso': value('Exif.Photo.PhotographicSensitivity') or value('Exif.Photo.ISOSpeedRatings'),
        'focal_length': value('Exif.Photo.FocalLength').replace(' mm', '').strip(),
        'taken_at': value('Exif.Photo.DateTimeOriginal'),
    }


@dataclass
class PhotoSession:
    path: str
    image: np.ndarray
    color_space: str
    cctf_decoding: bool
    is_raw: bool
    lens_summary: str
    metadata: Any
    width: int
    height: int
    original_preview_path: Path
    display_preview_path: Path
    last_full_render: FullRender | None = None
    last_fast_preview: PreviewResult | None = None
    preview_cache: dict[int, np.ndarray] = field(default_factory=dict)
    auto_ev_cache: dict[tuple[int, str], float] = field(default_factory=dict)


@dataclass
class SessionState:
    gui_state: GuiState = field(default_factory=lambda: clone_gui_state(PROJECT_DEFAULT_GUI_STATE))
    photo: PhotoSession | None = None
    last_preview: PreviewResult | None = None
    simulator: Simulator | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)


def _delta_e_stats(reference, candidate):
    import colour

    space = colour.RGB_COLOURSPACES['ProPhoto RGB']
    ref_lab = colour.XYZ_to_Lab(
        colour.RGB_to_XYZ(np.asarray(reference, dtype=float), space)
    )
    cand_lab = colour.XYZ_to_Lab(
        colour.RGB_to_XYZ(np.asarray(candidate, dtype=float), space)
    )
    delta = colour.delta_E(
        ref_lab.reshape(-1, 3), cand_lab.reshape(-1, 3), method='CIE 2000'
    )
    return {
        'max': float(np.max(delta)),
        'p99': float(np.percentile(delta, 99)),
        'mean': float(np.mean(delta)),
    }

class ServiceSession:
    def __init__(self, queue: JobQueue):
        self.state = SessionState()
        self.queue = queue
        self.quick = QuickEngine()
        self.lut_cache = lut_preview.PreviewLutCache()
        self.item_id = ''
        self._photo_counter = 0

    # ── 状态 ────────────────────────────────────────────────
    def state_dict(self) -> dict[str, Any]:
        from spektrafilm_gui.persistence import gui_state_to_dict

        return gui_state_to_dict(self.state.gui_state)

    def apply_state(self, data: dict[str, Any] | None) -> GuiState:
        if not data:
            return self.state.gui_state
        previous = self.state.gui_state
        state = gui_state_from_dict(data)
        profile_changed = (
            previous.selection.film_stock != state.selection.film_stock
            or previous.selection.print_paper != state.selection.print_paper
        )
        if profile_changed:
            state = self.quick.rebase(state)
        self.state.gui_state = state
        return state

    # ── 快速模式 ────────────────────────────────────────────
    def quick_payload(self) -> dict[str, Any]:
        state = self.state.gui_state
        return {
            'intents': dict(self.quick.intent),
            'axes': {
                name: {
                    'lo': axis.lo,
                    'hi': axis.hi,
                    'step': axis.step,
                    'decimals': axis.decimals,
                    'suffix': axis.suffix,
                }
                for name, axis in AXES.items()
            },
            'disabled': sorted(disabled_axes(scan_film=bool(state.simulation.io.scan_film))),
        }

    def set_quick_axis(self, name: str, value: float) -> dict[str, Any]:
        if name not in AXES:
            raise KeyError(f'未知快速轴：{name}')
        state = self.quick.set_axis(self.state.gui_state, name, float(value))
        self.state.gui_state = state
        return {'state': self.state_dict(), **self.quick_payload()}

    def reset_quick(self) -> dict[str, Any]:
        state = self.quick.restore_baseline(self.state.gui_state)
        self.state.gui_state = state
        return {'state': self.state_dict(), **self.quick_payload()}

    def reset_state(self) -> dict[str, Any]:
        state = clone_gui_state(PROJECT_DEFAULT_GUI_STATE)
        self.state.gui_state = state
        self.quick.capture(state, clear_intent=True)
        return {'state': self.state_dict(), **self.quick_payload()}

    # ── 打开照片 ────────────────────────────────────────────
    def open_photo(self, path: str, item_id: str = '') -> dict[str, Any]:
        with self.state.lock:
            self.item_id = str(item_id or '')
            gui_state = self.state.gui_state
            loaded = develop.load_input(path, {
                'white_balance': gui_state.gui_only.load_raw.white_balance,
                'temperature': gui_state.gui_only.load_raw.temperature,
                'tint': gui_state.gui_only.load_raw.tint,
                'lens_correction': gui_state.gui_only.load_raw.lens_correction,
            })
            self._photo_counter += 1
            photo_id = hashlib.sha1(f'{path}:{self._photo_counter}'.encode('utf-8')).hexdigest()[:12]

            preview = develop.display_preview_array(loaded.image, loaded.color_space, loaded.cctf_decoding)
            original_path = paths.preview_dir() / f'{photo_id}-original.png'
            display_path = paths.preview_dir() / f'{photo_id}-display.png'
            develop.save_original_png(original_path, preview)
            develop.save_original_png(display_path, preview)

            photo = PhotoSession(
                path=path,
                image=loaded.image,
                color_space=loaded.color_space,
                cctf_decoding=loaded.cctf_decoding,
                is_raw=loaded.is_raw,
                lens_summary=loaded.lens_summary,
                metadata=loaded.metadata,
                width=int(loaded.image.shape[1]),
                height=int(loaded.image.shape[0]),
                original_preview_path=original_path,
                display_preview_path=display_path,
            )
            self.state.photo = photo
            self.state.last_preview = None
            self.state.simulator = None
            self.quick.capture(self.state.gui_state, clear_intent=True)

            # RAW 与普通图都要把输入色彩写回状态，前端据此显示。
            gui_state.input_image.io.input_color_space = loaded.color_space
            gui_state.input_image.io.input_cctf_decoding = loaded.cctf_decoding

            return {
                'photo_id': photo_id,
                'path': path,
                'width': photo.width,
                'height': photo.height,
                'is_raw': photo.is_raw,
                'color_space': photo.color_space,
                'cctf_decoding': photo.cctf_decoding,
                'lens_summary': photo.lens_summary,
            'exif': exif_payload(photo.metadata),
                'original_preview': str(photo.original_preview_path),
                'display_preview': str(photo.display_preview_path),
                'state': self.state_dict(),
            }

    def photo_dict(self) -> dict[str, Any] | None:
        photo = self.state.photo
        if photo is None:
            return None
        return {
            'path': photo.path,
            'width': photo.width,
            'height': photo.height,
            'is_raw': photo.is_raw,
            'color_space': photo.color_space,
            'lens_summary': photo.lens_summary,
            'exif': exif_payload(photo.metadata),
        }

    # ── 预览 ────────────────────────────────────────────────
    def preview_fingerprint(self, scale: float) -> str:
        payload = {
            'state': self.state_dict(),
            'path': self.state.photo.path if self.state.photo else '',
            'scale': float(scale),
        }
        encoded = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha1(encoded.encode('utf-8')).hexdigest()

    def cancel_preview(self) -> None:
        self.queue.cancel_kind('preview')
        self.queue.cancel_kind('preview_fast')

    def submit_preview(self, scale: float) -> Job:
        return self.queue.submit(
            'preview',
            lambda job: self.run_preview(scale, job),
            supersede_kind='preview',
            initial_label='切换中…',
        )

    def run_preview(self, scale: float, job: Job) -> dict[str, Any]:
        photo = self.state.photo
        if photo is None:
            raise RuntimeError('请先载入一张输入图像')
        fingerprint = self.preview_fingerprint(scale)
        cached = self.state.last_preview
        if cached is not None and cached.fingerprint == fingerprint and cached.path.exists():
            return self._preview_payload(cached)

        self.queue.update_progress(job, '准备预览', 0, 1)
        long_edge = max(int(photo.image.shape[0]), int(photo.image.shape[1]))
        target_edge = min(max(1, int(round(long_edge * float(scale)))), develop.PREVIEW_MAX_EDGE)
        source = photo.preview_cache.get(target_edge)
        if source is None:
            source = develop.preview_source(np.double(photo.image), scale)
            photo.preview_cache[target_edge] = source
        output, output_color_space, _, elapsed_ms, timings = self._simulate(source, job)
        if self.queue.is_cancelled(job):
            raise JobCancelled('预览已被更新的请求取代')

        rgb = develop.output_to_display_rgb(output, output_color_space)
        target = paths.preview_dir() / f'{fingerprint[:16]}.png'
        develop.save_display_png(target, rgb)
        result = PreviewResult(
            fingerprint=fingerprint,
            path=target,
            width=int(rgb.shape[1]),
            height=int(rgb.shape[0]),
            output_color_space=output_color_space,
            elapsed_ms=elapsed_ms,
            timings=timings,
            status='',
        )
        self.state.last_preview = result
        return self._preview_payload(result)

    def _preview_payload(self, result: PreviewResult, *, predicted: bool = False) -> dict[str, Any]:
        return {
            'image_path': str(result.path),
            'width': result.width,
            'height': result.height,
            'output_color_space': result.output_color_space,
            'elapsed_ms': result.elapsed_ms,
            'timings': result.timings,
            'status': result.status,
            'fingerprint': result.fingerprint,
            'predicted': predicted,
        }

    # ── 全尺寸 ──────────────────────────────────────────────
    # ── LUT 预测预览（P2 服务接线） ────────────────────────
    def submit_fast_preview(self, scale: float) -> Job:
        return self.queue.submit(
            'preview_fast',
            lambda job: self.run_fast_preview(scale, job),
            supersede_kind='preview_fast',
            initial_label='预测中…',
        )

    def run_fast_preview(self, scale: float, job: Job) -> dict[str, Any]:
        photo = self.state.photo
        if photo is None:
            raise RuntimeError('请先载入一张输入图像')
        fingerprint = self.preview_fingerprint(scale) + ':lut'
        cached = photo.last_fast_preview
        if cached is not None and cached.fingerprint == fingerprint and cached.path.exists():
            return self._preview_payload(cached, predicted=True)

        self.queue.update_progress(job, '预测预览', 0, 1)
        start = time.perf_counter()
        long_edge = max(int(photo.image.shape[0]), int(photo.image.shape[1]))
        target_edge = min(max(1, int(round(long_edge * float(scale)))), develop.PREVIEW_MAX_EDGE)
        source = photo.preview_cache.get(target_edge)
        if source is None:
            source = develop.preview_source(np.double(photo.image), scale)
            photo.preview_cache[target_edge] = source

        bundle = self.lut_cache.get(self.state.gui_state)
        if self.queue.is_cancelled(job):
            raise JobCancelled('预测预览已被更新的请求取代')

        params = build_params_from_state(self.state.gui_state)
        auto_ev = 0.0
        if params.camera.auto_exposure:
            ev_key = (target_edge, str(params.camera.auto_exposure_method))
            auto_ev = photo.auto_ev_cache.get(ev_key)
            if auto_ev is None:
                auto_ev = lut_preview.measure_auto_ev(
                    source,
                    params.io.input_color_space,
                    params.io.input_cctf_decoding,
                    method=params.camera.auto_exposure_method,
                )
                photo.auto_ev_cache[ev_key] = auto_ev

        linear = bundle.predict(
            source,
            auto_ev=auto_ev,
            exposure_ev=float(params.camera.exposure_compensation_ev),
            print_exposure=float(params.enlarger.print_exposure),
            compensate=bool(self.state.gui_state.simulation.enlarger.print_exposure_compensation),
        )
        rgb = lut_preview.to_display_rgb8(linear)
        target = paths.preview_dir() / f'fast-{fingerprint[:16]}.jpg'
        develop.save_image_oiio(
            str(target),
            rgb.astype(np.float32) / 255.0,
            bit_depth=8,
            color_space='sRGB',
            cctf_encoding=True,
        )
        elapsed_ms = int(round((time.perf_counter() - start) * 1000))
        result = PreviewResult(
            fingerprint=fingerprint,
            path=target,
            width=int(rgb.shape[1]),
            height=int(rgb.shape[0]),
            output_color_space='sRGB',
            elapsed_ms=elapsed_ms,
            timings={},
            status='predicted',
        )
        photo.last_fast_preview = result
        return self._preview_payload(result, predicted=True)
    # ── 精度预检（P3） ─────────────────────────────────────
    def preflight(self, edge: int = 256) -> dict[str, Any]:
        photo = self.state.photo
        if photo is None:
            raise RuntimeError('请先载入一张输入图像')

        long_edge = max(int(photo.image.shape[0]), int(photo.image.shape[1]))
        scale = min(1.0, float(edge) / max(1, long_edge))
        source = develop.preview_source(np.double(photo.image), scale)

        params = build_params_from_state(self.state.gui_state)
        auto_ev = 0.0
        if params.camera.auto_exposure:
            auto_ev = lut_preview.measure_auto_ev(
                source,
                params.io.input_color_space,
                params.io.input_cctf_decoding,
                method=params.camera.auto_exposure_method,
            )

        with SIMULATION_LOCK:
            bundle = self.lut_cache.get(self.state.gui_state)
            predicted = bundle.predict(
                source,
                auto_ev=auto_ev,
                exposure_ev=float(params.camera.exposure_compensation_ev),
                print_exposure=float(params.enlarger.print_exposure),
                compensate=bool(
                    self.state.gui_state.simulation.enlarger.print_exposure_compensation
                ),
            )
            deterministic = self._render_compare(source, deterministic=True)
            full = self._render_compare(source, deterministic=False)

        model = _delta_e_stats(deterministic, predicted)
        effects = _delta_e_stats(full, deterministic)
        ok = model['max'] <= 2.0 and model['p99'] <= 1.0
        warning = ''
        if not ok:
            warning = '预测预览与精算结果存在可见差异，交付一律按精算结果。'
        return {
            'edge': int(min(edge, develop.PREVIEW_MAX_EDGE)),
            'model': model,
            'effects': effects,
            'thresholds': {'max': 2.0, 'p99': 1.0},
            'ok': bool(ok),
            'warning': warning,
        }

    def _render_compare(self, source: np.ndarray, *, deterministic: bool) -> np.ndarray:
        params = build_params_from_state(self.state.gui_state)
        params.io.output_color_space = 'ProPhoto RGB'
        params.io.output_cctf_encoding = False
        if deterministic:
            params.debug.deactivate_spatial_effects = True
            params.debug.deactivate_stochastic_effects = True
            params.film_render.halation.boost_ev = 0.0
            params.scanner.white_correction = False
            params.scanner.black_correction = False
            params.scanner.unsharp_mask = (0.0, 0.0)
        simulator = Simulator(digest_params(params))
        return np.asarray(simulator.process(np.double(source)), dtype=np.float32)
    def _simulate(
        self,
        image: np.ndarray,
        job: Job,
        *,
        output_cctf_encoding: bool | None = None,
    ) -> tuple[np.ndarray, str, bool, int, dict[str, float]]:
        params = build_params_from_state(self.state.gui_state)
        params.settings.preview_mode = False
        if output_cctf_encoding is not None:
            params.io.output_cctf_encoding = bool(output_cctf_encoding)
        output_color_space = str(params.io.output_color_space or 'sRGB')
        cctf_encoding = bool(params.io.output_cctf_encoding)

        def progress(label: str, index: int, total: int) -> None:
            self.queue.update_progress(job, label, index, total)

        with SIMULATION_LOCK:
            digested = digest_params(params)
            if self.state.simulator is None:
                self.state.simulator = Simulator(digested)
            else:
                self.state.simulator.update_params(digested)
            output = self.state.simulator.process(
                image,
                progress_callback=progress,
                cancel_callback=lambda: self.queue.is_cancelled(job),
            )
            elapsed_ms = int(round(self.state.simulator.get_total_elapsed_time() * 1000))
            timings = dict(self.state.simulator.get_timings())
        return np.asarray(output), output_color_space, cctf_encoding, elapsed_ms, timings

    def render_full(self, job: Job, *, output_cctf_encoding: bool | None = None) -> FullRender:
        photo = self.state.photo
        if photo is None:
            raise RuntimeError('请先载入一张输入图像')
        cctf_key = '' if output_cctf_encoding is None else ':linear'
        fingerprint = self.preview_fingerprint(1.0) + cctf_key
        cached = photo.last_full_render
        if cached is not None and cached.fingerprint == fingerprint:
            return cached

        self.queue.update_progress(job, '准备全尺寸', 0, 1)
        output, output_color_space, cctf_encoding, _, _ = self._simulate(
            np.double(photo.image),
            job,
            output_cctf_encoding=output_cctf_encoding,
        )
        result = FullRender(
            fingerprint=fingerprint,
            image=np.asarray(output),
            output_color_space=output_color_space,
            cctf_encoding=cctf_encoding,
        )
        photo.last_full_render = result
        return result

    # ── 导出 ────────────────────────────────────────────────
    def submit_export(self, settings: dict[str, Any] | None) -> Job:
        # 全尺寸导出优先：先把预览让出来，避免在 11 秒的显影阶段后面干等。
        self.queue.cancel_kind('preview')
        return self.queue.submit('export', lambda job: self.run_export(job, ExportSettings.from_dict(settings)))

    def run_export(self, job: Job, settings: ExportSettings) -> dict[str, Any]:
        photo = self.state.photo
        if photo is None:
            raise RuntimeError('请先载入一张输入图像')
        full = self.render_full(job)
        state = self.state.gui_state
        saving_color_space = str(state.simulation.workflow.saving_color_space or 'sRGB')
        saving_cctf = bool(state.simulation.workflow.saving_cctf_encoding)
        data = develop.convert_to_saving_space(
            full.image,
            source_color_space=full.output_color_space,
            source_cctf_encoding=full.cctf_encoding,
            saving_color_space=saving_color_space,
            saving_cctf_encoding=saving_cctf,
        )
        target = develop.export_image(
            data,
            settings,
            color_space=saving_color_space,
            cctf_encoding=saving_cctf,
            source_path=photo.path,
            film_stock=str(state.simulation.selection.film_stock or ''),
            print_paper=str(state.simulation.selection.print_paper or ''),
            metadata=photo.metadata,
        )
        return {
            'path': str(target),
            'color_space': saving_color_space,
            'cctf_encoding': saving_cctf,
        }

    # ── 交接图 ──────────────────────────────────────────────
    def submit_handoff(self) -> Job:
        self.queue.cancel_kind('preview')
        return self.queue.submit('handoff', lambda job: self.run_handoff(job))

    def run_handoff(self, job: Job) -> dict[str, Any]:
        from spektrafilm_gui.handoff import handoff_path

        photo = self.state.photo
        if photo is None:
            raise RuntimeError('请先载入一张输入图像')
        full = self.render_full(job, output_cctf_encoding=False)
        if self.item_id:
            target = handoff_path(self.item_id)
        else:
            target = paths.handoff_dir() / 'handoff.tif'
        target.parent.mkdir(parents=True, exist_ok=True)
        develop.write_handoff(target, full.image, full.output_color_space)
        return {
            'path': str(target),
            'bytes': int(target.stat().st_size),
            'color_space': develop.HANDOFF_COLOR_SPACE,
            'width': int(full.image.shape[1]),
            'height': int(full.image.shape[0]),
            'source_color_space': full.output_color_space,
        }


__all__ = ['PhotoSession', 'PreviewResult', 'ServiceSession', 'SessionState']
