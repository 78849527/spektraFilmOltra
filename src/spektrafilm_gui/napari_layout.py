from __future__ import annotations

import math
from importlib import import_module
import sys
from typing import TYPE_CHECKING, Callable
from typing import Any, cast

from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtCore import Qt

if TYPE_CHECKING:
    import napari

from spektrafilm_gui import motion

QFrame = QtWidgets.QFrame
QIcon = QtGui.QIcon
QMainWindow = QtWidgets.QMainWindow
QPushButton = QtWidgets.QPushButton
QStatusBar = QtWidgets.QStatusBar
QScrollArea = QtWidgets.QScrollArea
QWidget = QtWidgets.QWidget

from spektrafilm_gui.theme import APP_STYLE_SHEET
from spektrafilm_gui.theme_oflim import (
    ACCENT,
    ACCENT_ON,
    SIDEBAR_WIDTH,
    SURFACE_1,
    SURFACE_2,
    SURFACE_3,
    TEXT_2,
    TOP_BAR_HEIGHT,
)
from spektrafilm_gui.theme_palette import (
    GRAY_0,
    GRAY_18,
    SIZE_APP_MARGIN,
    SIZE_FOOTER_BOTTOM_INSET,
    SIZE_FOOTER_MIN_HEIGHT,
    SIZE_FOOTER_ITEM_SPACING,
    SIZE_FOOTER_TOP_SPACING,
    SIZE_PANEL_MARGIN,
    SIZE_SPLITTER_HANDLE_MARGIN_LEFT,
    SIZE_TAB_CONTENT_TOP_MARGIN,
)
from spektrafilm_gui.widgets import WidgetBundle
from spektrafilm_gui.widgets import CollapsibleSection, platform_default_font


DEFAULT_CONTROLS_PANEL_WIDTH = SIDEBAR_WIDTH
DEFAULT_VIEWER_SPLITTER_WIDTH = 1040
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19
class AppMainWindow(QMainWindow):
    """主窗口：除原有能力外，接收拖入的图片（oflim 式导入交互）。"""

    filesDropped = QtCore.Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self._viewer_status_bar: QStatusBar | None = None
        self._drop_overlay: QWidget | None = None
        self.setAcceptDrops(True)

    def set_viewer_status_bar(self, status_bar: QStatusBar) -> None:
        self._viewer_status_bar = status_bar

    def statusBar(self) -> QStatusBar:  # noqa: N802 - Qt API name
        if self._viewer_status_bar is not None:
            return self._viewer_status_bar
        return super().statusBar()

    # ── 拖放导入 ────────────────────────────────────────────────
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
        else:
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


class _DropOverlay(QWidget):
    """拖入时的整窗提示层，形态取自 oflim 的 DropOverlay。"""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setStyleSheet('background: rgba(11, 11, 11, 220);')

        card = QtWidgets.QFrame()
        card.setObjectName('dropCard')
        card.setFixedSize(340, 150)
        card.setStyleSheet(
            'QFrame#dropCard { background: #151515; border: 1px solid rgba(200,169,126,0.5); border-radius: 15px; }'
        )
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        card_layout.setSpacing(8)

        title = QtWidgets.QLabel('松开以导入图片')
        title_font = title.font()
        title_font.setPointSizeF(max(title_font.pointSizeF() + 2, 13.0))
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet('color: #FFFFFF; background: transparent; border: none;')

        hint = QtWidgets.QLabel('RAW · TIFF · PNG · JPEG · EXR')
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet('color: #8A8A82; background: transparent; border: none; letter-spacing: 1px;')

        card_layout.addWidget(title)
        card_layout.addWidget(hint)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card, 0, Qt.AlignCenter)

def _get_current_stylesheet() -> str:
    try:
        return str(import_module('napari.qt').get_current_stylesheet())
    except (ImportError, AttributeError):
        return ''


def _request_dark_title_bar(window: QWidget) -> bool:
    if sys.platform != 'win32':
        return False

    try:
        hwnd = int(window.winId())
    except (AttributeError, TypeError, ValueError):
        return False

    if hwnd == 0:
        return False

    try:
        ctypes = import_module('ctypes')
        dwmapi = ctypes.windll.dwmapi
        set_window_attribute = dwmapi.DwmSetWindowAttribute
    except (ImportError, AttributeError):
        return False

    value = ctypes.c_int(1)
    value_size = ctypes.sizeof(value)
    for attribute in (_DWMWA_USE_IMMERSIVE_DARK_MODE, _DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1):
        try:
            result = set_window_attribute(hwnd, attribute, ctypes.byref(value), value_size)
        except (OSError, AttributeError, TypeError, ValueError):
            continue
        if result == 0:
            return True
    return False
def _canvas_background_color(*, gray_18_canvas: bool) -> str:
    return GRAY_18 if gray_18_canvas else GRAY_0


def set_canvas_background(viewer: napari.Viewer, *, gray_18_canvas: bool) -> None:
    background = _canvas_background_color(gray_18_canvas=gray_18_canvas)

    viewer_window = getattr(viewer, 'window', None)
    if viewer_window is None:
        return

    qt_viewer = getattr(viewer_window, '_qt_viewer', None)
    if qt_viewer is None:
        return

    if hasattr(qt_viewer, 'setStyleSheet'):
        qt_viewer.setStyleSheet(f'background: {background};')

    canvas = getattr(qt_viewer, 'canvas', None)
    if canvas is not None:
        if hasattr(canvas, 'bgcolor'):
            setattr(canvas, 'bgcolor', background)
        native = getattr(canvas, 'native', None)
        if native is not None and hasattr(native, 'setStyleSheet'):
            native.setStyleSheet(f'background: {background};')


def configure_napari_chrome(viewer: napari.Viewer, *, gray_18_canvas: bool = True) -> None:
    qt_window = getattr(viewer.window, '_qt_window', None)
    if qt_window is not None:
        menu_bar = qt_window.menuBar()
        if menu_bar is not None:
            menu_bar.hide()

    qt_viewer = getattr(viewer.window, '_qt_viewer', None)
    if qt_viewer is None:
        return

    set_canvas_background(viewer, gray_18_canvas=gray_18_canvas)

    set_welcome_visible = getattr(qt_viewer, 'set_welcome_visible', None)
    if callable(set_welcome_visible):
        set_welcome_visible(False)

    layer_controls = getattr(qt_viewer, 'dockLayerControls', None)
    if layer_controls is not None:
        layer_controls.hide()

    layer_list = getattr(qt_viewer, 'dockLayerList', None)
    if layer_list is not None:
        layer_list.hide()


def set_host_window(viewer: napari.Viewer, host_window: QWidget) -> None:
    viewer_window = getattr(viewer, 'window', None)
    if viewer_window is not None:
        setattr(viewer_window, '_agx_host_window', host_window)


def _host_window(viewer: napari.Viewer) -> QWidget | None:
    viewer_window = getattr(viewer, 'window', None)
    if viewer_window is None:
        return None
    host_window = getattr(viewer_window, '_agx_host_window', None)
    if host_window is not None:
        return host_window
    qt_window = getattr(viewer_window, '_qt_window', None)
    if qt_window is not None:
        return qt_window
    return None


def take_viewer_widget(viewer: napari.Viewer) -> QWidget:
    viewer_window = getattr(viewer, 'window', None)
    if viewer_window is None:
        raise RuntimeError('Napari viewer window is not available')

    qt_window = getattr(viewer_window, '_qt_window', None)
    if qt_window is not None:
        take_central_widget = getattr(qt_window, 'takeCentralWidget', None)
        if callable(take_central_widget):
            central_widget = take_central_widget()
            if central_widget is not None:
                return central_widget

    qt_viewer = getattr(viewer_window, '_qt_viewer', None)
    if qt_viewer is not None:
        return qt_viewer
    raise RuntimeError('Napari Qt viewer widget is not available')


def _wrap_scrollable(widget: QWidget) -> QScrollArea:
    scroll = QtWidgets.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setSizeAdjustPolicy(QScrollArea.AdjustIgnored)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setFrameShape(QFrame.NoFrame)
    # 内容跟随视口铺满，避免卡片右侧留出一条空带
    widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
    scroll.setWidget(widget)
    return scroll


def _build_top_bar() -> QWidget:
    """oflim 形态的品牌条：黄铜点 + 字标，右侧一行状态。"""
    bar = QtWidgets.QWidget()
    bar.setObjectName('appTopBar')
    bar.setFixedHeight(TOP_BAR_HEIGHT)

    content = QtWidgets.QWidget()
    content.setObjectName('appTopBar')
    row = QtWidgets.QHBoxLayout(content)
    row.setContentsMargins(16, 0, 16, 0)
    row.setSpacing(7)

    dot = QtWidgets.QLabel('●')
    dot.setObjectName('brandDot')
    wordmark = QtWidgets.QLabel('SPEKTRAFILM')
    wordmark.setObjectName('brandWordmark')
    status = QtWidgets.QLabel('光谱胶片模拟')
    status.setObjectName('topBarStatus')

    row.addWidget(dot, 0, Qt.AlignVCenter)
    row.addWidget(wordmark, 0, Qt.AlignVCenter)
    row.addStretch(1)
    row.addWidget(status, 0, Qt.AlignVCenter)

    divider = QtWidgets.QFrame()
    divider.setObjectName('topBarDivider')
    divider.setFixedHeight(1)

    layout = QtWidgets.QVBoxLayout(bar)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(content, 1)
    layout.addWidget(divider)
    return bar


def _build_inspector_header(on_reset=None) -> QWidget:
    """侧栏页眉：标题 + 右侧重置入口（oflim 的 header 动作形态）。"""
    header = QtWidgets.QWidget()
    header.setObjectName('inspectorHeader')
    header.setFixedHeight(50)

    row = QtWidgets.QHBoxLayout(header)
    row.setContentsMargins(14, 0, 14, 0)
    row.setSpacing(6)

    eyebrow = QtWidgets.QLabel('显影')
    eyebrow.setObjectName('inspectorEyebrow')
    version = QtWidgets.QLabel('v0.3.4')
    version.setObjectName('inspectorCount')

    row.addWidget(eyebrow, 0, Qt.AlignVCenter)
    row.addStretch(1)
    if on_reset is not None:
        reset_button = QPushButton('重置')
        reset_button.setObjectName('headerResetButton')
        reset_button.setToolTip('把全部参数恢复为出厂默认（含载入的启动配置）')
        reset_button.setCursor(Qt.PointingHandCursor)
        reset_button.clicked.connect(on_reset)
        row.addWidget(reset_button, 0, Qt.AlignVCenter)
    row.addWidget(version, 0, Qt.AlignVCenter)
    return header


def _build_sidebar(controls_panel: QWidget, *, on_reset_default=None) -> QFrame:
    sidebar = QtWidgets.QFrame()
    sidebar.setObjectName('sidebarPanel')

    layout = QtWidgets.QVBoxLayout(sidebar)
    layout.setContentsMargins(SIZE_PANEL_MARGIN, SIZE_PANEL_MARGIN, SIZE_PANEL_MARGIN, SIZE_FOOTER_BOTTOM_INSET)
    layout.setSpacing(0)
    layout.addWidget(_build_inspector_header(on_reset=on_reset_default))
    layout.addWidget(controls_panel, 1)
    return sidebar


def _build_controls_tab(*widgets: QWidget) -> QWidget:
    """oflim 版式：一个分页 = 一张大卡，卡内是若干扁平参数组。"""
    tab = QtWidgets.QWidget()
    outer = QtWidgets.QVBoxLayout(tab)
    outer.setContentsMargins(0, SIZE_TAB_CONTENT_TOP_MARGIN, 0, 0)
    outer.setSpacing(0)
    outer.setAlignment(Qt.AlignTop)

    card = QtWidgets.QFrame()
    card.setObjectName('tabCard')
    card_layout = QtWidgets.QVBoxLayout(card)
    card_layout.setContentsMargins(4, 10, 4, 10)
    card_layout.setSpacing(2)
    card_layout.setAlignment(Qt.AlignTop)

    for widget in widgets:
        for section in _sections_in(widget):
            section.set_flat(True)
        card_layout.addWidget(widget)

    outer.addWidget(card)
    return tab


def _sections_in(widget: QWidget) -> list[QWidget]:
    from spektrafilm_gui.widget_primitives import CollapsibleSection

    sections = list(widget.findChildren(CollapsibleSection))
    if isinstance(widget, CollapsibleSection):
        sections.insert(0, widget)
    return sections


def _borrow_layer_list_widget(viewer: napari.Viewer) -> QWidget | None:
    qt_viewer = getattr(viewer.window, '_qt_viewer', None)
    layer_list = getattr(qt_viewer, 'dockLayerList', None) if qt_viewer is not None else None
    if layer_list is None or not hasattr(layer_list, 'widget'):
        return None
    widget = layer_list.widget()
    if isinstance(widget, QWidget):
        # napari 自带控件走系统调色板，递归把选中色统一到黄铜，避免跳出蓝色高亮
        _apply_oflim_palette(widget)
        widget.setStyleSheet(_get_current_stylesheet())
    return widget


def _apply_oflim_palette(root: QWidget) -> None:
    palette = root.palette()
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(ACCENT))
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(ACCENT_ON))
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(SURFACE_2))
    palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(SURFACE_3))
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(SURFACE_1))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(TEXT_2))
    palette.setColor(QtGui.QPalette.Text, QtGui.QColor(TEXT_2))
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor(SURFACE_2))
    palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(TEXT_2))
    root.setPalette(palette)
    for child in root.findChildren(QWidget):
        child.setPalette(palette)


def reset_viewer_camera(viewer: napari.Viewer) -> None:
    reset_view = getattr(viewer, 'reset_view', None)
    if callable(reset_view):
        reset_view()


def _viewer_device_pixel_ratio(viewer: napari.Viewer) -> float:
    viewer_window = getattr(viewer, 'window', None)
    qt_viewer = getattr(viewer_window, '_qt_viewer', None)
    if qt_viewer is None:
        return 1.0

    device_pixel_ratio = getattr(qt_viewer, 'devicePixelRatioF', None)
    if callable(device_pixel_ratio):
        try:
            return max(float(device_pixel_ratio()), 0.01)
        except (TypeError, ValueError):
            return 1.0

    if hasattr(qt_viewer, 'devicePixelRatio'):
        try:
            return max(float(qt_viewer.devicePixelRatio()), 0.01)
        except (TypeError, ValueError):
            return 1.0

    return 1.0


def _layer_pixel_world_size(layer: object | None) -> float:
    if layer is None:
        return 1.0

    scale = getattr(layer, 'scale', None)
    if scale is None:
        return 1.0

    if isinstance(scale, (int, float)):
        try:
            return max(abs(float(scale)), 1e-12)
        except (TypeError, ValueError):
            return 1.0

    try:
        scale_values = tuple(scale)
    except TypeError:
        return 1.0

    axis_scales: list[float] = []
    for value in scale_values[:2]:
        try:
            numeric_value = abs(float(value))
        except (TypeError, ValueError):
            continue
        if numeric_value > 0.0:
            axis_scales.append(numeric_value)

    if not axis_scales:
        return 1.0
    return sum(axis_scales) / len(axis_scales)


def _home_view_target_layer(viewer: napari.Viewer) -> object | None:
    layers = getattr(viewer, 'layers', None)
    if layers is None:
        return None

    selection = getattr(layers, 'selection', None)
    active_layer = getattr(selection, 'active', None)
    if active_layer is not None and getattr(active_layer, 'visible', True):
        return active_layer

    for layer in reversed(list(layers)):
        if getattr(layer, 'visible', True):
            return layer
    return None


def _viewer_camera(viewer: napari.Viewer):
    camera = getattr(viewer, 'camera', None)
    if camera is not None:
        return camera
    viewer_window = getattr(viewer, 'window', None)
    return getattr(viewer_window, 'camera', None)


def viewer_zoom_percent(viewer: napari.Viewer) -> float:
    """当前视角对应的 100% 制缩放（100 = 屏幕 1:1），与按钮语义一致。"""
    camera = _viewer_camera(viewer)
    if camera is None or not hasattr(camera, 'zoom'):
        return 100.0
    try:
        zoom = float(camera.zoom)
    except (TypeError, ValueError):
        return 100.0
    pixel_ratio = _viewer_device_pixel_ratio(viewer)
    layer_pixel_world_size = _layer_pixel_world_size(_home_view_target_layer(viewer))
    return zoom * layer_pixel_world_size / max(pixel_ratio, 0.01) * 100.0


def viewer_canvas_native(viewer: napari.Viewer) -> QWidget | None:
    """vispy 画布的原生 Qt 控件（滚轮拦截挂在这里）。"""
    viewer_window = getattr(viewer, 'window', None)
    qt_viewer = getattr(viewer_window, '_qt_viewer', None)
    canvas = getattr(qt_viewer, 'canvas', None)
    return getattr(canvas, 'native', None)


class ViewerZoomController(QtCore.QObject):
    """滚轮 / 按钮缩放的阻尼动画：目标百分比指数跟随，缩放始终平滑。

    滚轮事件由外部拦截后调用 wheel()；按钮调用 animate_to()。
    """

    MIN_PERCENT = 4.0
    MAX_PERCENT = 3200.0
    WHEEL_SHARPNESS = 700.0  # angleDelta 每 120 一格 → e^(120/700) ≈ 1.19 倍

    def __init__(self, viewer: napari.Viewer, *, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self._viewer = viewer
        self._target = viewer_zoom_percent(viewer)
        self._follow = motion.FollowValue(self, rate=10.0)
        self._follow.valueChanged.connect(self._on_follow)

    @property
    def target(self) -> float:
        return self._target

    def animate_to(self, percent: float) -> None:
        self._target = min(max(float(percent), self.MIN_PERCENT), self.MAX_PERCENT)
        self._follow.move_to(self._target)

    def wheel(self, angle_y: int) -> None:
        factor = math.exp(float(angle_y) / self.WHEEL_SHARPNESS)
        self.animate_to(self._target * factor)

    def _on_follow(self, value: float) -> None:
        set_viewer_zoom_percent(self._viewer, value)


def set_viewer_zoom_percent(viewer: napari.Viewer, percent: float) -> None:
    viewer_window = getattr(viewer, 'window', None)
    camera = getattr(viewer, 'camera', None)
    if camera is None:
        camera = getattr(viewer_window, 'camera', None)
    if camera is None or not hasattr(camera, 'zoom'):
        return

    pixel_ratio = _viewer_device_pixel_ratio(viewer)
    target_layer = _home_view_target_layer(viewer)
    layer_pixel_world_size = _layer_pixel_world_size(target_layer)
    zoom_scale = max(0.0, float(percent)) / 100.0
    camera.zoom = max((pixel_ratio * zoom_scale) / layer_pixel_world_size, pixel_ratio * 0.01)


def _build_viewer_panel(
    viewer_widget: QWidget,
    status_bar: QStatusBar,
    *,
    on_rotate_ccw: Callable[[], None] | None = None,
    on_rotate_cw: Callable[[], None] | None = None,
    on_zoom_100: Callable[[], None] | None = None,
    on_zoom_200: Callable[[], None] | None = None,
    on_zoom_400: Callable[[], None] | None = None,
    on_home_view: Callable[[], None] | None = None,
) -> QFrame:
    panel = QtWidgets.QFrame()
    panel.setObjectName('viewerPanel')
    divider_gap = int(SIZE_SPLITTER_HANDLE_MARGIN_LEFT.removesuffix('px'))

    status_container = QtWidgets.QWidget()
    status_layout = QtWidgets.QHBoxLayout(status_container)
    status_layout.setContentsMargins(0, 0, 0, 0)
    status_layout.setSpacing(SIZE_FOOTER_ITEM_SPACING)
    status_bar.setContentsMargins(0, 0, 0, 0)
    status_bar.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
    status_layout.addWidget(status_bar, 1)

    rotate_ccw_button = QPushButton('逆时针')
    rotate_ccw_button.setObjectName('rotateCcwButton')
    if on_rotate_ccw is not None:
        rotate_ccw_button.clicked.connect(on_rotate_ccw)

    rotate_cw_button = QPushButton('顺时针')
    rotate_cw_button.setObjectName('rotateCwButton')
    if on_rotate_cw is not None:
        rotate_cw_button.clicked.connect(on_rotate_cw)

    zoom_100_button = QPushButton('100%')
    zoom_100_button.setObjectName('zoom100Button')
    zoom_100_button.setToolTip('屏幕像素与图像像素 1:1 对应')
    if on_zoom_100 is not None:
        zoom_100_button.clicked.connect(on_zoom_100)

    zoom_200_button = QPushButton('200%')
    zoom_200_button.setObjectName('zoom200Button')
    zoom_200_button.setToolTip('2 个屏幕像素对应 1 个图像像素')
    if on_zoom_200 is not None:
        zoom_200_button.clicked.connect(on_zoom_200)

    zoom_400_button = QPushButton('400%')
    zoom_400_button.setObjectName('zoom400Button')
    zoom_400_button.setToolTip('4 个屏幕像素对应 1 个图像像素')
    if on_zoom_400 is not None:
        zoom_400_button.clicked.connect(on_zoom_400)

    home_button = QPushButton('适应窗口')
    home_button.setObjectName('homeViewButton')
    if on_home_view is not None:
        home_button.clicked.connect(on_home_view)
    row_height = int(SIZE_FOOTER_MIN_HEIGHT.removesuffix('px'))
    rotate_ccw_button.setFixedHeight(row_height)
    rotate_cw_button.setFixedHeight(row_height)
    zoom_100_button.setFixedHeight(row_height)
    zoom_200_button.setFixedHeight(row_height)
    zoom_400_button.setFixedHeight(row_height)
    home_button.setFixedHeight(row_height)
    status_bar.setFixedHeight(row_height)
    status_container.setFixedHeight(row_height)
    status_layout.addWidget(rotate_ccw_button)
    status_layout.addWidget(rotate_cw_button)
    status_layout.addWidget(zoom_100_button)
    status_layout.addWidget(zoom_200_button)
    status_layout.addWidget(zoom_400_button)
    status_layout.addWidget(home_button)

    layout = QtWidgets.QVBoxLayout(panel)
    layout.setContentsMargins(SIZE_PANEL_MARGIN, SIZE_PANEL_MARGIN, divider_gap, SIZE_FOOTER_BOTTOM_INSET)
    layout.setSpacing(0)
    layout.addWidget(viewer_widget, 1)
    layout.addSpacing(SIZE_FOOTER_TOP_SPACING)
    layout.addWidget(status_container)
    return panel


def build_controls_panel(viewer: napari.Viewer, widgets: WidgetBundle) -> QWidget:
    """oflim 版式的 inspector：身份卡 → 分页参数 → 动作栏。

    分页按暗房流程重排（EXPOSE / FILM / PRINT / OUTPUT / CONFIG），
    与 oflim 用「处理阶段」切分页面的逻辑一致。
    """
    panel = QtWidgets.QTabWidget()
    panel.setObjectName('controlsTabWidget')
    panel.setDocumentMode(True)
    panel.setUsesScrollButtons(False)
    panel.tabBar().setDrawBase(False)
    panel.addTab(
        _wrap_scrollable(
            _build_controls_tab(
                widgets.filepicker,
                widgets.load_raw,
                widgets.preview_crop,
                widgets.input_image,
                widgets.camera,
                widgets.exposure_control,
            ),
        ),
        '曝光',
    )
    panel.addTab(
        _wrap_scrollable(_build_controls_tab(widgets.halation, widgets.couplers, widgets.grain, widgets.camera_diffusion)),
        '胶片',
    )
    panel.addTab(
        _wrap_scrollable(
            _build_controls_tab(
                widgets.enlarger,
                widgets.chemistry,
                widgets.glare,
                widgets.preflashing,
                widgets.enlarger_diffusion,
                widgets.scanner,
            ),
        ),
        '印相',
    )
    panel.addTab(
        _wrap_scrollable(
            _build_controls_tab(
                widgets.output,
                widgets.spectral_upsampling,
                widgets.input_gamut_compress,
                widgets.output_gamut_compress,
                widgets.tune,
                widgets.special,
            ),
        ),
        '输出',
    )

    napari_layers_content = QtWidgets.QWidget()
    napari_layers_content_layout = QtWidgets.QVBoxLayout(napari_layers_content)
    napari_layers_content_layout.setContentsMargins(0, 0, 0, 0)
    napari_layers_content_layout.setSpacing(6)

    layer_list_widget = _borrow_layer_list_widget(viewer)
    if layer_list_widget is not None:
        napari_layers_content_layout.addWidget(layer_list_widget)

    panel.addTab(
        _wrap_scrollable(
            _build_controls_tab(
                widgets.gui_config,
                widgets.display,
                CollapsibleSection('napari layers', napari_layers_content, expanded=False),
            ),
        ),
        '配置',
    )

    container = QtWidgets.QWidget()
    container_layout = QtWidgets.QVBoxLayout(container)
    container_layout.setContentsMargins(12, 12, 12, 0)
    container_layout.setSpacing(10)
    look_card = getattr(widgets.simulation, 'look_card', None)
    if look_card is not None:
        container_layout.addWidget(look_card)
    container_layout.addWidget(panel, 1)
    container_layout.addWidget(widgets.simulation.action_bar())

    return container


def build_main_window(
    viewer: napari.Viewer,
    controls_panel: QWidget,
    *,
    on_rotate_ccw: Callable[[], None] | None = None,
    on_rotate_cw: Callable[[], None] | None = None,
    on_reset_default: Callable[[], None] | None = None,
) -> QMainWindow:
    viewer_widget = take_viewer_widget(viewer)
    status_bar = QtWidgets.QStatusBar()
    status_bar.setSizeGripEnabled(False)

    main_window = AppMainWindow()
    main_window.setWindowTitle('spektrafilm')
    main_window.setWindowIcon(QIcon())
    main_window.resize(DEFAULT_CONTROLS_PANEL_WIDTH + DEFAULT_VIEWER_SPLITTER_WIDTH, 980)
    main_window.setFont(platform_default_font())
    main_window.setStyleSheet(APP_STYLE_SHEET)
    main_window.set_viewer_status_bar(status_bar)
    set_host_window(viewer, main_window)

    splitter = QtWidgets.QSplitter(Qt.Horizontal)
    splitter.setChildrenCollapsible(False)
    splitter.addWidget(
        _build_viewer_panel(
            viewer_widget,
            status_bar,
            on_rotate_ccw=on_rotate_ccw,
            on_rotate_cw=on_rotate_cw,
            on_zoom_100=lambda: set_viewer_zoom_percent(viewer, 100.0),
            on_zoom_200=lambda: set_viewer_zoom_percent(viewer, 200.0),
            on_zoom_400=lambda: set_viewer_zoom_percent(viewer, 400.0),
            on_home_view=lambda: reset_viewer_camera(viewer),
        )
    )
    splitter.addWidget(_build_sidebar(controls_panel, on_reset_default=on_reset_default))
    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(1, 0)
    splitter.setSizes([DEFAULT_VIEWER_SPLITTER_WIDTH, DEFAULT_CONTROLS_PANEL_WIDTH])

    central = QtWidgets.QWidget()
    central.setObjectName('appCentral')
    central_layout = QtWidgets.QVBoxLayout(central)
    central_layout.setContentsMargins(SIZE_APP_MARGIN, SIZE_APP_MARGIN, SIZE_APP_MARGIN, SIZE_APP_MARGIN)
    central_layout.setSpacing(0)
    central_layout.addWidget(_build_top_bar())
    central_layout.addWidget(splitter, 1)

    main_window.setCentralWidget(central)
    _request_dark_title_bar(main_window)
    main_window.statusBar().showMessage('就绪', 3000)
    return main_window


def dialog_parent(viewer: napari.Viewer) -> QWidget | None:
    return _host_window(viewer)


def set_status(viewer: napari.Viewer, message: str, *, timeout_ms: int = 5000) -> None:
    host_window = cast(Any, _host_window(viewer))
    if host_window is None:
        return
    status_bar = host_window.statusBar() if hasattr(host_window, 'statusBar') else None
    if status_bar is not None:
        status_bar.showMessage(message, timeout_ms)


def show_viewer_window(viewer: napari.Viewer) -> None:
    host_window = _host_window(viewer)
    if host_window is not None and hasattr(host_window, 'show'):
        host_window.show()

    app = QtWidgets.QApplication.instance()
    if app is None:
        return

    active_window = app.activeWindow()
    if active_window is not None:
        active_window.showMaximized()
        return

    for window in reversed(app.topLevelWidgets()):
        if window.isVisible():
            window.showMaximized()
            return