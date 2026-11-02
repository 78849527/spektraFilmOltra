"""原片对比：可拖分隔线，左侧原片、右侧显影。

实现：把原片复制成一张带列式 alpha 遮罩的 RGBA 图层叠在显影层之上。
拖动分隔线时原地改写 alpha 列再 refresh()，不做全图重算；
相机平移/缩放由 33ms 轮询把分隔线投影回画布，保持线与像素边界对齐。
不碰控制器与渲染管线，退出时恢复所有图层可见性。
"""

from __future__ import annotations

from qtpy import QtCore, QtGui, QtWidgets

from spektrafilm_gui.controller_layers import (
    INPUT_PREVIEW_LAYER_NAME,
    OUTPUT_LAYER_NAME,
    WATERMARK_LAYER_NAME,
    WHITE_BORDER_LAYER_NAME,
)
from spektrafilm_gui.theme_oflim import ACCENT

Qt = QtCore.Qt

COMPARE_LAYER_NAME = 'compare_original'
STRIP_WIDTH = 36
HANDLE_RADIUS = 13.0
EDGE_KEEP_RATIO = 0.03  # 分隔线距画布边的最小余量


def _viewer_camera(viewer):
    camera = getattr(viewer, 'camera', None)
    if camera is not None:
        return camera
    return getattr(getattr(viewer, 'window', None), 'camera', None)


def _image_layer(viewer, name: str):
    layers = getattr(viewer, 'layers', None)
    if layers is None:
        return None
    for layer in layers:
        if getattr(layer, 'name', None) == name:
            return layer
    return None


class CompareOverlay(QtWidgets.QWidget):
    """画布上的分隔条：细黄铜线 + 圆形把手。只拦截条带附近的鼠标。"""

    drag_requested = QtCore.Signal(float)  # 画布 x（逻辑像素）

    def __init__(self, parent: QtWidgets.QWidget):
        super().__init__(parent)
        self.setFixedWidth(STRIP_WIDTH)
        self.setCursor(Qt.SizeHorCursor)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._dragging = False

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            cx = self.width() / 2.0
            height = self.height()

            line = QtGui.QPen(QtGui.QColor(ACCENT), 1.2)
            painter.setPen(line)
            painter.drawLine(QtCore.QPointF(cx, 0.0), QtCore.QPointF(cx, height))

            cy = height / 2.0
            center = QtCore.QPointF(cx, cy)
            # 把手：深色底盘 + 黄铜环 + 左右箭头
            painter.setPen(Qt.NoPen)
            painter.setBrush(QtGui.QColor(11, 11, 11, 216))
            painter.drawEllipse(center, HANDLE_RADIUS, HANDLE_RADIUS)
            painter.setPen(QtGui.QPen(QtGui.QColor(ACCENT), 1.2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, HANDLE_RADIUS, HANDLE_RADIUS)

            painter.setPen(QtGui.QPen(QtGui.QColor(ACCENT), 1.6))
            painter.setBrush(QtGui.QColor(ACCENT))
            arrow = 4.0
            gap = 3.4
            for direction in (-1.0, 1.0):
                tip_x = cx + direction * (gap + arrow)
                back_x = cx + direction * gap
                path = QtGui.QPainterPath()
                path.moveTo(tip_x, cy)
                path.lineTo(back_x, cy - arrow * 0.85)
                path.lineTo(back_x, cy + arrow * 0.85)
                path.closeSubpath()
                painter.drawPath(path)
        finally:
            painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self.drag_requested.emit(self._canvas_x(event.position().x()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._dragging:
            self.drag_requested.emit(self._canvas_x(event.position().x()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._dragging:
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _canvas_x(self, local_x: float) -> float:
        return self.x() + float(local_x)


class CompareSession(QtCore.QObject):
    """一次对比会话：建层、改遮罩、投影同步、退出恢复。"""

    active_changed = QtCore.Signal(bool)

    def __init__(self, viewer, canvas: QtWidgets.QWidget, *, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self._viewer = viewer
        self._canvas = canvas
        self._active = False
        self._rgba = None
        self._layer = None
        self._saved_visibility: dict[str, bool] = {}
        self._ratio = 0.5
        self._strip = CompareOverlay(canvas)
        self._strip.hide()
        self._strip.drag_requested.connect(self.set_ratio_from_canvas_x)
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._sync)

    # ── 生命周期 ────────────────────────────────────────────────
    @property
    def active(self) -> bool:
        return self._active

    def is_available(self) -> bool:
        preview = _image_layer(self._viewer, INPUT_PREVIEW_LAYER_NAME)
        output = _image_layer(self._viewer, OUTPUT_LAYER_NAME)
        return preview is not None and output is not None

    def enter(self) -> bool:
        if self._active:
            return True
        preview = _image_layer(self._viewer, INPUT_PREVIEW_LAYER_NAME)
        if preview is None or not self.is_available():
            return False
        rgba = self._build_rgba(preview)
        if rgba is None:
            return False

        layer = None
        try:
            viewer = self._viewer
            existing = _image_layer(viewer, COMPARE_LAYER_NAME)
            if existing is not None:
                layer = existing
                layer.data = rgba
            else:
                layer = viewer.add_image(rgba, name=COMPARE_LAYER_NAME, blending='translucent')
            layer.scale = tuple(getattr(preview, 'scale', (1.0, 1.0)))
            layer.translate = tuple(getattr(preview, 'translate', (0.0, 0.0)))
            layer.visible = True
            self._raise_to_top(layer)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

        self._rgba = rgba
        self._layer = layer
        self._saved_visibility = {}
        for name in (WHITE_BORDER_LAYER_NAME, WATERMARK_LAYER_NAME):
            saved = _image_layer(self._viewer, name)
            if saved is not None:
                self._saved_visibility[name] = bool(saved.visible)
                try:
                    saved.visible = False
                except (AttributeError, RuntimeError):
                    pass

        self._active = True
        self._ratio = 0.5
        self._apply_ratio()
        self._strip.show()
        self._strip.raise_()
        self._timer.start()
        self.active_changed.emit(True)
        return True

    def exit(self) -> None:
        if not self._active:
            return
        self._timer.stop()
        self._strip.hide()
        if self._layer is not None:
            try:
                self._viewer.layers.remove(self._layer)
            except (ValueError, AttributeError, RuntimeError):
                pass
        self._layer = None
        self._rgba = None
        for name, visible in self._saved_visibility.items():
            saved = _image_layer(self._viewer, name)
            if saved is not None:
                try:
                    saved.visible = visible
                except (AttributeError, RuntimeError):
                    pass
        self._saved_visibility = {}
        self._active = False
        self.active_changed.emit(False)

    # ── 几何 ────────────────────────────────────────────────────
    def set_ratio_from_canvas_x(self, canvas_x: float) -> None:
        if not self._active:
            return
        width = max(float(self._canvas.width()), 1.0)
        margin = width * EDGE_KEEP_RATIO
        clamped = min(max(float(canvas_x), margin), width - margin)
        self._ratio = clamped / width
        self._apply_ratio()
        self._sync_strip()

    def layout_strip(self) -> None:
        """画布尺寸变化后重放分隔条位置。"""
        if not self._active:
            return
        self._sync_strip()

    def _apply_ratio(self) -> None:
        layer = self._layer
        rgba = self._rgba
        if layer is None or rgba is None:
            return
        try:
            width = rgba.shape[1]
            column = self._split_column(width)
            alpha = rgba[..., 3]
            alpha[:, :] = 0.0
            if column > 0:
                alpha[:, :column] = 1.0
            layer.refresh()
        except (AttributeError, RuntimeError, TypeError, ValueError, IndexError):
            return

    def _split_column(self, width: int) -> int:
        column = int(round(self._ratio * width))
        return min(max(column, 0), width - 1)

    # ── 相机投影 ────────────────────────────────────────────────
    def _logical_per_world(self) -> float | None:
        camera = _viewer_camera(self._viewer)
        if camera is None or not hasattr(camera, 'zoom'):
            return None
        try:
            zoom = float(camera.zoom)
        except (TypeError, ValueError):
            return None
        ratio = 1.0
        qt_viewer = getattr(getattr(self._viewer, 'window', None), '_qt_viewer', None)
        dpr = getattr(qt_viewer, 'devicePixelRatioF', None)
        if callable(dpr):
            try:
                ratio = max(float(dpr()), 0.01)
            except (TypeError, ValueError):
                ratio = 1.0
        return zoom / ratio

    def _center_world_x(self) -> float:
        camera = _viewer_camera(self._viewer)
        center = getattr(camera, 'center', (0.0, 0.0))
        try:
            return float(center[-1])
        except (TypeError, ValueError, IndexError):
            return 0.0

    def _world_x_for_canvas(self, canvas_x: float) -> float | None:
        scale = self._logical_per_world()
        if scale is None or scale <= 0:
            return None
        width = max(float(self._canvas.width()), 1.0)
        return self._center_world_x() + (canvas_x - width / 2.0) / scale

    def _canvas_x_for_world(self, world_x: float) -> float | None:
        scale = self._logical_per_world()
        if scale is None or scale <= 0:
            return None
        width = max(float(self._canvas.width()), 1.0)
        return (world_x - self._center_world_x()) * scale + width / 2.0

    # ── 轮询同步 ────────────────────────────────────────────────
    def _sync(self) -> None:
        if not self._active:
            return
        layer = self._layer
        if layer is None or _image_layer(self._viewer, COMPARE_LAYER_NAME) is None:
            self.exit()
            return
        if not self.is_available():
            self.exit()
            return
        try:
            if self._viewer.layers and self._viewer.layers[-1] is not layer:
                self._raise_to_top(layer)
        except (AttributeError, RuntimeError, TypeError):
            pass
        self._sync_strip()

    def _sync_strip(self) -> None:
        layer = self._layer
        if layer is None:
            return
        try:
            width = int(round(layer.data.shape[1]))
            world = layer.data_to_world((0.0, float(self._split_column(width))))
            world_x = float(world[-1])
        except (AttributeError, RuntimeError, TypeError, ValueError, IndexError):
            return
        canvas_x = self._canvas_x_for_world(world_x)
        if canvas_x is None:
            return
        strip = self._strip
        x = int(round(canvas_x - strip.width() / 2.0))
        x = min(max(x, 0), max(int(self._canvas.width()) - strip.width(), 0))
        if strip.x() != x:
            strip.move(x, 0)
        if strip.height() != self._canvas.height():
            strip.setFixedHeight(self._canvas.height())

    def _raise_to_top(self, layer) -> None:
        layers = self._viewer.layers
        try:
            index = layers.index(layer)
            top = len(layers) - 1
            if index != top:
                layers.move(index, top)
        except (ValueError, AttributeError, RuntimeError):
            return

    @staticmethod
    def _build_rgba(preview) -> 'object | None':
        import numpy as np

        try:
            data = np.asarray(preview.data)
        except (AttributeError, TypeError):
            return None
        if data.ndim < 2:
            return None
        if data.ndim == 2:
            rgb = np.repeat(data[..., None], 3, axis=2)
        else:
            rgb = data[..., :3]
        if np.issubdtype(rgb.dtype, np.integer):
            info = np.iinfo(rgb.dtype)
            frame = rgb.astype(np.float32) / float(max(int(info.max), 1))
        else:
            frame = np.clip(rgb.astype(np.float32), 0.0, 1.0)
        alpha = np.zeros(frame.shape[:2], dtype=np.float32)
        return np.concatenate([frame, alpha[..., None]], axis=2)
