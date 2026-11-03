"""应用外壳：照片库 ↔ 调整页，以及单张照片的调整记忆。

这里只协调前端状态（打开哪张、存哪份 GUI state、什么时候导出），
所有显影/RAW/LUT 计算仍然走原有 controller。
"""

from __future__ import annotations

import copy
import time
from dataclasses import replace

from qtpy import QtCore, QtWidgets

from spektrafilm_gui import motion
from spektrafilm_gui.editor_page import EditorPage
from spektrafilm_gui.export_dialog import edit_export_settings
from spektrafilm_gui.film_frame import DEFAULT_FRAME_PRESET, preset_by_key
from spektrafilm_gui.grade_page import GradePage
from spektrafilm_gui.handoff import (
    handoff_fingerprint,
    handoff_is_current,
    handoff_path,
    has_grade_recipe,
    read_grade_recipe,
    read_handoff,
    write_grade_recipe,
    write_handoff,
)
from spektrafilm_gui.library_page import LibraryPage
from spektrafilm_gui.library_store import LibraryItem, LibraryStore, is_raw_image
from spektrafilm_gui.napari_layout import (
    _DropOverlay,
    _request_dark_title_bar,
    configure_napari_chrome,
    set_host_window,
    take_viewer_widget,
)
from spektrafilm_gui.persistence import load_default_gui_state
from spektrafilm_gui.state import PROJECT_DEFAULT_GUI_STATE
from spektrafilm_gui.state_bridge import apply_gui_state, collect_gui_state
from spektrafilm_gui.persistence import gui_state_from_dict, gui_state_to_dict
from spektrafilm_gui.theme import APP_STYLE_SHEET
from spektrafilm_gui.theme_library import LIBRARY_STYLE_SHEET
from spektrafilm_gui.theme_shell import SHELL_STYLE_SHEET
from spektrafilm_gui.ui_names import film_display_name, paper_display_name
from spektrafilm_gui.widget_primitives import platform_default_font

QApplication = QtWidgets.QApplication
QMainWindow = QtWidgets.QMainWindow
QMessageBox = QtWidgets.QMessageBox
QStackedWidget = QtWidgets.QStackedWidget
QStatusBar = QtWidgets.QStatusBar
QTimer = QtCore.QTimer
Qt = QtCore.Qt
Signal = QtCore.Signal


class WorkspaceWindow(QMainWindow):
    filesDropped = Signal(list)

    def __init__(
        self,
        *,
        viewer,
        widgets,
        controller,
        store: LibraryStore | None = None,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self._viewer = viewer
        self._widgets = widgets
        self._controller = controller
        self.store = store or LibraryStore()
        self._active_item_id = ''
        self._drop_overlay: QtWidgets.QWidget | None = None
        self._pending_handoff: tuple[str, str, Path] | None = None

        self.setWindowTitle('Spektrafilm')
        self.resize(1460, 940)
        self.setMinimumSize(1180, 760)
        self.setFont(platform_default_font())
        self.setStyleSheet(
            '\n\n'.join((APP_STYLE_SHEET, SHELL_STYLE_SHEET, LIBRARY_STYLE_SHEET))
        )
        self.setAcceptDrops(True)

        viewer_widget = take_viewer_widget(viewer)
        configure_napari_chrome(
            viewer,
            gray_18_canvas=bool(getattr(widgets.display.gray_18_canvas, 'value', False)),
        )
        set_host_window(viewer, self)

        self.library_page = LibraryPage(self.store)
        self.thumbnails = self.library_page.thumbnails
        self.editor_page = EditorPage(
            viewer,
            viewer_widget,
            widgets,
            controller,
            thumbnails=self.thumbnails,
        )
        self.grade_page = GradePage()
        self.grade_page.set_display_transform_provider(self._display_transform_enabled)
        set_frame_provider = getattr(controller, 'set_frame_provider', None)
        if callable(set_frame_provider):
            set_frame_provider(self._frame_settings)
        self._stack = QStackedWidget()
        self._stack.addWidget(self.library_page)
        self._stack.addWidget(self.editor_page)
        self._stack.addWidget(self.grade_page)
        self.setCentralWidget(self._stack)

        status = QStatusBar()
        status.setSizeGripEnabled(False)
        self.setStatusBar(status)

        self._persist_timer = QTimer(self)
        self._persist_timer.setSingleShot(True)
        self._persist_timer.setInterval(1500)
        self._persist_timer.timeout.connect(self._persist_active_state)

        self._grade_persist_timer = QTimer(self)
        self._grade_persist_timer.setSingleShot(True)
        self._grade_persist_timer.setInterval(600)
        self._grade_persist_timer.timeout.connect(self._save_grade_recipe)
        self._grade_persist_pending = False

        self._connect_signals()
        controller.add_simulation_finished_callback(self._on_simulation_finished)
        for registrar, callback in (
            ('add_simulation_started_callback', self._on_simulation_started),
            ('add_simulation_progress_callback', self._on_simulation_progress),
            ('add_simulation_failed_callback', self._on_simulation_failed),
        ):
            add = getattr(controller, registrar, None)
            if callable(add):
                add(callback)
        self._apply_dark_title_bar()
        self.show_library()
        status.showMessage('照片库已就绪', 3000)

    # ── 连接 ────────────────────────────────────────────────────
    def _connect_signals(self) -> None:
        self.library_page.open_item_requested.connect(self.open_item)
        self.library_page.status_message.connect(self._show_status)
        self.library_page.photos_imported.connect(self._on_photos_imported)

        self.editor_page.back_requested.connect(self.show_library)
        self.editor_page.grade_requested.connect(self._on_grade_requested)
        self.editor_page.direct_export_requested.connect(self._request_direct_export)
        self.editor_page.export_settings_requested.connect(self._on_export_settings)
        self.editor_page.quick_preview_requested.connect(self._controller.run_preview)
        self.editor_page.scan_requested.connect(self._controller.run_scan)
        self.editor_page.save_requested.connect(self._controller.save_output_layer)
        self.editor_page.favorite_toggled.connect(self._on_favorite_toggled)
        self.editor_page.add_photos_requested.connect(lambda: self.library_page.import_photos(parent=self))
        self.editor_page.reset_requested.connect(self._on_reset)
        self.editor_page.film_selected.connect(self._on_film_selected)
        self.editor_page.paper_selected.connect(self._on_paper_selected)
        self.editor_page.frame_selected.connect(self._on_frame_selected)
        self.editor_page.frame_changed.connect(self._on_frame_changed)
        self.editor_page.profile_changed.connect(self._on_deck_profile_changed)
        self.editor_page.quick_changed.connect(self._schedule_persist)
        self.editor_page.strip_item_selected.connect(self.open_item)
        self.grade_page.back_requested.connect(self.show_editor)
        self.grade_page.recipe_changed.connect(self._schedule_grade_persist)
        self.grade_page.export_settings_requested.connect(self._on_export_settings)
        self.grade_page.grade_image_ready.connect(self._on_grade_image_ready)
        self.grade_page.status_message.connect(self._show_status)
        self._grade_persist_pending = False
        set_scale = getattr(self._controller, 'set_preview_render_scale', None)
        if callable(set_scale):
            self.editor_page.preview_scale_changed.connect(set_scale)
        self.filesDropped.connect(self._on_files_dropped)
        try:
            self._widgets.simulation.film_stock.textActivated.connect(self._on_profile_combo_changed)
            self._widgets.simulation.print_paper.textActivated.connect(self._on_profile_combo_changed)
        except AttributeError:
            pass

    def _apply_dark_title_bar(self) -> None:
        try:
            _request_dark_title_bar(self)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return

    def _show_status(self, message: str) -> None:
        self.statusBar().showMessage(message, 5000)

    # ── 页面切换 ────────────────────────────────────────────────
    def show_library(self) -> None:
        if self._controller.is_simulating():
            self._show_status('正在计算，请稍候再返回照片库')
            return
        self._flush_grade_recipe()
        self._persist_active_state()
        self.grade_page.unload()
        self._active_item_id = ''
        self._stack.setCurrentIndex(0)
        self.library_page.refresh()
        self.library_page.set_current_item('')
        motion.fade_in(self.library_page, duration=200, start=0.6)
        self.setWindowTitle('Spektrafilm')
        self.statusBar().showMessage('照片库', 2500)

    def show_editor(self) -> None:
        if not self._active_item_id or self._stack.currentIndex() != 2:
            return
        self._flush_grade_recipe()
        self._persist_active_state()
        self._stack.setCurrentIndex(1)
        self.grade_page.unload()
        self.setWindowTitle('Spektrafilm')
        self._show_status('显影台')

    def _sync_display_transform(self) -> None:
        """预览必须按显示器 ICC 显示，才能和导出文件在 macOS 里的观感一致。"""
        sync = getattr(self._controller, 'sync_display_transform_availability', None)
        if callable(sync):
            sync(report_status=False)

    def _display_transform_enabled(self) -> bool:
        """调色台画布跟随显影台的「使用系统色彩显示」开关。"""
        try:
            return bool(self._widgets.display.get_state().use_display_transform)
        except (AttributeError, TypeError):
            return False

    def _frame_settings(self) -> tuple[bool, str]:
        """把右侧栏的边框开关与左侧预设台的选择交给控制器。"""
        try:
            state = self.editor_page.frame_state_dict()
        except (AttributeError, TypeError, ValueError):
            return True, DEFAULT_FRAME_PRESET
        return bool(state.get('enabled', True)), str(state.get('preset') or DEFAULT_FRAME_PRESET)

    def _request_direct_export(self) -> None:
        request = getattr(self._controller, 'request_direct_export', None)
        if callable(request):
            request()

    def _on_grade_requested(self) -> None:
        """进入调色台：交接图有效就直接进，否则先跑一次全尺寸显影。"""
        if not self._active_item_id:
            return
        if self._controller.is_simulating():
            self._show_status('显影完成后再调色')
            return
        item = self.store.item(self._active_item_id)
        if item is None:
            return

        self._persist_active_state()
        item = self.store.item(self._active_item_id) or item
        state_data = item.state if isinstance(item.state, dict) else None
        fingerprint = handoff_fingerprint(state_data)
        if handoff_is_current(state_data, fingerprint):
            self._open_grade_page(item)
            return

        path = handoff_path(item.id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._show_status(f'无法创建调色目录：{exc}')
            return
        start = getattr(self._controller, 'start_handoff', None)
        if not callable(start):
            self._show_status('当前版本无法生成调色交接图')
            return
        self._pending_handoff = (item.id, fingerprint, path)
        if not start(str(path), self._on_handoff_finished, fingerprint=fingerprint):
            self._pending_handoff = None
            self._show_status('当前无法生成调色交接图')

    def _on_handoff_finished(self, result, error) -> None:
        pending = self._pending_handoff
        self._pending_handoff = None
        self.editor_page.set_simulation_busy(False)
        if pending is None:
            return
        if error is not None or result is None:
            self._show_status(f'调色交接失败：{error}')
            QMessageBox.warning(self, '调色', f'交接图生成失败。\n\n{error}')
            return

        item_id, fingerprint, path = pending
        float_image = getattr(result, 'float_image', None)
        height = width = 0
        shape = getattr(float_image, 'shape', None)
        if shape is not None and len(shape) >= 2:
            height, width = int(shape[0]), int(shape[1])

        item = self.store.item(item_id)
        if item is None:
            return
        state_data = dict(item.state) if isinstance(item.state, dict) else {}
        state_data = write_handoff(
            state_data,
            path=path,
            fingerprint=fingerprint,
            width=width,
            height=height,
        )
        updated = self.store.update_item(item_id, save=True, state=state_data)
        if updated is not None:
            self.library_page.refresh_item(updated.id)
            item = updated
        self.editor_page.set_grade_recipe(has_grade_recipe(item.state))
        self._open_grade_page(item)
        self._show_status('调色交接图已生成')

    def _open_grade_page(self, item: LibraryItem) -> None:
        handoff = read_handoff(item.state) or {}
        path = str(handoff.get('path') or '')
        recipe = read_grade_recipe(item.state)
        grade = item.state.get('grade') if isinstance(item.state, dict) else None
        preset_id = str(grade.get('preset_id') or '') if isinstance(grade, dict) else ''
        loaded = self.grade_page.load(item, path or None, recipe, preset_id=preset_id)
        self._grade_persist_pending = False
        self._stack.setCurrentIndex(2)
        self.setWindowTitle('Spektrafilm · 调色台')
        motion.fade_in(self.grade_page, duration=200, start=0.6)
        if loaded:
            self._show_status(f'进入调色台 · {item.name}')
        else:
            self._show_status('交接图读取失败，请返回显影台重新调色')

    def open_item(self, item_id: str) -> None:
        if self._controller.is_simulating():
            self._show_status('正在计算，请稍候再切换照片')
            return
        item = self.store.item(item_id)
        if item is None:
            return
        if self._stack.currentIndex() == 1 and self._active_item_id == item_id:
            return
        if not item.exists:
            QMessageBox.warning(self, '打开照片', '这张照片的源文件已被移动或删除。\n\n请重新导入，或把文件放回原位置。')
            return

        # 以磁盘上的真实后缀为准，修复历史存档里错误的 is_raw 标记。
        raw_item = is_raw_image(item.path)
        if item.is_raw != raw_item:
            repaired = self.store.update_item(item_id, save=True, is_raw=raw_item)
            if repaired is not None:
                item = repaired

        self._flush_grade_recipe()
        self._persist_active_state()
        self.grade_page.unload()
        state = self._state_for_item(item)
        # 显示/预览偏好是全局的，不能被某张照片的存档带跑
        global_display = self._widgets.display.get_state()
        global_auto_preview = self._widgets.simulation.auto_preview_value()
        try:
            apply_gui_state(state, widgets=self._widgets)
        except (AttributeError, KeyError, TypeError, ValueError):
            apply_gui_state(PROJECT_DEFAULT_GUI_STATE, widgets=self._widgets)
        self._widgets.display.set_state(global_display)
        self._widgets.simulation.set_auto_preview_value(global_auto_preview)
        self._sync_display_transform()
        self._refresh_frame(persist=False)

        self._active_item_id = item_id
        self._stack.setCurrentIndex(1)
        motion.fade_in(self.editor_page.inspector, duration=180, start=0.5)
        motion.fade_in(self.editor_page.preset_rail, duration=180, start=0.5)
        self.setWindowTitle('Spektrafilm')
        quick_raw = item.state.get('quick') if isinstance(item.state, dict) else None
        self.editor_page.set_quick_state(quick_raw)
        frame_raw = item.state.get('frame') if isinstance(item.state, dict) else None
        self.editor_page.set_frame_state(frame_raw)
        display_item = self._display_item(item, state)
        self.editor_page.set_photo(display_item, self._strip_items_for(display_item))
        self.editor_page.set_grade_recipe(has_grade_recipe(item.state))
        self.editor_page.set_grade_ready(False)
        self.editor_page.set_histogram(None)
        self.library_page.set_current_item(item_id)

        QApplication.setOverrideCursor(Qt.WaitCursor)
        load_failed = False
        try:
            if raw_item:
                try:
                    self._widgets.load_raw.set_path(item.path)
                except AttributeError:
                    pass
                self._controller.load_raw_image(item.path)
            else:
                self._controller.load_input_image(item.path)
        except (OSError, RuntimeError, ValueError) as exc:
            load_failed = True
            QMessageBox.critical(self, '打开照片', f'这张照片没能打开。\n\n{exc}')
        finally:
            QApplication.restoreOverrideCursor()

        current_path = getattr(self._controller, '_current_input_path', None)
        if load_failed or current_path != item.path:
            self._active_item_id = ''
            self._stack.setCurrentIndex(0)
            self.library_page.set_current_item('')
            self.library_page.refresh()
            self.setWindowTitle('Spektrafilm')
            self._show_status(f'打开 {item.name} 失败')
            return

        size = self._controller.current_input_size()
        updates = {
            'film_stock': str(getattr(self._widgets.simulation.film_stock, 'value', '') or ''),
            'print_paper': str(getattr(self._widgets.simulation.print_paper, 'value', '') or ''),
        }
        if size is not None:
            updates['width'] = size[0]
            updates['height'] = size[1]
        saved = self.store.update_item(item_id, save=True, **updates)
        if saved is not None:
            display_item = saved
        self.editor_page.set_photo(display_item, self._strip_items_for(display_item))
        self.editor_page.refresh_after_state_change()
        self._persist_active_state()
        self._show_status(f'已打开 {item.name}')

    # ── 单张状态 ────────────────────────────────────────────────
    def _state_for_item(self, item: LibraryItem):
        if isinstance(item.state, dict):
            try:
                return gui_state_from_dict(item.state)
            except (AttributeError, KeyError, TypeError, ValueError):
                pass
        return load_default_gui_state()

    @staticmethod
    def _display_item(item: LibraryItem, state) -> LibraryItem:
        try:
            film = str(state.simulation.selection.film_stock or item.film_stock)
            paper = str(state.simulation.selection.print_paper or item.print_paper)
        except AttributeError:
            film, paper = item.film_stock, item.print_paper
        return replace(item, film_stock=film, print_paper=paper)

    def _strip_items_for(self, item: LibraryItem) -> list[LibraryItem]:
        if item.folder_id and self.store.folder(item.folder_id) is not None:
            return self.store.items_in_folder(item.folder_id)
        return self.store.all_items()

    @staticmethod
    def _adjustment_fingerprint(data: dict) -> dict:
        """只比较“照片调整”，忽略全局显示/预览/保存偏好。"""
        fingerprint = copy.deepcopy(data)
        fingerprint.pop('display', None)
        fingerprint.pop('quick', None)
        fingerprint.pop('grade', None)
        # 边框是显示层选择（与预览白边同类），不算「照片被调整过」。
        fingerprint.pop('frame', None)
        simulation = fingerprint.get('simulation')
        if isinstance(simulation, dict):
            for key in ('auto_preview', 'scan_film', 'saving_color_space', 'saving_cctf_encoding'):
                simulation.pop(key, None)
            workflow = simulation.get('workflow')
            if isinstance(workflow, dict):
                workflow.pop('auto_preview', None)
                workflow.pop('saving_color_space', None)
                workflow.pop('saving_cctf_encoding', None)
            io = simulation.get('io')
            if isinstance(io, dict):
                io.pop('scan_film', None)
        return fingerprint

    def _persist_active_state(self) -> None:
        if not self._active_item_id:
            return
        if self.store.item(self._active_item_id) is None:
            return
        state = collect_gui_state(widgets=self._widgets)
        data = gui_state_to_dict(state)
        data['quick'] = self.editor_page.quick_state_dict()
        data['frame'] = self.editor_page.frame_state_dict()
        existing = self.store.item(self._active_item_id)
        existing_state = existing.state if existing is not None and isinstance(existing.state, dict) else {}
        if isinstance(existing_state.get('grade'), dict):
            # 调色配方与交接图独立于显影参数，不能被每次防抖保存冲掉。
            data['grade'] = copy.deepcopy(existing_state['grade'])
        try:
            default_data = gui_state_to_dict(load_default_gui_state())
        except (OSError, ValueError, TypeError):
            default_data = {}
        adjusted = bool(default_data) and (
            self._adjustment_fingerprint(data) != self._adjustment_fingerprint(default_data)
        )
        film = str(getattr(self._widgets.simulation.film_stock, 'value', '') or '')
        paper = str(getattr(self._widgets.simulation.print_paper, 'value', '') or '')
        updated = self.store.set_adjustment_state(
            self._active_item_id,
            data,
            film_stock=film,
            print_paper=paper,
            adjusted=adjusted,
        )
        if updated is not None:
            self.editor_page.top_bar.set_photo(updated)
            self.editor_page.preview.set_photo_info(updated)
            self.editor_page.set_grade_recipe(has_grade_recipe(updated.state))
            try:
                self.library_page.refresh_item(updated.id)
            except (AttributeError, RuntimeError):
                pass

    def _schedule_persist(self) -> None:
        if self._active_item_id:
            self._persist_timer.start()

    # ── 调色配方 ────────────────────────────────────────────────
    def _schedule_grade_persist(self, _recipe: object | None = None) -> None:
        self._grade_persist_pending = True
        self._grade_persist_timer.start()

    def _flush_grade_recipe(self) -> None:
        self._grade_persist_timer.stop()
        if self._grade_persist_pending or self._stack.currentIndex() == 2:
            self._grade_persist_pending = True
            self._save_grade_recipe()

    def _save_grade_recipe(self) -> None:
        if not self._grade_persist_pending or not self._active_item_id:
            return
        self._grade_persist_pending = False
        item = self.store.item(self._active_item_id)
        if item is None:
            return
        recipe = self.grade_page.recipe()
        preset_id = self.grade_page.preset_id()
        state_data = dict(item.state) if isinstance(item.state, dict) else {}
        if recipe.is_identity():
            grade = state_data.get('grade')
            if isinstance(grade, dict):
                grade = dict(grade)
                grade.pop('recipe', None)
                grade.pop('preset_id', None)
                grade['updated_at'] = time.time()
                state_data['grade'] = grade
        else:
            state_data = write_grade_recipe(state_data, recipe, preset_id=preset_id)
        updated = self.store.update_item(item.id, save=True, state=state_data)
        if updated is None:
            return
        try:
            self.library_page.refresh_item(updated.id)
        except (AttributeError, RuntimeError):
            pass
        self.editor_page.set_grade_recipe(has_grade_recipe(updated.state))

    def _on_grade_image_ready(self, image, direct: bool) -> None:
        export = getattr(self._controller, 'export_graded_image', None)
        if callable(export):
            export(image, direct=bool(direct))
        else:
            self._show_status('当前版本无法导出调色结果')

    def _on_simulation_finished(self, result) -> None:
        self.editor_page.set_simulation_busy(False)
        self.editor_page.set_grade_ready(True)
        try:
            # 用未加边框的显示像素做直方图，否则白边/片基会把分布拉偏。
            self.editor_page.set_histogram(result.display_image)
        except (AttributeError, TypeError, ValueError):
            pass
        self._schedule_persist()

    def _on_simulation_started(self, _mode_label: str, scale: float) -> None:
        self.editor_page.set_simulation_busy(True, scale)

    def _on_simulation_progress(self, label: str, completed: int, total: int) -> None:
        self.editor_page.set_simulation_progress(label, completed, total)

    def _on_simulation_failed(self, _message: str) -> None:
        self.editor_page.set_simulation_busy(False)

    def _on_profile_combo_changed(self, _value: str) -> None:
        # 控制器已经通过 textActivated 应用了 profile 默认值；这里只把
        # 代理滑块/预设台同步到新值，避免基础面板显示旧数字。
        QTimer.singleShot(0, self._after_external_state_change)

    def _after_external_state_change(self) -> None:
        self.editor_page.refresh_after_state_change()
        self._schedule_persist()

    # ── 预设 / 收藏 / 重置 ──────────────────────────────────────
    def _on_film_selected(self, raw: str) -> None:
        try:
            self._widgets.simulation.film_stock.value = raw
        except (AttributeError, ValueError):
            return
        self._controller.apply_profile_defaults(raw)
        self.editor_page.refresh_after_state_change()
        self._schedule_persist()
        self._show_status(f'已套用 {film_display_name(raw)}')

    def _on_paper_selected(self, raw: str) -> None:
        try:
            self._widgets.simulation.print_paper.value = raw
        except (AttributeError, ValueError):
            return
        self._controller.apply_profile_defaults(raw)
        self.editor_page.refresh_after_state_change()
        self._schedule_persist()
        self._show_status(f'已套用 {paper_display_name(raw)}')

    def _on_frame_selected(self, raw: str) -> None:
        self.editor_page.set_frame_preset(raw)
        self._refresh_frame()
        self._show_status(f'边框已切换为 {preset_by_key(raw).name}')

    def _on_frame_changed(self) -> None:
        self._refresh_frame()

    def _refresh_frame(self, *, persist: bool = True) -> None:
        apply_frame_state = getattr(self._controller, 'apply_frame_state', None)
        if callable(apply_frame_state):
            apply_frame_state()
        if persist:
            self._schedule_persist()

    def _on_favorite_toggled(self, favorite: bool) -> None:
        if not self._active_item_id:
            return
        updated = self.store.set_favorite(self._active_item_id, favorite)
        if updated is not None:
            self.editor_page.set_favorite(updated.favorite)
            self._show_status('已收藏' if favorite else '已取消收藏')

    def _on_export_settings(self) -> None:
        getter = getattr(self._controller, 'export_settings', None)
        setter = getattr(self._controller, 'set_export_settings', None)
        if not callable(getter) or not callable(setter):
            return
        updated = edit_export_settings(self, getter())
        if updated is not None:
            try:
                setter(updated)
            except OSError:
                self._show_status('导出设置保存失败')
                return
            self._show_status('导出设置已保存')

    def _on_deck_profile_changed(self, leaf: str, raw: str) -> None:
        self.editor_page.refresh_after_state_change()
        self._schedule_persist()
        if leaf == 'film_stock':
            self._show_status(f'已套用 {film_display_name(raw)}')
        elif leaf == 'print_paper':
            self._show_status(f'已套用 {paper_display_name(raw)}')

    def _on_reset(self) -> None:
        global_display = self._widgets.display.get_state()
        global_auto_preview = self._widgets.simulation.auto_preview_value()
        apply_gui_state(load_default_gui_state(), widgets=self._widgets)
        self._widgets.display.set_state(global_display)
        self._widgets.simulation.set_auto_preview_value(global_auto_preview)
        self._sync_display_transform()
        self.editor_page.reset_quick_state()
        self.editor_page.refresh_after_state_change()
        self._schedule_persist()
        self._show_status('已重置为默认参数')

    def _on_photos_imported(self, ids: list[str]) -> None:
        if not ids:
            return
        if self._stack.currentIndex() == 1:
            self.open_item(ids[0])

    def _on_files_dropped(self, paths: list[str]) -> None:
        self.library_page.import_paths(paths)

    # ── 拖放 ────────────────────────────────────────────────────
    @staticmethod
    def _dropped_paths(event) -> list[str]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._dropped_paths(event):
            event.acceptProposedAction()
            self._show_drop_overlay(True)
            return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._show_drop_overlay(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt API name
        paths = self._dropped_paths(event)
        self._show_drop_overlay(False)
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self.filesDropped.emit(paths)

    def _show_drop_overlay(self, visible: bool) -> None:
        if visible:
            if self._drop_overlay is None:
                self._drop_overlay = _DropOverlay(self)
            self._drop_overlay.setGeometry(self.rect())
            self._drop_overlay.raise_()
            self._drop_overlay.show()
        elif self._drop_overlay is not None:
            self._drop_overlay.hide()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        if self._drop_overlay is not None and self._drop_overlay.isVisible():
            self._drop_overlay.setGeometry(self.rect())

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._controller.is_simulating():
            QMessageBox.information(self, '正在计算', '显影计算还没有结束，完成后再关闭窗口。')
            event.ignore()
            return
        self._persist_timer.stop()
        self._flush_grade_recipe()
        self._persist_active_state()
        self.thumbnails.wait_for_idle(2000)
        super().closeEvent(event)


def build_workspace_window(*, viewer, widgets, controller, store: LibraryStore | None = None) -> WorkspaceWindow:
    return WorkspaceWindow(viewer=viewer, widgets=widgets, controller=controller, store=store)
