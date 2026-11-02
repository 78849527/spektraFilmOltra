from __future__ import annotations

import hashlib
import json
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import numpy as np
from qtpy import QtCore, QtWidgets

from spektrafilm_gui.i18n import tr
from spektrafilm_gui import controller_persistence as persistence_actions
from spektrafilm_gui import controller_profile_sync as profile_sync
from spektrafilm_gui import controller_runtime as runtime
from spektrafilm_gui.input_color import detect_input_color_space
from spektrafilm_gui.library_store import RAW_SUFFIXES
from spektrafilm_gui.export_settings import ExportSettings, load_export_settings, save_export_settings
from spektrafilm_gui.controller_layers import (
    INPUT_LAYER_NAME,
    INPUT_PREVIEW_LAYER_NAME,
    ViewerLayerService,
)
from spektrafilm_gui.persistence import (
    clear_saved_default_gui_state,
    gui_state_to_dict,
    load_dialog_dir,
    load_gui_state_from_path,
    save_default_gui_state,
    save_dialog_dir,
    save_gui_state_to_path,
)
from spektrafilm_gui.state import PROJECT_DEFAULT_GUI_STATE, digest_after_selection, gui_state_from_params
from spektrafilm_gui.napari_layout import dialog_parent, reset_viewer_camera, set_canvas_background, set_status
from spektrafilm_gui.params_mapper import build_params_from_state
from spektrafilm_gui.state_bridge import apply_gui_state, collect_gui_state
from spektrafilm_gui.widgets import WidgetBundle

OUTPUT_FLOAT_DATA_KEY = 'pipeline_float_output'
OUTPUT_COLOR_SPACE_KEY = 'pipeline_output_color_space'
OUTPUT_CCTF_ENCODING_KEY = 'pipeline_output_cctf_encoding'
OUTPUT_DISPLAY_TRANSFORM_KEY = 'pipeline_use_display_transform'
PROFILE_SYNC_SECTION_NAMES = profile_sync.PROFILE_SYNC_SECTION_NAMES
if TYPE_CHECKING:
    import napari
    from napari.layers import Image as NapariImageLayer


QThreadPool = getattr(QtCore, 'QThreadPool')
QTimer = getattr(QtCore, 'QTimer')
QFileDialog = QtWidgets.QFileDialog
QMessageBox = QtWidgets.QMessageBox
SimulationRequest = runtime.SimulationRequest
SimulationResult = runtime.SimulationResult
STARTUP_PREVIEW_ASPECT_RATIO = (3, 2)
DISPLAY_PREVIEW_MAX_SIZE = 1600
PREVIEW_SIMULATION_MAX_EDGE = 1920
PREVIEW_DEBOUNCE_MS = 120
PREVIEW_RENDER_SCALES = (1.0, 0.5, 0.25)


def _sanitize_filename(name: str) -> str:
    for character in ('/', '\\', ':', '*', '?', '"', '<', '>', '|', '\n', '\r', '\t'):
        name = name.replace(character, '_')
    return name.strip().strip('.')


class _DirMemoryDialog:
    """Wraps QFileDialog to open in the last-used directory via QSettings."""

    def __init__(self, key: str) -> None:
        self._key = key

    def get_save_file_name(self, parent, title, filename, file_filter):
        last_dir = load_dialog_dir(self._key)
        initial = str(Path(last_dir) / Path(filename).name) if last_dir else filename
        path, fmt = QFileDialog.getSaveFileName(parent, title, initial, file_filter)
        if path:
            save_dialog_dir(self._key, str(Path(path).parent))
        return path, fmt

    def get_open_file_name(self, parent, title, _initial, file_filter):
        path, fmt = QFileDialog.getOpenFileName(
            parent, title, load_dialog_dir(self._key), file_filter
        )
        if path:
            save_dialog_dir(self._key, str(Path(path).parent))
        return path, fmt


class _LazyModuleProxy:
    def __init__(self, loader):
        self._loader = loader
        self._module = None

    def _load(self):
        if self._module is None:
            self._module = self._loader()
        return self._module

    def __getattr__(self, name: str):
        return getattr(self._load(), name)


def _import_colour_module():
    return import_module('colour')


def _import_pil_image_module():
    return import_module('PIL.Image')


def _import_imagecms_module():
    return import_module('PIL.ImageCms')


def runtime_simulator(*args, **kwargs):
    return import_module('spektrafilm.runtime.api').Simulator(*args, **kwargs)


def digest_params(*args, **kwargs):
    return import_module('spektrafilm.runtime.api').digest_params(*args, **kwargs)


def load_image_oiio(*args, **kwargs):
    return import_module('spektrafilm.utils.io').load_image_oiio(*args, **kwargs)


def save_image_oiio(*args, **kwargs):
    return import_module("spektrafilm.utils.io").save_image_oiio(*args, **kwargs)


def read_image_metadata(*args, **kwargs):
    return import_module("spektrafilm.utils.io").read_image_metadata(*args, **kwargs)


def write_image_metadata(*args, **kwargs):
    return import_module("spektrafilm.utils.io").write_image_metadata(*args, **kwargs)


def load_and_process_raw_file(*args, **kwargs):
    return import_module('spektrafilm.utils.raw_file_processor').load_and_process_raw_file(*args, **kwargs)


def resize_for_preview(*args, **kwargs):
    return import_module('spektrafilm.utils.preview').resize_for_preview(*args, **kwargs)


colour = _LazyModuleProxy(_import_colour_module)
PILImage = _LazyModuleProxy(_import_pil_image_module)
ImageCms = _LazyModuleProxy(_import_imagecms_module)


class GuiController:
    def __init__(self, *, viewer: napari.Viewer, widgets: WidgetBundle):
        self._viewer = viewer
        self._widgets = widgets
        self._layers = ViewerLayerService(
            viewer=viewer,
            output_float_data_key=OUTPUT_FLOAT_DATA_KEY,
            output_color_space_key=OUTPUT_COLOR_SPACE_KEY,
            output_cctf_encoding_key=OUTPUT_CCTF_ENCODING_KEY,
            output_display_transform_key=OUTPUT_DISPLAY_TRANSFORM_KEY,
        )
        self._thread_pool = QThreadPool.globalInstance()
        self._active_simulation_worker: runtime.SimulationWorker | None = None
        self._active_simulation_label: str | None = None
        self._runtime_simulator = None
        self._next_runtime_digest_applies_stock_specifics = True
        self._current_input_image: np.ndarray | None = None
        self._current_input_path: str | None = None
        self._current_preview_image: np.ndarray | None = None
        self._last_input_was_rgb = False
        self._preview_render_scale = 0.5
        self._preview_scale_cache: dict[float, np.ndarray] = {}
        self._preview_generation = 0
        self._last_preview_fingerprint: object | None = None
        self._pending_preview_fingerprint: object | None = None
        self._auto_preview_scheduled = False
        self._pending_auto_preview = False
        self._active_simulation_reports_status = True
        self._simulation_finished_callbacks: list[Callable[[SimulationResult], None]] = []
        self._simulation_started_callbacks: list[Callable[[str, float], None]] = []
        self._simulation_progress_callbacks: list[Callable[[str, int, int], None]] = []
        self._simulation_failed_callbacks: list[Callable[[str], None]] = []
        self._export_after_scan = False
        self._export_pending_after_simulation = False
        self._export_settings = load_export_settings()

    def show_startup_placeholder(self) -> None:
        if self._white_border_layer() is not None:
            return

        state = collect_gui_state(widgets=self._widgets)
        preview_height = max(int(state.gui_only.display.settings.preview_max_size), 1)
        preview_width = max(
            int(round(preview_height * STARTUP_PREVIEW_ASPECT_RATIO[1] / STARTUP_PREVIEW_ASPECT_RATIO[0])),
            1,
        )
        placeholder_preview = np.zeros((preview_height, preview_width, 3), dtype=np.uint8)
        self._layers.set_or_add_input_preview_layer(
            placeholder_preview,
            watermark_source_size=(preview_height, preview_width),
            white_padding=state.gui_only.display.white_padding,
            hide_output=True,
            set_active=True,
        )
        self._home_input_stack()

    def load_input_image(self, path: str) -> None:
        if Path(path).suffix.lower() in RAW_SUFFIXES:
            self.load_raw_image(path)
            return
        color_space, decode = detect_input_color_space(path)
        self._apply_input_color_space(color_space, decode)
        self._last_input_was_rgb = True
        load_raw = getattr(self._widgets, 'load_raw', None)
        set_path = getattr(load_raw, 'set_path', None)
        if callable(set_path):
            set_path('')
        image = load_image_oiio(path)[..., :3]
        self._current_input_path = path
        self._set_or_add_input_stack(image)
        self._request_auto_preview_if_enabled()

    def _apply_input_color_space(self, color_space: str, decode: bool) -> None:
        holders = getattr(self._widgets, 'input_image', None)
        if holders is None:
            return
        editors = getattr(holders, '_editors', None) or {}
        for leaf, value in (
            ('input_color_space', color_space),
            ('input_cctf_decoding', bool(decode)),
        ):
            editor = editors.get(leaf)
            if editor is None:
                continue
            try:
                editor.value = value
            except (AttributeError, TypeError, ValueError):
                continue

    def handle_dropped_paths(self, paths: list[str]) -> None:
        """拖放导入：按扩展名分流到 RAW 或普通图像载入。"""
        if not paths:
            return
        path = paths[0]
        if Path(path).suffix.lower() in RAW_SUFFIXES:
            self.load_raw_image(path)
        else:
            self.load_input_image(path)

    def load_raw_image(self, path: str) -> None:
        # 只有 RAW 后缀才允许进 rawpy；PNG/JPEG 等交给普通图像载入，
        # 避免把编码图像塞进 LibRaw 导致进程崩溃。
        if Path(path).suffix.lower() not in RAW_SUFFIXES:
            self.load_input_image(path)
            return
        # RAW 解码到线性 ProPhoto；如果上一张是普通 RGB 图，先恢复 RAW 的线性默认值。
        if self._last_input_was_rgb:
            self._apply_input_color_space('ProPhoto RGB', False)
        self._last_input_was_rgb = False
        load_raw = getattr(self._widgets, 'load_raw', None)
        set_path = getattr(load_raw, 'set_path', None)
        if callable(set_path):
            set_path(path)
        gui_state = collect_gui_state(widgets=self._widgets)
        set_status(self._viewer, "正在载入 RAW…", timeout_ms=0)
        lens_info: dict[str, str] = {}
        try:
            image = load_and_process_raw_file(
                path,
                white_balance=gui_state.gui_only.load_raw.white_balance,
                temperature=gui_state.gui_only.load_raw.temperature,
                tint=gui_state.gui_only.load_raw.tint,
                lens_correction=gui_state.gui_only.load_raw.lens_correction,
                output_colorspace=gui_state.input_image.io.input_color_space,
                output_cctf_encoding=gui_state.input_image.io.input_cctf_decoding,
                lens_info_out=lens_info,
            )
        except Exception as exc:
            QMessageBox.critical(dialog_parent(self._viewer), '载入 RAW', f'RAW 图像载入失败。\n\n{exc}')
            set_status(self._viewer, 'RAW 载入失败')
            return

        self._current_input_path = path
        self._set_or_add_input_stack(image)

        lens_summary = lens_info.get('summary')
        if lens_summary:
            set_status(
                self._viewer,
                f"已载入 RAW，并应用镜头校正：{lens_summary}",
            )
        elif gui_state.gui_only.load_raw.lens_correction:
            set_status(self._viewer, "已载入 RAW，未应用镜头校正")
        else:
            set_status(self._viewer, "已载入 RAW")
        self._request_auto_preview_if_enabled()

    def refresh_preview_cache(self, *_args) -> None:
        input_image = self._current_input_image
        if input_image is None:
            return
        self._update_preview_cache(
            input_image,
            home_input_stack=False,
            hide_output=False,
        )

    def rotate_input_image_clockwise(self) -> None:
        self._rotate_input_image(quarter_turns=-1)

    def rotate_input_image_counterclockwise(self) -> None:
        self._rotate_input_image(quarter_turns=1)

    def _rotate_input_image(self, *, quarter_turns: int) -> None:
        input_image = self._current_input_image
        if input_image is None:
            return

        rotated_image = np.rot90(np.asarray(input_image), k=int(quarter_turns))
        self._update_preview_cache(
            rotated_image,
            home_input_stack=True,
            hide_output=True,
        )
        self._request_auto_preview_if_enabled()

    def apply_profile_defaults(self, _selected_value: str) -> None:
        state = collect_gui_state(widgets=self._widgets)
        if not state.selection.film_stock or not state.selection.print_paper:
            return

        params = build_params_from_state(state)
        synced_state = gui_state_from_params(
            digest_after_selection(params),
            film_stock=state.selection.film_stock,
            print_paper=state.selection.print_paper,
        )
        # 换胶片/相纸只同步物理默认值，不重置用户的通道互换、自动预览与保存偏好。
        current_special = getattr(state, 'special', None)
        synced_special = getattr(synced_state, 'special', None)
        if current_special is not None and synced_special is not None:
            synced_special.film_channel_swap = current_special.film_channel_swap
            synced_special.print_channel_swap = current_special.print_channel_swap
        current_workflow = getattr(getattr(state, 'simulation', None), 'workflow', None)
        synced_workflow = getattr(getattr(synced_state, 'simulation', None), 'workflow', None)
        if current_workflow is not None and synced_workflow is not None:
            synced_workflow.auto_preview = current_workflow.auto_preview
            synced_workflow.saving_color_space = current_workflow.saving_color_space
            synced_workflow.saving_cctf_encoding = current_workflow.saving_cctf_encoding
        self._apply_profile_sync_state(synced_state)
        self._next_runtime_digest_applies_stock_specifics = True

    def apply_film_profile_defaults(self, film_stock: str) -> None:
        self.apply_profile_defaults(film_stock)

    def _apply_profile_sync_state(self, synced_state) -> None:
        profile_sync.apply_profile_sync_state(
            widgets=self._widgets,
            synced_state=synced_state,
            profile_sync_section_names=PROFILE_SYNC_SECTION_NAMES,
        )

    def run_preview(self) -> None:
        self._run_preview(report_status=True)

    def _run_preview(self, *, report_status: bool) -> None:
        self._start_simulation(
            source_layer_name=INPUT_PREVIEW_LAYER_NAME,
            mode_label='Preview',
            report_status=report_status,
        )

    def run_scan(self) -> None:
        self._start_simulation(source_layer_name=INPUT_LAYER_NAME, mode_label='Scan')

    def is_simulating(self) -> bool:
        return self._active_simulation_worker is not None

    def add_simulation_finished_callback(self, callback: Callable[[SimulationResult], None]) -> None:
        """只增加一个“算完了”的展示回调，不改动模拟调度与参数。"""
        if callback not in self._simulation_finished_callbacks:
            self._simulation_finished_callbacks.append(callback)

    def add_simulation_started_callback(self, callback: Callable[[str, float], None]) -> None:
        if callback not in self._simulation_started_callbacks:
            self._simulation_started_callbacks.append(callback)

    def add_simulation_progress_callback(self, callback: Callable[[str, int, int], None]) -> None:
        if callback not in self._simulation_progress_callbacks:
            self._simulation_progress_callbacks.append(callback)

    def add_simulation_failed_callback(self, callback: Callable[[str], None]) -> None:
        if callback not in self._simulation_failed_callbacks:
            self._simulation_failed_callbacks.append(callback)

    def current_output_display_image(self) -> np.ndarray | None:
        layer = self._output_layer()
        if layer is None:
            return None
        data = getattr(layer, 'data', None)
        if data is None:
            return None
        return np.asarray(data)

    def current_input_size(self) -> tuple[int, int] | None:
        image = self._current_input_image
        if image is None:
            return None
        shape = getattr(image, 'shape', None)
        if not shape or len(shape) < 2:
            return None
        return int(shape[1]), int(shape[0])

    def request_export(self) -> None:
        """一键导出：正在渲染时排队，渲染完成后自动导出全尺寸。"""
        if self._active_simulation_worker is not None:
            self._export_pending_after_simulation = True
            set_status(self._viewer, '已排队，当前渲染完成后自动导出')
            return
        self._export_pending_after_simulation = False
        self._export_after_scan = True
        self.run_scan()
        if self._active_simulation_worker is None:
            self._export_after_scan = False

    def request_auto_preview(self, *_args) -> None:
        if self._auto_preview_scheduled:
            return
        self._auto_preview_scheduled = True
        QTimer.singleShot(PREVIEW_DEBOUNCE_MS, self._run_scheduled_auto_preview)

    def _request_auto_preview_if_enabled(self) -> None:
        if not self._auto_preview_enabled() or self._current_preview_image is None:
            return
        self.request_auto_preview()

    def report_display_transform_status(self, enabled: bool) -> None:
        if enabled and not self.sync_display_transform_availability(report_status=True):
            return
        set_status(self._viewer, runtime.display_transform_status_message(enabled, imagecms_module=ImageCms))

    def set_gray_18_canvas_enabled(self, enabled: bool) -> None:
        set_canvas_background(self._viewer, gray_18_canvas=enabled)

    def set_output_interpolation_mode(self, mode: str) -> None:
        output_layer = self._output_layer()
        if output_layer is None:
            return
        self._layers.set_output_layer_interpolation(output_layer, mode)

    def sync_display_transform_availability(self, *, report_status: bool) -> bool:
        if runtime.display_profile_available(imagecms_module=ImageCms):
            return True

        self._set_display_transform_checked(False)
        if report_status:
            set_status(self._viewer, '未检测到显示器色彩描述文件，显示变换已关闭')
        return False

    def export_settings(self) -> ExportSettings:
        return self._export_settings.normalized()

    def set_export_settings(self, settings: ExportSettings) -> None:
        self._export_settings = settings.normalized()
        save_export_settings(self._export_settings)

    def _export_image_payload(self) -> tuple[np.ndarray, str, bool, object] | None:
        output_layer = self._output_layer()
        if output_layer is None:
            return None
        gui_state = collect_gui_state(widgets=self._widgets)
        float_image_data = self._output_layer_float_data()
        if float_image_data is None:
            image_data = runtime.normalized_image_data(np.asarray(output_layer.data)[..., :3])
        else:
            image_data = np.asarray(float_image_data)[..., :3]

        source_color_space, source_cctf_encoding = self._output_layer_render_settings(
            default_color_space=gui_state.simulation.io.output_color_space,
            default_cctf_encoding=True,
        )
        saving_color_space = gui_state.simulation.workflow.saving_color_space
        saving_cctf_encoding = gui_state.simulation.workflow.saving_cctf_encoding
        if source_color_space != saving_color_space or source_cctf_encoding != saving_cctf_encoding:
            image_data = colour.RGB_to_RGB(
                image_data,
                source_color_space,
                saving_color_space,
                apply_cctf_decoding=source_cctf_encoding,
                apply_cctf_encoding=saving_cctf_encoding,
            )

        source_metadata = None
        if self._current_input_path is not None:
            try:
                source_metadata = read_image_metadata(self._current_input_path)
            except Exception:
                source_metadata = None
        return image_data, saving_color_space, saving_cctf_encoding, source_metadata

    def export_now(self) -> None:
        """直接导出：使用当前导出设置，不弹保存对话框。"""
        if self._output_layer() is None:
            QMessageBox.warning(dialog_parent(self._viewer), '导出', '请先运行一次模拟，再导出。')
            return
        if self._active_simulation_worker is not None:
            set_status(self._viewer, '模拟正在运行中，请稍候')
            return

        payload = self._export_image_payload()
        if payload is None:
            return
        image_data, color_space, cctf_encoding, source_metadata = payload
        settings = self._export_settings.normalized()
        if settings.long_edge > 0 and max(image_data.shape[:2]) > settings.long_edge:
            image_data = self._resize_for_preview(image_data, max_size=settings.long_edge)

        try:
            filepath = self._export_target_path(settings)
        except OSError as exc:
            QMessageBox.critical(dialog_parent(self._viewer), '导出', f'导出目录不可用。\n\n{exc}')
            return

        try:
            self._save_with_settings(
                filepath,
                image_data,
                settings,
                color_space=color_space,
                cctf_encoding=cctf_encoding,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(dialog_parent(self._viewer), '导出', f'导出失败。\n\n{exc}')
            return

        metadata_error = self._write_export_metadata(
            filepath,
            source_metadata,
            color_space=color_space,
            cctf_encoding=cctf_encoding,
        )
        if metadata_error is not None:
            set_status(self._viewer, f'已导出到 {filepath}，但元数据复制失败：{metadata_error}')
        else:
            set_status(self._viewer, f'已导出到 {filepath}')

    def _save_with_settings(
        self,
        filepath: Path,
        image_data: np.ndarray,
        settings: ExportSettings,
        *,
        color_space: str,
        cctf_encoding: bool,
    ) -> None:
        suffix = filepath.suffix.lower()
        bit_depth = 16
        quality = None
        compression = None
        if suffix in {'.tif', '.tiff'}:
            bit_depth = settings.bit_depth if settings.bit_depth in {8, 16, 32} else 16
            compression = settings.tiff_compression
        elif suffix == '.exr':
            bit_depth = settings.bit_depth if settings.bit_depth in {16, 32} else 16
            compression = settings.exr_compression
        elif suffix == '.png':
            compression = settings.png_compression
        elif suffix in {'.jpg', '.jpeg'}:
            quality = settings.jpeg_quality
        save_image_oiio(
            str(filepath),
            image_data,
            bit_depth=bit_depth,
            color_space=color_space,
            cctf_encoding=cctf_encoding,
            quality=quality,
            compression=compression,
        )

    def _write_export_metadata(
        self,
        filepath: Path,
        source_metadata: object,
        *,
        color_space: str,
        cctf_encoding: bool,
    ) -> Exception | None:
        try:
            write_image_metadata(
                str(filepath),
                source_metadata,
                saving_color_space=color_space,
                saving_cctf_encoding=cctf_encoding,
            )
            return None
        except Exception as exc:
            return exc

    def _export_target_path(self, settings: ExportSettings) -> Path:
        source = Path(self._current_input_path) if self._current_input_path is not None else None
        if settings.directory:
            directory = Path(settings.directory).expanduser()
        elif source is not None:
            directory = source.parent
        else:
            directory = Path.home() / 'Pictures'
        directory.mkdir(parents=True, exist_ok=True)

        gui_state = collect_gui_state(widgets=self._widgets)
        values = {
            'name': source.stem if source is not None else 'output',
            'film': str(gui_state.simulation.selection.film_stock or ''),
            'paper': str(gui_state.simulation.selection.print_paper or ''),
        }
        try:
            stem = settings.filename_template.format(**values)
        except (KeyError, ValueError):
            stem = f"{values['name']}_spektrafilm"
        stem = _sanitize_filename(stem) or f"{values['name']}_spektrafilm"

        path = directory / f'{stem}.{settings.extension}'
        if not path.exists():
            return path
        for index in range(1, 1000):
            candidate = path.with_name(f'{path.stem}-{index}{path.suffix}')
            if not candidate.exists():
                return candidate
        return path

    def save_output_layer(self) -> None:
        output_layer = self._output_layer()
        if output_layer is None:
            QMessageBox.warning(dialog_parent(self._viewer), '保存输出', '请先运行一次模拟，再保存输出图层。')
            return

        if self._current_input_path is not None:
            default_name = Path(self._current_input_path).stem + f'.{self._export_settings.extension}'
        else:
            default_name = f'output.{self._export_settings.extension}'

        filepath, _ = _DirMemoryDialog('save_output').get_save_file_name(
            dialog_parent(self._viewer),
            '保存输出图像',
            default_name,
            '图像 (*.jpg *.jpeg *.png *.tif *.tiff *.exr)',
        )
        if not filepath:
            return

        payload = self._export_image_payload()
        if payload is None:
            return
        image_data, saving_color_space, saving_cctf_encoding, source_metadata = payload

        try:
            save_image_oiio(
                filepath,
                image_data,
                color_space=saving_color_space,
                cctf_encoding=saving_cctf_encoding,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(dialog_parent(self._viewer), '保存输出', f'输出图像保存失败。\n\n{exc}')
            return

        metadata_write_error = self._write_export_metadata(
            Path(filepath),
            source_metadata,
            color_space=saving_color_space,
            cctf_encoding=saving_cctf_encoding,
        )

        if metadata_write_error is not None:
            set_status(
                self._viewer,
                f"输出图像已保存到 {filepath}，但元数据复制失败：{metadata_write_error}",
            )
        else:
            set_status(self._viewer, f"输出图像已保存到 {filepath}")

    def save_current_as_default(self) -> None:
        persistence_actions.save_current_as_default(
            viewer=self._viewer,
            widgets=self._widgets,
            collect_gui_state_fn=collect_gui_state,
            save_default_gui_state_fn=save_default_gui_state,
            set_status_fn=set_status,
            dialog_parent_fn=dialog_parent,
            message_box=QMessageBox,
        )

    def save_current_state_to_file(self) -> None:
        persistence_actions.save_current_state_to_file(
            viewer=self._viewer,
            widgets=self._widgets,
            file_dialog=_DirMemoryDialog('gui_state'),
            collect_gui_state_fn=collect_gui_state,
            save_gui_state_to_path_fn=save_gui_state_to_path,
            set_status_fn=set_status,
            dialog_parent_fn=dialog_parent,
            message_box=QMessageBox,
        )

    def load_state_from_file(self) -> None:
        persistence_actions.load_state_from_file(
            viewer=self._viewer,
            widgets=self._widgets,
            file_dialog=_DirMemoryDialog('gui_state'),
            load_gui_state_from_path_fn=load_gui_state_from_path,
            apply_gui_state_fn=apply_gui_state,
            sync_canvas_background_fn=self._sync_canvas_background,
            set_status_fn=set_status,
            dialog_parent_fn=dialog_parent,
            message_box=QMessageBox,
        )

    def restore_factory_default(self) -> None:
        persistence_actions.restore_factory_default(
            viewer=self._viewer,
            widgets=self._widgets,
            project_default_gui_state=PROJECT_DEFAULT_GUI_STATE,
            clear_saved_default_gui_state_fn=clear_saved_default_gui_state,
            apply_gui_state_fn=apply_gui_state,
            sync_canvas_background_fn=self._sync_canvas_background,
            set_status_fn=set_status,
            dialog_parent_fn=dialog_parent,
            message_box=QMessageBox,
        )

    def _preview_input_layer(self) -> NapariImageLayer | None:
        return self._layers.preview_input_layer()

    def _white_border_layer(self) -> NapariImageLayer | None:
        return self._layers.white_border_layer()

    def _set_or_add_output_layer(
        self,
        image: np.ndarray,
        *,
        float_image: np.ndarray,
        output_color_space: str,
        output_cctf_encoding: bool,
        use_display_transform: bool,
    ) -> None:
        self._layers.set_or_add_output_layer(
            image,
            float_image=float_image,
            output_color_space=output_color_space,
            output_cctf_encoding=output_cctf_encoding,
            use_display_transform=use_display_transform,
            output_interpolation_mode=self._output_interpolation_mode(),
        )

    def _set_or_add_input_stack(
        self,
        image: np.ndarray,
    ) -> None:
        self._update_preview_cache(
            image,
            home_input_stack=True,
            hide_output=True,
        )

    def _update_preview_cache(
        self,
        image: np.ndarray,
        *,
        home_input_stack: bool,
        hide_output: bool,
    ) -> None:
        state = collect_gui_state(widgets=self._widgets)
        display_source = self._resize_for_preview(image, max_size=DISPLAY_PREVIEW_MAX_SIZE)
        preview_display_image = self._prepare_input_color_preview_image(
            display_source,
            input_color_space=state.input_image.io.input_color_space,
            apply_cctf_decoding=state.input_image.io.input_cctf_decoding,
        )
        self._current_input_image = image
        self._preview_scale_cache.clear()
        self._preview_generation += 1
        self._last_preview_fingerprint = None
        self._current_preview_image = self._scaled_preview_image()
        self._layers.set_or_add_input_preview_layer(
            preview_display_image,
            watermark_source_size=tuple(int(dimension) for dimension in image.shape[:2]),
            white_padding=state.gui_only.display.white_padding,
            hide_output=hide_output,
            set_active=home_input_stack or self._output_layer() is None,
        )
        if home_input_stack:
            self._home_input_stack()

    def _sync_white_border(self, *, white_padding: float) -> None:
        self._layers.sync_white_border(white_padding=white_padding)

    def _home_input_stack(self) -> None:
        if self._white_border_layer() is None:
            return
        reset_viewer_camera(self._viewer)
        self._set_active_layer(self._white_border_layer())

    def _scaled_preview_image(self) -> np.ndarray | None:
        image = self._current_input_image
        if image is None:
            return None
        scale = self._preview_render_scale
        height, width = image.shape[:2]
        long_edge = max(int(height), int(width))
        if scale >= 1.0 and long_edge <= PREVIEW_SIMULATION_MAX_EDGE:
            return image
        target = min(
            max(1, int(round(long_edge * scale))),
            PREVIEW_SIMULATION_MAX_EDGE,
        )
        cached = self._preview_scale_cache.get(target)
        if cached is not None:
            return cached
        scaled = self._resize_for_preview(image, max_size=target)
        self._preview_scale_cache[target] = scaled
        return scaled

    def set_preview_render_scale(self, scale: float) -> None:
        try:
            value = float(scale)
        except (TypeError, ValueError):
            return
        if value not in PREVIEW_RENDER_SCALES:
            value = 1.0
        changed = value != self._preview_render_scale
        self._preview_render_scale = value
        if changed:
            self._preview_generation += 1
            self._last_preview_fingerprint = None
        self._current_preview_image = self._scaled_preview_image()
        if changed and self._current_preview_image is not None:
            self.request_auto_preview()

    def preview_render_scale(self) -> float:
        return float(self._preview_render_scale)

    def _simulation_input_image(self, *, source_layer_name: str) -> np.ndarray | None:
        if source_layer_name == INPUT_PREVIEW_LAYER_NAME:
            scaled = self._scaled_preview_image()
            return scaled if scaled is not None else self._current_preview_image
        if source_layer_name == INPUT_LAYER_NAME:
            return self._current_input_image
        return None

    def _auto_preview_enabled(self) -> bool:
        simulation_section = getattr(self._widgets, 'simulation', None)
        auto_preview_value = getattr(simulation_section, 'auto_preview_value', None)
        return bool(auto_preview_value()) if callable(auto_preview_value) else False

    def _run_scheduled_auto_preview(self) -> None:
        self._auto_preview_scheduled = False
        if not self._auto_preview_enabled() or self._current_preview_image is None:
            self._pending_auto_preview = False
            return
        if self._active_simulation_worker is not None:
            self._pending_auto_preview = True
            return
        fingerprint = self._preview_fingerprint()
        if fingerprint is not None and fingerprint == self._last_preview_fingerprint:
            self._pending_auto_preview = False
            return
        self._pending_preview_fingerprint = fingerprint
        self._run_preview(report_status=True)

    def _preview_fingerprint(self) -> object | None:
        """当前预览输入 + GUI 状态的稳定指纹，用于跳过重复渲染。"""
        image = self._current_preview_image
        if image is None:
            return None
        try:
            state = collect_gui_state(widgets=self._widgets)
            payload = gui_state_to_dict(state)
            payload['selection'] = {
                'film_stock': str(getattr(state.selection, 'film_stock', '')),
                'print_paper': str(getattr(state.selection, 'print_paper', '')),
            }
            encoded = json.dumps(payload, sort_keys=True, default=str)
        except (AttributeError, TypeError, ValueError, KeyError):
            return None
        digest = hashlib.sha1(encoded.encode('utf-8')).hexdigest()
        return (self._preview_generation, digest)

    def _replay_pending_auto_preview(self) -> None:
        if not self._pending_auto_preview:
            return
        self._pending_auto_preview = False
        self.request_auto_preview()

    def _output_layer(self) -> NapariImageLayer | None:
        return self._layers.output_layer()

    def _set_active_layer(self, layer: NapariImageLayer | None) -> None:
        self._layers.set_active_layer(layer)

    def _output_layer_float_data(self) -> np.ndarray | None:
        output_layer = self._output_layer()
        if output_layer is None:
            return None
        float_data = output_layer.metadata.get(OUTPUT_FLOAT_DATA_KEY)
        if float_data is None:
            return None
        return np.asarray(float_data)

    def _output_layer_render_settings(
        self,
        *,
        default_color_space: str,
        default_cctf_encoding: bool,
    ) -> tuple[str, bool]:
        output_layer = self._output_layer()
        if output_layer is None:
            return default_color_space, default_cctf_encoding
        color_space = output_layer.metadata.get(OUTPUT_COLOR_SPACE_KEY, default_color_space)
        cctf_encoding = output_layer.metadata.get(OUTPUT_CCTF_ENCODING_KEY, default_cctf_encoding)
        return str(color_space), bool(cctf_encoding)

    def _output_interpolation_mode(self) -> str:
        display_section = getattr(self._widgets, 'display', None)
        editor = getattr(display_section, 'output_interpolation', None)
        value = getattr(editor, 'value', None)
        if isinstance(value, str) and value:
            return value
        current_text = getattr(editor, 'currentText', None)
        if callable(current_text):
            text = current_text()
            if isinstance(text, str) and text:
                return text
        return 'spline36'

    @staticmethod
    def _resize_for_preview(image_data: np.ndarray, *, max_size: int) -> np.ndarray:
        return resize_for_preview(image_data, max_size)

    @staticmethod
    def _prepare_input_color_preview_image(
        image_data: np.ndarray,
        *,
        input_color_space: str,
        apply_cctf_decoding: bool,
    ) -> np.ndarray:
        return runtime.prepare_input_color_preview_image(
            image_data,
            input_color_space=input_color_space,
            apply_cctf_decoding=apply_cctf_decoding,
            colour_module=colour,
        )

    @staticmethod
    def _prepare_output_display_image(
        image_data: np.ndarray,
        *,
        output_color_space: str,
        use_display_transform: bool,
        padding_pixels: float = 0.0,
    ) -> tuple[np.ndarray, str]:
        return runtime.prepare_output_display_image(
            image_data,
            output_color_space=output_color_space,
            use_display_transform=use_display_transform,
            padding_pixels=padding_pixels,
            imagecms_module=ImageCms,
            colour_module=colour,
            pil_image_module=PILImage,
        )

    def _process_image_with_runtime(self, image_data: np.ndarray, params, *, progress_callback=None) -> np.ndarray:
        from spektrafilm_gui.runtime_guard import SIMULATION_LOCK

        with SIMULATION_LOCK:
            apply_stocks_specifics = (
                self._runtime_simulator is None
                or self._next_runtime_digest_applies_stock_specifics
            )
            digested_params = digest_params(
                params,
                apply_stocks_specifics=apply_stocks_specifics,
            )
            try:
                if self._runtime_simulator is None:
                    self._runtime_simulator = runtime_simulator(digested_params)
                else:
                    self._runtime_simulator.update_params(digested_params)
                self._next_runtime_digest_applies_stock_specifics = False
                return self._runtime_simulator.process(image_data, progress_callback=progress_callback)
            except Exception:
                self._runtime_simulator = None
                raise

    def _set_display_transform_checked(self, enabled: bool) -> None:
        display_section = getattr(self._widgets, 'display', None)
        toggle = getattr(display_section, 'use_display_transform', None)
        if toggle is None:
            return

        block_signals = getattr(toggle, 'blockSignals', None)
        set_checked = getattr(toggle, 'setChecked', None)
        if not callable(set_checked):
            return

        previous_block_state = None
        if callable(block_signals):
            previous_block_state = block_signals(True)
        try:
            set_checked(enabled)
        finally:
            if callable(block_signals):
                block_signals(bool(previous_block_state))

    def _sync_canvas_background(self) -> None:
        display_section = getattr(self._widgets, 'display', None)
        toggle = getattr(display_section, 'gray_18_canvas', None)
        is_checked = getattr(toggle, 'isChecked', None)
        self.set_gray_18_canvas_enabled(bool(is_checked()) if callable(is_checked) else False)

    def _execute_simulation_request(self, request: SimulationRequest, *, progress_callback=None) -> SimulationResult:
        return runtime.execute_simulation_request(
            request,
            run_simulation_fn=self._process_image_with_runtime,
            prepare_output_display_image_fn=self._prepare_output_display_image,
            progress_callback=progress_callback,
        )

    @staticmethod
    def _configure_simulation_params(params, *, source_layer_name: str):
        # 预览与全尺寸走同一套物理参数：颗粒、柔化、锐化等都不再为预览让步。
        settings = getattr(params, 'settings', None)
        if settings is not None and hasattr(settings, 'preview_mode'):
            settings.preview_mode = False
        return params

    def _start_simulation(self, *, source_layer_name: str, mode_label: str, report_status: bool = True) -> None:
        if self._active_simulation_worker is not None:
            set_status(self._viewer, '模拟正在运行中')
            return

        image_data = self._simulation_input_image(source_layer_name=source_layer_name)
        if image_data is None:
            QMessageBox.warning(dialog_parent(self._viewer), '运行模拟', '请先载入一张输入图像，再运行模拟。')
            return

        state = collect_gui_state(widgets=self._widgets)
        self._sync_white_border(white_padding=state.gui_only.display.white_padding)
        params = self._configure_simulation_params(
            build_params_from_state(state),
            source_layer_name=source_layer_name,
        )

        image = np.double(image_data)
        request = SimulationRequest(
            mode_label=mode_label,
            image=image,
            params=params,
            output_color_space=state.simulation.io.output_color_space,
            use_display_transform=state.gui_only.display.use_display_transform,
        )

        worker = runtime.SimulationWorker(request, execute_request=self._execute_simulation_request)
        worker.signals.finished.connect(self._on_simulation_finished)
        worker.signals.failed.connect(self._on_simulation_failed)
        worker.signals.progress.connect(self._on_simulation_progress)
        self._active_simulation_worker = worker
        self._active_simulation_label = mode_label
        self._active_simulation_reports_status = report_status
        self._set_simulation_controls_enabled(False)
        scale = 1.0 if source_layer_name == INPUT_LAYER_NAME else self._preview_render_scale
        for callback in tuple(self._simulation_started_callbacks):
            try:
                callback(mode_label, scale)
            except (AttributeError, LookupError, RuntimeError, TypeError, ValueError):
                continue
        if report_status:
            set_status(self._viewer, f'正在计算{tr(mode_label)}…', timeout_ms=0)
        self._thread_pool.start(worker)

    def _on_simulation_progress(self, label: str, completed: int, total: int) -> None:
        for callback in tuple(self._simulation_progress_callbacks):
            try:
                callback(label, int(completed), int(total))
            except (AttributeError, LookupError, RuntimeError, TypeError, ValueError):
                continue

    def _result_is_full_size(self, result: SimulationResult) -> bool:
        image = self._current_input_image
        if image is None:
            return False
        display = np.asarray(result.display_image)
        return tuple(display.shape[:2]) == tuple(np.asarray(image).shape[:2])

    def _on_simulation_finished(self, result: SimulationResult) -> None:
        report_status = self._active_simulation_reports_status
        self._active_simulation_worker = None
        self._active_simulation_label = None
        self._active_simulation_reports_status = True
        self._set_simulation_controls_enabled(True)
        if result.mode_label == 'Preview':
            self._last_preview_fingerprint = self._pending_preview_fingerprint
            self._pending_preview_fingerprint = None
        self._set_or_add_output_layer(
            result.display_image,
            float_image=result.float_image,
            output_color_space=result.output_color_space,
            output_cctf_encoding=True,
            use_display_transform=result.use_display_transform,
        )
        if report_status:
            set_status(self._viewer, f'{tr(result.mode_label)}完成。{result.status_message}')
        for callback in tuple(self._simulation_finished_callbacks):
            try:
                callback(result)
            except (AttributeError, LookupError, RuntimeError, TypeError, ValueError):
                continue
        pending_export = self._export_pending_after_simulation
        self._export_pending_after_simulation = False
        do_export_now = False
        start_export_scan = False
        if pending_export:
            if result.mode_label == 'Scan' or self._result_is_full_size(result):
                do_export_now = True
            else:
                start_export_scan = True
        if self._export_after_scan and result.mode_label == 'Scan':
            self._export_after_scan = False
            do_export_now = True
        if start_export_scan:
            QTimer.singleShot(0, self._start_export_scan)
        elif do_export_now:
            QTimer.singleShot(0, self.export_now)
        else:
            self._replay_pending_auto_preview()

    def _on_simulation_failed(self, message: str) -> None:
        had_export = self._export_pending_after_simulation or self._export_after_scan
        self._active_simulation_worker = None
        self._export_pending_after_simulation = False
        self._export_after_scan = False
        mode_label = self._active_simulation_label or '模拟'
        self._active_simulation_label = None
        self._active_simulation_reports_status = True
        self._set_simulation_controls_enabled(True)
        QMessageBox.critical(dialog_parent(self._viewer), '运行模拟', f'模拟失败。\n\n{message}')
        set_status(self._viewer, f'{tr(mode_label)}失败')
        for callback in tuple(self._simulation_failed_callbacks):
            try:
                callback(message)
            except (AttributeError, LookupError, RuntimeError, TypeError, ValueError):
                continue
        if not had_export:
            self._replay_pending_auto_preview()

    def _start_export_scan(self) -> None:
        self._export_after_scan = True
        self.run_scan()
        if self._active_simulation_worker is None:
            self._export_after_scan = False

    def _set_simulation_controls_enabled(self, enabled: bool) -> None:
        simulation_section = getattr(self._widgets, 'simulation', None)
        if simulation_section is None:
            return
        for button_name in ('preview_button', 'scan_button', 'save_button'):
            button = getattr(simulation_section, button_name, None)
            set_enabled = getattr(button, 'setEnabled', None)
            if callable(set_enabled):
                set_enabled(enabled)

    def _run_simulation(self, *, source_layer_name: str) -> None:
        image_data = self._simulation_input_image(source_layer_name=source_layer_name)
        if image_data is None:
            QMessageBox.warning(dialog_parent(self._viewer), '运行模拟', '请先载入一张输入图像，再运行模拟。')
            return

        state = collect_gui_state(widgets=self._widgets)
        self._sync_white_border(white_padding=state.gui_only.display.white_padding)
        params = self._configure_simulation_params(
            build_params_from_state(state),
            source_layer_name=source_layer_name,
        )

        image = np.double(image_data)
        scan = self._process_image_with_runtime(image, params)
        scan_display, display_status = self._prepare_output_display_image(
            scan,
            output_color_space=state.simulation.io.output_color_space,
            use_display_transform=state.gui_only.display.use_display_transform,
        )
        self._set_or_add_output_layer(
            scan_display,
            float_image=scan,
            output_color_space=state.simulation.io.output_color_space,
            output_cctf_encoding=True,
            use_display_transform=state.gui_only.display.use_display_transform,
        )
        set_status(self._viewer, display_status)
