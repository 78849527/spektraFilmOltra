"""调整页：顶栏 + 左预设台 + 中预览/胶片条 + 右调整台。"""

from __future__ import annotations

from pathlib import Path

from qtpy import QtCore, QtGui, QtWidgets

from spektrafilm_gui import shell_icons
from spektrafilm_gui.parameter_deck import ParameterDeck
from spektrafilm_gui.library_page import ElidedLabel, ThumbnailView
from spektrafilm_gui.library_store import LibraryItem
from spektrafilm_gui.library_thumbs import ThumbnailService
from spektrafilm_gui.preset_rail import PresetRail
from spektrafilm_gui.theme_oflim import ACCENT, SURFACE_2, TEXT_1, TEXT_2, TEXT_3, rgba
from spektrafilm_gui.ui_names import film_display_name, paper_display_name
from spektrafilm_gui.widget_primitives import tabular_font

QFrame = QtWidgets.QFrame
QHBoxLayout = QtWidgets.QHBoxLayout
QLabel = QtWidgets.QLabel
QMenu = QtWidgets.QMenu
QPushButton = QtWidgets.QPushButton
QScrollArea = QtWidgets.QScrollArea
QSplitter = QtWidgets.QSplitter
QToolButton = QtWidgets.QToolButton
QVBoxLayout = QtWidgets.QVBoxLayout
QWidget = QtWidgets.QWidget
Qt = QtCore.Qt
Signal = QtCore.Signal

SIMULATION_STAGE_LABELS = {
    'preprocess': '输入准备',
    'filming.expose': '胶片曝光',
    'filming.develop': '胶片显影',
    'printing.expose': '放大曝光',
    'printing.develop': '相纸显影',
    'scanning.scan_print': '扫描相纸',
    'scanning.scan_film': '扫描底片',
}

RENDER_SCALE_LABELS = {1.0: '完整', 0.5: '1/2', 0.25: '1/4'}


class EditorTopBar(QWidget):
    back_requested = Signal()
    export_requested = Signal()
    export_settings_requested = Signal()
    quick_preview_requested = Signal()
    scan_requested = Signal()
    save_requested = Signal()
    favorite_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('editorTopBar')
        self.setFixedHeight(46)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 16, 0)
        layout.setSpacing(9)

        back = QPushButton('照片库')
        back.setObjectName('compactBack')
        back.setIcon(shell_icons.icon('back', TEXT_2, 10))
        back.setIconSize(QtCore.QSize(10, 10))
        back.setFixedHeight(26)
        back.setCursor(Qt.PointingHandCursor)
        back.setToolTip('返回照片库')
        back.clicked.connect(self.back_requested.emit)

        self._name = ElidedLabel('')
        self._name.setObjectName('editorTitle')
        self._name.setMinimumWidth(140)
        self._meta = ElidedLabel('')
        self._meta.setObjectName('editorMeta')
        self._meta.setFont(tabular_font(self._meta.font()))
        self._meta.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._busy = QLabel('')
        self._busy.setObjectName('editorBusy')
        self._busy.setStyleSheet(f'color: {ACCENT}; font-size: 10px; background: transparent;')
        self._busy.hide()

        self._progress = QtWidgets.QProgressBar(self)
        self._progress.setObjectName('topProgress')
        self._progress.setFixedHeight(2)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        self._progress.setStyleSheet(
            f'QProgressBar {{ background: {SURFACE_2}; border: none; }}'
            f'QProgressBar::chunk {{ background: {ACCENT}; }}'
        )
        self._progress.hide()

        self._favorite = QPushButton()
        self._favorite.setObjectName('iconButton')
        self._favorite.setCheckable(True)
        self._favorite.setFixedSize(26, 26)
        self._favorite.setCursor(Qt.PointingHandCursor)
        self._favorite.setToolTip('收藏这张照片')
        self._favorite.toggled.connect(self._on_favorite_toggled)

        self._export_button = QPushButton('导出')
        self._export_button.setObjectName('exportButton')
        self._export_button.setCursor(Qt.PointingHandCursor)
        self._export_button.setFixedHeight(26)
        self._export_button.setToolTip('按当前导出设置直接导出；点右侧箭头修改设置')
        self._export_button.setIcon(shell_icons.icon('export', ACCENT, 12))
        self._export_button.setIconSize(QtCore.QSize(12, 12))
        self._export_button.clicked.connect(self.export_requested.emit)

        self._export_menu = QPushButton()
        self._export_menu.setObjectName('exportMenu')
        self._export_menu.setIcon(shell_icons.icon('chevron_down', ACCENT, 10))
        self._export_menu.setIconSize(QtCore.QSize(10, 10))
        self._export_menu.setFixedWidth(22)
        self._export_menu.setFixedHeight(26)
        self._export_menu.setCursor(Qt.PointingHandCursor)
        menu = QMenu(self._export_menu)
        menu.addAction('导出设置…', self.export_settings_requested.emit)
        menu.addAction('另存为…', self.save_requested.emit)
        self._export_menu.setMenu(menu)

        export_box = QWidget()
        export_box.setObjectName('exportBox')
        export_box.setAttribute(Qt.WA_StyledBackground, True)
        export_layout = QHBoxLayout(export_box)
        export_layout.setContentsMargins(0, 0, 0, 0)
        export_layout.setSpacing(0)
        export_layout.addWidget(self._export_button)
        export_layout.addWidget(self._export_menu)

        layout.addWidget(back, 0, Qt.AlignVCenter)
        layout.addWidget(self._name, 1, Qt.AlignVCenter)
        layout.addWidget(self._busy, 0, Qt.AlignVCenter)
        layout.addWidget(self._meta, 0, Qt.AlignVCenter)
        layout.addSpacing(6)
        layout.addWidget(self._favorite, 0, Qt.AlignVCenter)
        layout.addSpacing(4)
        layout.addWidget(export_box, 0, Qt.AlignVCenter)

    def set_photo(self, item: LibraryItem) -> None:
        self._name.setText(item.name)
        parts: list[str] = []
        if item.width and item.height:
            parts.append(f'{item.width}×{item.height}')
        if item.is_raw:
            parts.append('RAW')
        if item.film_stock:
            parts.append(film_display_name(item.film_stock))
        if item.print_paper:
            parts.append(paper_display_name(item.print_paper))
        self._meta.setText(' · '.join(parts))
        self._favorite.blockSignals(True)
        self._favorite.setChecked(item.favorite)
        self._favorite.blockSignals(False)
        self._favorite.setIcon(
            shell_icons.icon('star_filled' if item.favorite else 'star', ACCENT if item.favorite else TEXT_1, 15)
        )

    def set_favorite(self, favorite: bool) -> None:
        self._favorite.blockSignals(True)
        self._favorite.setChecked(favorite)
        self._favorite.blockSignals(False)
        self._favorite.setIcon(
            shell_icons.icon('star_filled' if favorite else 'star', ACCENT if favorite else TEXT_1, 15)
        )

    def _on_favorite_toggled(self, checked: bool) -> None:
        self._favorite.setIcon(
            shell_icons.icon('star_filled' if checked else 'star', ACCENT if checked else TEXT_1, 15)
        )
        self.favorite_toggled.emit(bool(checked))

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._progress.setGeometry(0, max(0, self.height() - 2), self.width(), 2)

    def set_simulation_busy(self, busy: bool, scale: float = 1.0) -> None:
        if busy:
            self._progress.setRange(0, 1)
            self._progress.setValue(0)
            self._progress.show()
            self._progress.raise_()
            self._busy.setText(f'正在显影 · {RENDER_SCALE_LABELS.get(float(scale), "完整")}')
            self._busy.show()
            return
        self._busy.hide()
        self._progress.hide()
        self._progress.setValue(0)

    def set_simulation_progress(self, label: str, completed: int, total: int) -> None:
        total = max(int(total), 1)
        completed = max(0, min(int(completed), total))
        self._progress.setRange(0, total)
        self._progress.setValue(completed)
        stage = SIMULATION_STAGE_LABELS.get(label, label)
        self._busy.setText(f'正在显影 · {stage}  {completed}/{total}')
        self._busy.show()
        self._progress.show()
        self._progress.raise_()


class PreviewStage(QWidget):
    render_scale_changed = Signal(float)
    render_requested = Signal()

    def __init__(self, viewer, viewer_widget: QWidget, *, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('previewStage')
        self._viewer = viewer
        self._render_scale = 0.5
        self._scale_actions: dict[float, QtGui.QAction] = {}

        self._canvas = QWidget()
        self._canvas.setObjectName('previewCanvas')
        canvas_layout = QVBoxLayout(self._canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        canvas_layout.addWidget(viewer_widget, 1)

        # 顶部状态 chip（照片 / 底片）
        self._chip = QLabel('照片')
        self._chip.setObjectName('previewChip')
        self._chip.setParent(self._canvas)
        self._chip.adjustSize()
        self._chip.move(14, 14)
        self._chip.raise_()

        # 对比模式下的两侧标签
        self._before_chip = QLabel('原片')
        self._before_chip.setObjectName('previewChip')
        self._before_chip.setParent(self._canvas)
        self._before_chip.hide()
        self._after_chip = QLabel('显影')
        self._after_chip.setObjectName('previewChip')
        self._after_chip.setParent(self._canvas)
        self._after_chip.hide()

        # 底部信息 chip（悬浮在画面上，不做通栏条）
        self._info = ElidedLabel('')
        self._info.setObjectName('floatInfo')
        self._info.setFont(tabular_font(self._info.font()))
        self._info.setParent(self._canvas)

        # 左下角渲染档位：完整 / 1/2 / 1/4
        self._scale_button = QPushButton('1/2')
        self._scale_button.setObjectName('ghostAction')
        self._scale_button.setFixedHeight(24)
        self._scale_button.setCursor(Qt.PointingHandCursor)
        self._scale_button.setToolTip('预览渲染分辨率：完整、1/2 或 1/4')
        self._scale_button.setIcon(shell_icons.icon('chevron_down', TEXT_3, 8))
        self._scale_button.setIconSize(QtCore.QSize(8, 8))
        self._scale_button.setParent(self._canvas)
        scale_menu = QMenu(self._scale_button)
        scale_group = QtGui.QActionGroup(self._scale_button)
        scale_group.setExclusive(True)
        for text, value in (('完整', 1.0), ('1/2', 0.5), ('1/4', 0.25)):
            action = scale_menu.addAction(text)
            action.setCheckable(True)
            action.setData(value)
            action.setActionGroup(scale_group)
            action.triggered.connect(lambda _checked=False, scale=value: self.set_render_scale(scale))
            self._scale_actions[value] = action
        self._scale_button.setMenu(scale_menu)
        self._scale_actions[0.5].setChecked(True)

        # 悬浮工具条：对比 / 旋转 / 适应 / 缩放
        self._toolbar = QWidget(self._canvas)
        self._toolbar.setObjectName('floatToolbar')
        tools = QHBoxLayout(self._toolbar)
        tools.setContentsMargins(9, 0, 9, 0)
        tools.setSpacing(2)

        self._compare_button = QPushButton('对比')
        self._compare_button.setObjectName('ghostAction')
        self._compare_button.setCheckable(True)
        self._compare_button.setCursor(Qt.PointingHandCursor)
        self._compare_button.setIcon(shell_icons.icon('compare', TEXT_2, 13))
        self._compare_button.setIconSize(QtCore.QSize(13, 13))
        self._compare_button.setFixedHeight(24)
        self._compare_button.setToolTip('拖动分隔线对比原片与显影结果')
        self._compare_button.toggled.connect(self._on_compare_toggled)
        tools.addWidget(self._compare_button)

        render_button = QPushButton('渲染')
        render_button.setObjectName('ghostAction')
        render_button.setFixedHeight(24)
        render_button.setCursor(Qt.PointingHandCursor)
        render_button.setToolTip('按当前渲染档位重新计算预览')
        render_button.clicked.connect(self.render_requested.emit)
        tools.addWidget(render_button)

        tools.addWidget(self._tool_button('rotate_ccw', '逆时针旋转', lambda: self._rotate(-1)))
        tools.addWidget(self._tool_button('rotate_cw', '顺时针旋转', lambda: self._rotate(1)))
        tools.addWidget(self._tool_button('fit', '适应窗口', self._fit))
        for percent in (100, 200, 400):
            button = QPushButton(f'{percent}%')
            button.setObjectName('ghostAction')
            button.setFixedHeight(24)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip('屏幕像素与图像像素 1:1 对应' if percent == 100 else f'{percent}% 放大查看')
            button.clicked.connect(lambda _checked=False, value=percent: self._zoom(value))
            tools.addWidget(button)

        # 阻尼缩放 + 原片对比（仅真实 napari viewer 可用）
        self._zoom_controller = None
        self.compare = None
        native = self._canvas_native(viewer)
        if native is not None:
            try:
                from spektrafilm_gui.napari_layout import ViewerZoomController

                self._zoom_controller = ViewerZoomController(viewer, parent=self)
                native.installEventFilter(self)
            except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
                self._zoom_controller = None
            try:
                from spektrafilm_gui.preview_compare import CompareSession

                self.compare = CompareSession(viewer, self._canvas, parent=self)
                self.compare.active_changed.connect(self._on_compare_active)
            except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
                self.compare = None
        if self.compare is None:
            self._compare_button.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._canvas, 1)

    # ── 画布浮动层布局 ──────────────────────────────────────────
    def _layout_overlays(self) -> None:
        width = max(self._canvas.width(), 1)
        height = max(self._canvas.height(), 1)

        self._chip.adjustSize()
        self._chip.move(14, 14)

        self._before_chip.adjustSize()
        self._after_chip.adjustSize()
        self._before_chip.move(14, 14)
        self._after_chip.move(width - 14 - self._after_chip.width(), 14)

        self._info.adjustSize()
        self._scale_button.adjustSize()
        button_height = max(self._scale_button.height(), 24)
        self._scale_button.move(14, height - 14 - button_height)

        self._toolbar.adjustSize()
        toolbar_x = width - 14 - self._toolbar.width()
        self._toolbar.move(toolbar_x, height - 14 - self._toolbar.height())

        info_x = 14 + self._scale_button.width() + 10
        info_width = max(0, toolbar_x - info_x - 12)
        self._info.setFixedWidth(info_width)
        self._info.move(info_x, height - 12 - self._info.height())
        self._chip.raise_()
        self._before_chip.raise_()
        self._after_chip.raise_()
        self._info.raise_()
        self._scale_button.raise_()
        self._toolbar.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        if self.compare is not None:
            self.compare.layout_strip()
        self._layout_overlays()

    @staticmethod
    def _canvas_native(viewer) -> QWidget | None:
        try:
            from spektrafilm_gui.napari_layout import viewer_canvas_native

            return viewer_canvas_native(viewer)
        except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
            return None

    # ── 事件 ────────────────────────────────────────────────────
    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt API name
        if self._zoom_controller is not None and event.type() == QtCore.QEvent.Wheel:
            angle = event.angleDelta()
            if angle.y() != 0:
                self._zoom_controller.wheel(int(angle.y()))
                event.accept()
                return True
        return super().eventFilter(obj, event)

    # ── 对比 ────────────────────────────────────────────────────
    def _on_compare_toggled(self, checked: bool) -> None:
        if checked:
            if self.compare is None or not self.compare.enter():
                self._compare_button.blockSignals(True)
                self._compare_button.setChecked(False)
                self._compare_button.blockSignals(False)
            return
        if self.compare is not None:
            self.compare.exit()

    def _on_compare_active(self, active: bool) -> None:
        self._compare_button.blockSignals(True)
        self._compare_button.setChecked(active)
        self._compare_button.blockSignals(False)
        self._chip.setVisible(not active)
        self._before_chip.setVisible(active)
        self._after_chip.setVisible(active)
        self._layout_overlays()

    def reset_compare(self) -> None:
        if self.compare is not None and self.compare.active:
            self.compare.exit()

    # ── 工具 ────────────────────────────────────────────────────
    def _tool_button(self, icon_name: str, tooltip: str, callback) -> QPushButton:
        button = QPushButton()
        button.setObjectName('iconButton')
        button.setIcon(shell_icons.icon(icon_name, TEXT_2, 15))
        button.setFixedSize(26, 24)
        button.setToolTip(tooltip)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(callback)
        return button

    def set_photo_info(self, item: LibraryItem) -> None:
        parts = [item.name]
        if item.width and item.height:
            parts.append(f'{item.width}×{item.height}')
        if item.film_stock:
            parts.append(film_display_name(item.film_stock))
        self._info.setText(' · '.join(parts))
        self._info.adjustSize()
        self._layout_overlays()

    def set_chip(self, text: str) -> None:
        self._chip.setText(text)
        self._chip.adjustSize()
        self._layout_overlays()

    def set_render_scale(self, scale: float) -> None:
        try:
            value = float(scale)
        except (TypeError, ValueError):
            return
        if value not in self._scale_actions:
            value = 1.0
        if value == self._render_scale:
            for action_value, action in self._scale_actions.items():
                action.setChecked(action_value == value)
            return
        self._render_scale = value
        for action_value, action in self._scale_actions.items():
            action.setChecked(action_value == value)
        self._scale_button.setText({1.0: '完整', 0.5: '1/2', 0.25: '1/4'}[value])
        self._layout_overlays()
        self.render_scale_changed.emit(value)

    def render_scale(self) -> float:
        return float(self._render_scale)

    def _rotate(self, direction: int) -> None:
        callback = getattr(self, '_on_rotate', None)
        if callable(callback):
            callback(direction)

    def _zoom(self, percent: int) -> None:
        if self._zoom_controller is not None:
            self._zoom_controller.animate_to(float(percent))
            return
        try:
            from spektrafilm_gui.napari_layout import set_viewer_zoom_percent

            set_viewer_zoom_percent(self._viewer, float(percent))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return

    def _fit(self) -> None:
        try:
            from spektrafilm_gui.napari_layout import reset_viewer_camera

            reset_viewer_camera(self._viewer)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return

    def set_rotate_callback(self, callback) -> None:
        self._on_rotate = callback


class FilmThumb(QFrame):
    clicked = Signal(str)

    def __init__(self, item: LibraryItem, image: QtGui.QImage | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('filmThumb')
        self.item_id = item.id
        self.setFixedSize(66, 66)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(item.name)
        self._selected = False
        self._thumb = ThumbnailView()
        self._thumb.set_raw(item.is_raw)
        self._thumb.set_missing(not item.exists)
        self._thumb.setFixedSize(58, 58)
        if image is not None and not image.isNull():
            self._thumb.set_image(image)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._thumb)

    def set_thumbnail(self, image: QtGui.QImage) -> None:
        self._thumb.set_image(image)
        self._thumb.set_missing(False)

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self.setProperty('selected', 'true' if selected else 'false')
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.item_id)
            event.accept()
            return
        super().mousePressEvent(event)


class Filmstrip(QWidget):
    item_clicked = Signal(str)
    add_requested = Signal()

    def __init__(self, thumbnails: ThumbnailService, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('filmstrip')
        self.setFixedHeight(88)
        self._thumbnails = thumbnails
        self._thumbs: dict[str, FilmThumb] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._strip = QWidget()
        self._strip_layout = QHBoxLayout(self._strip)
        self._strip_layout.setContentsMargins(10, 9, 10, 9)
        self._strip_layout.setSpacing(6)
        self._strip_layout.setAlignment(Qt.AlignLeft)
        self._scroll.setWidget(self._strip)
        layout.addWidget(self._scroll)

        thumbnails.thumbnail_ready.connect(self._on_thumbnail_ready)

    def set_items(self, items: list[LibraryItem], current_id: str) -> None:
        while self._strip_layout.count():
            layout_item = self._strip_layout.takeAt(0)
            if layout_item is not None:
                widget = layout_item.widget()
                if widget is not None:
                    widget.deleteLater()
        self._thumbs.clear()

        for item in items:
            image = self._thumbnails.cached(item.id)
            if image is None:
                image = self._thumbnails.request(item)
            thumb = FilmThumb(item, image)
            thumb.clicked.connect(self.item_clicked.emit)
            thumb.set_selected(item.id == current_id)
            self._thumbs[item.id] = thumb
            self._strip_layout.addWidget(thumb)

        add = QPushButton()
        add.setObjectName('filmAddThumb')
        add.setFixedSize(66, 66)
        add.setCursor(Qt.PointingHandCursor)
        add.setToolTip('导入照片')
        add.setIcon(shell_icons.icon('plus', TEXT_3, 20))
        add.setIconSize(QtCore.QSize(20, 20))
        add.clicked.connect(self.add_requested.emit)
        self._strip_layout.addWidget(add)
        self._strip_layout.addStretch(1)

        current = self._thumbs.get(current_id)
        if current is not None:
            def _ensure_current() -> None:
                try:
                    self._scroll.ensureWidgetVisible(current, 60, 0)
                except RuntimeError:
                    return

            QtCore.QTimer.singleShot(0, _ensure_current)

    def _on_thumbnail_ready(self, item_id: str, image: QtGui.QImage) -> None:
        thumb = self._thumbs.get(item_id)
        if thumb is not None:
            thumb.set_thumbnail(image)


class EditorPage(QWidget):
    back_requested = Signal()
    export_requested = Signal()
    export_settings_requested = Signal()
    quick_preview_requested = Signal()
    scan_requested = Signal()
    save_requested = Signal()
    favorite_toggled = Signal(bool)
    add_photos_requested = Signal()
    reset_requested = Signal()
    film_selected = Signal(str)
    paper_selected = Signal(str)
    strip_item_selected = Signal(str)
    preview_scale_changed = Signal(float)
    profile_changed = Signal(str, str)

    def __init__(
        self,
        viewer,
        viewer_widget: QWidget,
        widgets,
        controller,
        *,
        thumbnails: ThumbnailService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName('editorPage')
        self._viewer = viewer
        self._widgets = widgets
        self._controller = controller

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.top_bar = EditorTopBar()
        root.addWidget(self.top_bar)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)

        self.preset_rail = PresetRail()
        self.preview = PreviewStage(viewer, viewer_widget)
        self.inspector = ParameterDeck(widgets, controller)
        self.filmstrip = Filmstrip(thumbnails)

        center = QWidget()
        center.setObjectName('editorCenter')
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(self.preview, 1)
        center_layout.addWidget(self.filmstrip)

        splitter.addWidget(self.preset_rail)
        splitter.addWidget(center)
        splitter.addWidget(self.inspector)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([300, 900, 330])
        root.addWidget(splitter, 1)

        self.top_bar.back_requested.connect(self.back_requested.emit)
        self.top_bar.export_requested.connect(self.export_requested.emit)
        self.top_bar.export_settings_requested.connect(self.export_settings_requested.emit)
        self.top_bar.quick_preview_requested.connect(self.quick_preview_requested.emit)
        self.top_bar.scan_requested.connect(self.scan_requested.emit)
        self.top_bar.save_requested.connect(self.save_requested.emit)
        self.top_bar.favorite_toggled.connect(self.favorite_toggled.emit)
        self.inspector.reset_requested.connect(self.reset_requested.emit)
        self.inspector.profile_changed.connect(self.profile_changed.emit)
        self.preset_rail.film_selected.connect(self.film_selected.emit)
        self.preset_rail.paper_selected.connect(self.paper_selected.emit)
        self.filmstrip.item_clicked.connect(self.strip_item_selected.emit)
        self.filmstrip.add_requested.connect(self.add_photos_requested.emit)
        self.preview.set_rotate_callback(self._rotate)
        self.preview.render_scale_changed.connect(self.preview_scale_changed.emit)
        self.preview.render_requested.connect(self.quick_preview_requested.emit)
        try:
            self._widgets.simulation.scan_film.toggled.connect(self._refresh_chip)
        except AttributeError:
            pass

    def _rotate(self, direction: int) -> None:
        if direction < 0:
            self._controller.rotate_input_image_counterclockwise()
        else:
            self._controller.rotate_input_image_clockwise()

    def set_photo(self, item: LibraryItem, strip_items: list[LibraryItem]) -> None:
        self.preview.reset_compare()
        self.top_bar.set_photo(item)
        self.preview.set_photo_info(item)
        self.filmstrip.set_items(strip_items, item.id)
        self.preset_rail.set_current(item.film_stock, item.print_paper)
        self.inspector.refresh()
        self._refresh_chip()

    def set_strip_items(self, items: list[LibraryItem], current_id: str) -> None:
        self.filmstrip.set_items(items, current_id)

    def refresh_after_state_change(self) -> None:
        self.inspector.refresh()
        film = ''
        paper = ''
        try:
            film = str(self._widgets.simulation.film_stock.value)
            paper = str(self._widgets.simulation.print_paper.value)
        except AttributeError:
            pass
        self.preset_rail.set_current(film, paper)
        self._refresh_chip()

    def _refresh_chip(self, *_args) -> None:
        try:
            scan_film = bool(self._widgets.simulation.scan_film.value)
        except AttributeError:
            scan_film = False
        self.preview.set_chip('底片' if scan_film else '照片')

    def set_histogram(self, array) -> None:
        self.inspector.set_histogram(array)

    def set_simulation_busy(self, busy: bool, scale: float = 1.0) -> None:
        self.top_bar.set_simulation_busy(busy, scale)

    def set_simulation_progress(self, label: str, completed: int, total: int) -> None:
        self.top_bar.set_simulation_progress(label, completed, total)

    def set_favorite(self, favorite: bool) -> None:
        self.top_bar.set_favorite(favorite)
