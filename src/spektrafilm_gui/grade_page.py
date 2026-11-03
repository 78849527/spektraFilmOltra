"""调色台：左 LUT/预设、中预览、右 Lightroom 式参数台。

右栏结构对齐 oflim：直方图 → 「光影 / 色彩」Tab → 下方「通透 / 画质 / 光学」
折叠区。所有参数写入 GradeRecipe，预览在 QThreadPool 内按 generation 丢弃旧帧。
"""

from __future__ import annotations

import colorsys
import shutil
from pathlib import Path
from typing import Callable

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

from spektrafilm_gui import app_paths, motion, shell_icons
from spektrafilm_gui.grade_engine import (
    ToneAnalysis,
    downsample_linear,
    load_handoff_image,
    prepare_source,
    srgb_encode,
)
from spektrafilm_gui.grade_presets import GradePreset, GradePresetStore
from spektrafilm_gui.grade_recipe import (
    GRADE_ZONE_LABELS,
    GRADE_ZONE_NAMES,
    HSL_BAND_HUES,
    HSL_BAND_LABELS,
    GradeRecipe,
)
from spektrafilm_gui.grade_worker import GradeFileRenderTask, GradeRenderTask
from spektrafilm_gui.library_store import LibraryItem
from spektrafilm_gui.parameter_deck import GroupLabel, HistogramView, Tabs
from spektrafilm_gui.theme_oflim import (
    ACCENT,
    ACCENT_ON,
    ACCENT_STRONG,
    HAIRLINE,
    HAIRLINE_STRONG,
    SURFACE_0,
    SURFACE_1,
    SURFACE_2,
    SURFACE_3,
    SURFACE_4,
    TEXT_1,
    TEXT_2,
    TEXT_3,
    TEXT_4,
    rgba,
)
from spektrafilm_gui.ui_names import film_display_name, paper_display_name
from spektrafilm_gui.widget_primitives import (
    CollapsibleSection,
    DampedScrollArea,
    WheelSafeSlider,
    tabular_font,
)

QAction = QtGui.QAction
QButtonGroup = QtWidgets.QButtonGroup
QFileDialog = QtWidgets.QFileDialog
QFrame = QtWidgets.QFrame
QHBoxLayout = QtWidgets.QHBoxLayout
QInputDialog = QtWidgets.QInputDialog
QLabel = QtWidgets.QLabel
QListWidget = QtWidgets.QListWidget
QListWidgetItem = QtWidgets.QListWidgetItem
QMessageBox = QtWidgets.QMessageBox
QPushButton = QtWidgets.QPushButton
QSize = QtCore.QSize
QSizePolicy = QtWidgets.QSizePolicy
QSplitter = QtWidgets.QSplitter
QStackedWidget = QtWidgets.QStackedWidget
QThreadPool = QtCore.QThreadPool
QTimer = QtCore.QTimer
QToolButton = QtWidgets.QToolButton
QVBoxLayout = QtWidgets.QVBoxLayout
QWidget = QtWidgets.QWidget
Qt = QtCore.Qt
Signal = QtCore.Signal

GRADE_PREVIEW_MAX_EDGE = 1600
GRADE_PREVIEW_DEBOUNCE_MS = 140
GRADE_RAIL_WIDTH = 244
GRADE_DECK_WIDTH = 348


def _qimage_from_array(image) -> QtGui.QImage | None:
    if image is None:
        return None
    try:
        array = np.asarray(image)
        if array.ndim != 3 or array.shape[2] < 3:
            return None
        if array.dtype.kind == 'f':
            array = np.clip(array, 0.0, 1.0) * 255.0
        array = np.ascontiguousarray(array[..., :3], dtype=np.uint8)
    except (TypeError, ValueError):
        return None
    height, width = array.shape[:2]
    if width <= 0 or height <= 0:
        return None
    return QtGui.QImage(
        array.data,
        width,
        height,
        width * 3,
        QtGui.QImage.Format_RGB888,
    ).copy()


def _get_path(root, path: tuple[str, ...]):
    obj = root
    for part in path:
        obj = getattr(obj, part)
    return obj


def _set_path(root, path: tuple[str, ...], value) -> None:
    obj = root
    for part in path[:-1]:
        obj = getattr(obj, part)
    setattr(obj, path[-1], value)


GRADE_STYLE = f"""
QWidget#gradePage {{ background: {SURFACE_0}; }}
QWidget#gradeRail {{
    background: {SURFACE_1};
    border-right: 1px solid {HAIRLINE};
}}
QWidget#gradeCanvasArea {{ background: {SURFACE_0}; }}
QWidget#gradeDeck {{
    background: {SURFACE_0};
    border-left: 1px solid {HAIRLINE};
}}
QLabel#gradeBadge {{
    color: {ACCENT};
    font-size: 11px;
    font-weight: 500;
    background: {rgba(ACCENT, 0.10)};
    border-radius: 7px;
    padding: 1px 7px;
}}
QPushButton#gradeReset {{
    color: {TEXT_2}; background: transparent;
    border: 1px solid {HAIRLINE}; border-radius: 9px;
    font-size: 12px; font-weight: 500;
    padding: 0px 14px;
}}
QPushButton#gradeReset:hover {{ background: {SURFACE_2}; border-color: {HAIRLINE_STRONG}; color: {TEXT_1}; }}
QPushButton#compactBack:checked {{
    background: {rgba(ACCENT, 0.14)};
    border-color: {rgba(ACCENT, 0.50)};
    color: {ACCENT};
}}
QToolButton#exportArrow {{
    background: {ACCENT}; border: 1px solid {ACCENT}; border-radius: 6px;
}}
QToolButton#exportArrow:hover {{ background: {ACCENT_STRONG}; }}
QToolButton#exportArrow:disabled {{ background: {SURFACE_3}; border-color: {SURFACE_3}; }}

QFrame#gradeHistogram {{
    background: {SURFACE_2};
    border: 1px solid {HAIRLINE};
    border-radius: 12px;
}}
QLabel#gradeHistogramTitle {{ color: {TEXT_2}; font-size: 11px; font-weight: 500; }}
QLabel#gradeHistogramMeta {{ color: {TEXT_3}; font-size: 11px; }}

QFrame#gradeCard {{
    background: {SURFACE_2};
    border: 1px solid {HAIRLINE};
    border-radius: 12px;
}}
QLabel#gradeGroup {{ color: {TEXT_3}; font-size: 11px; font-weight: 600; }}
QLabel#gradeLabel {{ color: {TEXT_2}; font-size: 12px; background: transparent; }}
QLabel#gradeValue {{ color: {TEXT_3}; font-size: 12px; background: transparent; }}
QLabel#gradeValue[dirty="true"] {{ color: {ACCENT}; }}

QSlider#gradeSlider {{ background: transparent; }}
QSlider#gradeSlider::groove:horizontal {{
    height: 3px; background: {SURFACE_4}; border-radius: 1.5px;
}}
QSlider#gradeSlider::sub-page:horizontal {{
    height: 3px; background: {rgba('#FFFFFF', 0.22)}; border-radius: 1.5px;
}}
QSlider#gradeSlider[dirty="true"]::sub-page:horizontal {{
    height: 3px; background: {ACCENT}; border-radius: 1.5px;
}}
QSlider#gradeSlider::handle:horizontal {{
    width: 11px; height: 11px; margin: -5px 0;
    border-radius: 5px; background: #ECE9E2;
    border: 1px solid rgba(0, 0, 0, 0.35);
}}
QSlider#gradeSlider::handle:horizontal:hover {{ background: #FFFFFF; }}

QPushButton#railAction {{
    background: {SURFACE_2}; color: {TEXT_2};
    border: 1px solid {HAIRLINE}; border-radius: 8px;
    font-size: 12px; min-height: 27px; padding: 0 9px;
}}
QPushButton#railAction:hover {{ color: {TEXT_1}; border-color: {HAIRLINE_STRONG}; }}
QPushButton#railAction:disabled {{ color: {TEXT_4}; }}

QListWidget#railList {{
    background: transparent; border: none; outline: none;
    color: {TEXT_2}; font-size: 12px;
}}
QListWidget#railList::item {{
    padding: 7px 8px; border-radius: 7px;
}}
QListWidget#railList::item:hover {{ background: {SURFACE_2}; color: {TEXT_1}; }}
QListWidget#railList::item:selected {{ background: {SURFACE_3}; color: {ACCENT}; }}

QWidget#gradeCanvas {{ background: {SURFACE_0}; }}
QLabel#gradeStatus {{ color: {TEXT_4}; font-size: 11px; }}
QLabel#gradeAnalysis {{ color: {TEXT_3}; font-size: 11px; }}
QLabel#gradeHint {{ color: {TEXT_4}; font-size: 11px; }}

QScrollArea QScrollBar:vertical {{
    background: transparent; width: 6px; margin: 4px 2px 4px 0;
}}
QScrollArea QScrollBar::handle:vertical {{
    background: {rgba('#FFFFFF', 0.14)}; border-radius: 3px; min-height: 32px;
}}
QScrollArea QScrollBar::handle:vertical:hover {{ background: {rgba('#FFFFFF', 0.24)}; }}
QScrollArea QScrollBar::add-line:vertical,
QScrollArea QScrollBar::sub-line:vertical,
QScrollArea QScrollBar::add-page:vertical,
QScrollArea QScrollBar::sub-page:vertical {{
    background: none; height: 0px; width: 0px; border: none;
}}
"""


class RecipeSliderRow(QWidget):
    """标签 + 等宽读数 + 细轨道滑块；双击标签恢复默认值。"""

    valueChanged = Signal(float)

    def __init__(
        self,
        label: str,
        *,
        minimum: float,
        maximum: float,
        step: float,
        decimals: int = 0,
        default: float = 0.0,
        suffix: str = '',
        tooltip: str = '',
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._minimum = float(minimum)
        self._maximum = float(maximum)
        self._step = float(step) if step > 0 else 0.01
        self._decimals = max(0, int(decimals))
        self._default = float(default)
        self._suffix = suffix
        self._syncing = False
        self.setFixedHeight(44)

        self._label = QLabel(label)
        self._label.setObjectName('gradeLabel')
        self._value = QLabel('')
        self._value.setObjectName('gradeValue')
        self._value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._value.setMinimumWidth(52)
        self._value.setFont(tabular_font())

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        header.addWidget(self._label, 1, Qt.AlignVCenter)
        header.addWidget(self._value, 0, Qt.AlignVCenter)

        self._slider = WheelSafeSlider(Qt.Horizontal)
        self._slider.setObjectName('gradeSlider')
        self._slider.setRange(0, self._ticks())
        self._slider.setFixedHeight(14)
        self._slider.setCursor(Qt.PointingHandCursor)
        self._slider.valueChanged.connect(self._on_slider)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(5)
        layout.addLayout(header)
        layout.addWidget(self._slider)

        if tooltip:
            self.setToolTip(tooltip)
        self._label.mouseDoubleClickEvent = self._reset  # type: ignore[method-assign]
        self.set_value_silent(self._default)

    def _ticks(self) -> int:
        span = self._maximum - self._minimum
        return max(1, int(round(span / self._step)))

    def _to_tick(self, value: float) -> int:
        ratio = (float(value) - self._minimum) / max(self._maximum - self._minimum, 1e-9)
        return max(0, min(self._ticks(), int(round(ratio * self._ticks()))))

    def _from_tick(self, tick: int) -> float:
        span = self._maximum - self._minimum
        value = self._minimum + span * tick / max(self._ticks(), 1)
        value = round(value / self._step) * self._step
        return max(self._minimum, min(self._maximum, value))

    def _format(self, value: float) -> str:
        if self._decimals == 0:
            text = f'{int(round(value))}'
        else:
            text = f'{value:.{self._decimals}f}'
        if self._minimum < 0 and value > 0:
            text = f'+{text}'
        return f'{text}{self._suffix}'

    def _update_visuals(self, value: float) -> None:
        self._value.setText(self._format(value))
        dirty = abs(float(value) - self._default) > 10 ** (-self._decimals) / 2
        self._value.setProperty('dirty', 'true' if dirty else 'false')
        self._value.style().unpolish(self._value)
        self._value.style().polish(self._value)
        self._slider.setProperty('dirty', 'true' if dirty else 'false')
        self._slider.style().unpolish(self._slider)
        self._slider.style().polish(self._slider)

    def _on_slider(self, tick: int) -> None:
        if self._syncing:
            return
        value = self._from_tick(tick)
        self._update_visuals(value)
        self.valueChanged.emit(value)

    def _reset(self, event) -> None:  # noqa: N802 - Qt API name
        self.set_value_silent(self._default)
        self.valueChanged.emit(self._default)
        motion.fade_in(self._value, duration=140, start=0.3)
        event.accept()

    def value(self) -> float:
        return self._from_tick(self._slider.value())

    def set_value_silent(self, value: float) -> None:
        self._syncing = True
        try:
            self._slider.setValue(self._to_tick(value))
            self._update_visuals(float(value))
        finally:
            self._syncing = False

    def setToolTip(self, text: str) -> None:  # noqa: N802 - Qt API name
        super().setToolTip(text)
        self._label.setToolTip(text)
        self._value.setToolTip(text)
        self._slider.setToolTip(text)


class _BandChip(QtWidgets.QAbstractButton):
    def __init__(self, label: str, hue: float, parent: QWidget | None = None):
        super().__init__(parent)
        self._hue = float(hue)
        self.setText(label)
        self.setCheckable(True)
        self.setFixedSize(31, 25)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            red, green, blue = colorsys.hsv_to_rgb(self._hue / 360.0, 0.55, 0.86)
            fill = QtGui.QColor(round(red * 255), round(green * 255), round(blue * 255))
            rect = QtCore.QRectF(1.0, 1.0, self.width() - 2.0, self.height() - 2.0)
            if self.isChecked():
                painter.setPen(QtGui.QPen(QtGui.QColor(ACCENT), 1.5))
            elif self.underMouse():
                painter.setPen(QtGui.QPen(QtGui.QColor(HAIRLINE_STRONG), 1.0))
            else:
                painter.setPen(QtGui.QPen(QtGui.QColor(HAIRLINE), 1.0))
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 7.0, 7.0)

            luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
            painter.setPen(QtGui.QColor('#14120E' if luminance > 0.55 else '#F4F4F2'))
            font = QtGui.QFont(self.font())
            font.setPixelSize(10)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, self.text())
        finally:
            painter.end()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().leaveEvent(event)
        self.update()


class _ShrinkStack(QStackedWidget):
    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        widget = self.currentWidget()
        return widget.sizeHint() if widget is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        widget = self.currentWidget()
        return widget.minimumSizeHint() if widget is not None else super().minimumSizeHint()

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802 - Qt API name
        super().setCurrentIndex(index)
        self.updateGeometry()


class GradeTopBar(QWidget):
    back_requested = Signal()
    compare_toggled = Signal(bool)
    export_requested = Signal(bool)
    export_settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('gradeTopBar')
        self.setFixedHeight(54)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f'QWidget#gradeTopBar {{ background: {SURFACE_0};'
            f' border-bottom: 1px solid {HAIRLINE}; }}'
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        back = QPushButton('显影台')
        back.setObjectName('compactBack')
        back.setIcon(shell_icons.icon('back', TEXT_2, 11))
        back.setIconSize(QSize(11, 11))
        back.setFixedHeight(28)
        back.setCursor(Qt.PointingHandCursor)
        back.setToolTip('返回显影台')
        back.clicked.connect(self.back_requested.emit)

        self._name = QLabel('')
        self._name.setObjectName('gradeTitle')
        self._name.setStyleSheet(f'color: {TEXT_1}; font-size: 14px; font-weight: 600;')
        self._meta = QLabel('')
        self._meta.setObjectName('gradeMeta')
        self._meta.setStyleSheet(f'color: {TEXT_3}; font-size: 11px;')
        self._meta.setFont(tabular_font(self._meta.font()))

        title_box = QWidget()
        title_layout = QVBoxLayout(title_box)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(1)
        title_layout.addWidget(self._name)
        title_layout.addWidget(self._meta)

        badge = QLabel('调色台')
        badge.setObjectName('gradeBadge')

        self._compare = QPushButton('前后对比')
        self._compare.setObjectName('compactBack')
        self._compare.setCheckable(True)
        self._compare.setIcon(shell_icons.icon('compare', TEXT_2, 12))
        self._compare.setIconSize(QSize(12, 12))
        self._compare.setFixedHeight(28)
        self._compare.setCursor(Qt.PointingHandCursor)
        self._compare.setToolTip('切换原片与调色结果')
        self._compare.toggled.connect(self.compare_toggled.emit)

        self._export = QPushButton('导出')
        self._export.setObjectName('exportButton')
        self._export.setFixedHeight(28)
        self._export.setIcon(shell_icons.icon('export', ACCENT_ON, 12))
        self._export.setIconSize(QSize(12, 12))
        self._export.setCursor(Qt.PointingHandCursor)
        self._export.clicked.connect(lambda: self.export_requested.emit(False))

        self._arrow = QToolButton()
        self._arrow.setObjectName('exportArrow')
        self._arrow.setFixedSize(22, 28)
        self._arrow.setCursor(Qt.PointingHandCursor)
        self._arrow.setPopupMode(QToolButton.InstantPopup)
        self._arrow.setIcon(shell_icons.icon('chevron_down', ACCENT_ON, 8))
        self._arrow.setIconSize(QSize(8, 8))
        menu = QtWidgets.QMenu(self._arrow)
        direct_action = QAction('直接导出（90% PNG）', menu)
        direct_action.triggered.connect(lambda: self.export_requested.emit(True))
        settings_action = QAction('导出设置…', menu)
        settings_action.triggered.connect(self.export_settings_requested.emit)
        menu.addAction(direct_action)
        menu.addAction(settings_action)
        self._arrow.setMenu(menu)

        layout.addWidget(back, 0, Qt.AlignVCenter)
        layout.addWidget(title_box, 1)
        layout.addWidget(badge, 0, Qt.AlignVCenter)
        layout.addWidget(self._compare, 0, Qt.AlignVCenter)
        layout.addWidget(self._export, 0, Qt.AlignVCenter)
        layout.addWidget(self._arrow, 0, Qt.AlignVCenter)

    def set_photo(self, item: LibraryItem) -> None:
        self._name.setText(item.name)
        parts: list[str] = []
        if item.width and item.height:
            parts.append(f'{item.width}×{item.height}')
        if item.film_stock:
            parts.append(film_display_name(item.film_stock))
        if item.print_paper:
            parts.append(paper_display_name(item.print_paper))
        parts.append('16-bit ProPhoto 线性交接图')
        self._meta.setText(' · '.join(parts))

    def set_busy(self, busy: bool, label: str = '渲染中…') -> None:
        self._export.setEnabled(not busy)
        self._export.setText(label if busy else '导出')
        self._arrow.setEnabled(not busy)

    def set_compare_checked(self, checked: bool) -> None:
        was_blocked = self._compare.blockSignals(True)
        self._compare.setChecked(bool(checked))
        self._compare.blockSignals(was_blocked)


class GradeCanvas(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('gradeCanvas')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f'QWidget#gradeCanvas {{ background: {SURFACE_0}; }}')
        self._pixmap = QtGui.QPixmap()
        self._original = QtGui.QPixmap()
        self._message = '正在读取交接图…'
        self._compare = False

    def set_image(self, image) -> None:
        qimage = _qimage_from_array(image)
        if qimage is None:
            self._pixmap = QtGui.QPixmap()
        else:
            self._pixmap = QtGui.QPixmap.fromImage(qimage)
        self._message = ''
        self.update()

    def set_original(self, image) -> None:
        qimage = _qimage_from_array(image)
        self._original = QtGui.QPixmap.fromImage(qimage) if qimage is not None else QtGui.QPixmap()

    def set_compare(self, compare: bool) -> None:
        self._compare = bool(compare)
        self.update()

    def set_message(self, message: str) -> None:
        self._message = str(message)
        self.update()

    def clear(self) -> None:
        self._pixmap = QtGui.QPixmap()
        self._original = QtGui.QPixmap()
        self._message = '等待交接图'
        self.update()

    def _active_pixmap(self) -> QtGui.QPixmap:
        if self._compare and not self._original.isNull():
            return self._original
        return self._pixmap

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
            rect = self.rect().adjusted(28, 24, -28, -24)
            pixmap = self._active_pixmap()
            if pixmap.isNull():
                painter.setPen(QtGui.QColor(TEXT_4))
                painter.drawText(rect, Qt.AlignCenter, self._message)
                return
            scaled = pixmap.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = rect.left() + (rect.width() - scaled.width()) // 2
            y = rect.top() + (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        finally:
            painter.end()


class _LutPage(QWidget):
    lut_changed = Signal(str, float)
    status_message = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._syncing = False
        self._current_path = ''

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        self._list = QListWidget()
        self._list.setObjectName('railList')
        self._list.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self._list, 1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(6)
        import_button = QPushButton('导入 LUT')
        import_button.setObjectName('railAction')
        import_button.setCursor(Qt.PointingHandCursor)
        import_button.clicked.connect(self._import)
        remove_button = QPushButton('移除')
        remove_button.setObjectName('railAction')
        remove_button.setCursor(Qt.PointingHandCursor)
        remove_button.clicked.connect(self._remove)
        buttons.addWidget(import_button)
        buttons.addWidget(remove_button)
        layout.addLayout(buttons)

        self._strength = RecipeSliderRow(
            '强度',
            minimum=0.0,
            maximum=100.0,
            step=1.0,
            decimals=0,
            default=100.0,
            tooltip='LUT 应用强度',
        )
        self._strength.valueChanged.connect(self._on_strength)
        layout.addWidget(self._strength)

        hint = QLabel('把 .cube 放入 LUT 库，选择后立即套用到调色结果。')
        hint.setObjectName('gradeHint')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.refresh()

    def _lut_dir(self) -> Path:
        return app_paths.app_data_dir() / 'luts'

    @staticmethod
    def _path_of(item: QListWidgetItem | None) -> str:
        if item is None:
            return ''
        data = item.data(Qt.UserRole)
        return str(data) if data else ''

    def refresh(self, select_path: str = '') -> None:
        wanted = select_path or self._current_path
        self._syncing = True
        try:
            self._list.clear()
            none_item = QListWidgetItem('无 LUT')
            none_item.setData(Qt.UserRole, '')
            self._list.addItem(none_item)
            directory = self._lut_dir()
            if directory.is_dir():
                for path in sorted(directory.glob('*.cube'), key=lambda p: p.stem.lower()):
                    item = QListWidgetItem(path.stem)
                    item.setData(Qt.UserRole, str(path))
                    item.setToolTip(str(path))
                    self._list.addItem(item)
            selected = 0
            for index in range(self._list.count()):
                if self._path_of(self._list.item(index)) == wanted:
                    selected = index
                    break
            self._list.setCurrentRow(selected)
            self._current_path = self._path_of(self._list.item(selected))
        finally:
            self._syncing = False

    def _on_selection(self) -> None:
        if self._syncing:
            return
        path = self._path_of(self._list.currentItem())
        self._current_path = path
        self.lut_changed.emit(path, self._strength.value())

    def _on_strength(self, value: float) -> None:
        if self._syncing:
            return
        self.lut_changed.emit(self._current_path, value)

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, '导入 LUT', '', 'Cube LUT (*.cube)')
        if not path:
            return
        directory = self._lut_dir()
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / Path(path).name
        index = 2
        while target.exists():
            target = directory / f'{Path(path).stem} {index}.cube'
            index += 1
        try:
            shutil.copy2(path, target)
        except OSError as exc:
            self.status_message.emit(f'LUT 导入失败：{exc}')
            return
        self.refresh(str(target))
        self.status_message.emit(f'已导入 {target.name}')
        self.lut_changed.emit(str(target), self._strength.value())

    def _is_library_path(self, path: str) -> bool:
        try:
            Path(path).resolve().relative_to(self._lut_dir().resolve())
        except (OSError, ValueError):
            return False
        return True

    def _remove(self) -> None:
        path = self._current_path
        if not path:
            return
        if not self._is_library_path(path):
            for index in range(self._list.count()):
                if self._path_of(self._list.item(index)) == path:
                    self._list.takeItem(index)
                    break
            self._current_path = ''
            self._list.setCurrentRow(0)
            self.lut_changed.emit('', self._strength.value())
            self.status_message.emit('外部 LUT 不在库内，已取消选择')
            return

        answer = QMessageBox.question(
            self,
            '移除 LUT',
            f'从 LUT 库删除 {Path(path).name}？',
        )
        if answer != QMessageBox.Yes:
            return
        try:
            Path(path).unlink(missing_ok=True)
        except OSError as exc:
            self.status_message.emit(f'LUT 删除失败：{exc}')
            return
        self.refresh()
        self.lut_changed.emit('', self._strength.value())
        self.status_message.emit('已移除 LUT')

    def set_lut(self, path: str, strength: float) -> None:
        self._syncing = True
        try:
            if path and not Path(path).exists():
                path = ''
            self._current_path = str(path)
            self._strength.set_value_silent(float(strength))
            found = False
            for index in range(self._list.count()):
                if self._path_of(self._list.item(index)) == self._current_path:
                    self._list.setCurrentRow(index)
                    found = True
                    break
            if not found and self._current_path:
                item = QListWidgetItem(f'外部 · {Path(self._current_path).stem}')
                item.setData(Qt.UserRole, self._current_path)
                item.setToolTip(f'{self._current_path}（不在 LUT 库内）')
                self._list.insertItem(1, item)
                self._list.setCurrentRow(1)
            elif not found:
                self._list.setCurrentRow(0)
                for index in range(self._list.count() - 1, 0, -1):
                    item_path = self._path_of(self._list.item(index))
                    if item_path and not self._is_library_path(item_path):
                        self._list.takeItem(index)
        finally:
            self._syncing = False


class _PresetPage(QWidget):
    preset_selected = Signal(object)
    status_message = Signal(str)

    def __init__(
        self,
        store: GradePresetStore,
        recipe_provider: Callable[[], GradeRecipe],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._store = store
        self._recipe_provider = recipe_provider
        self._syncing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        self._list = QListWidget()
        self._list.setObjectName('railList')
        self._list.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self._list, 1)

        first_row = QHBoxLayout()
        first_row.setContentsMargins(0, 0, 0, 0)
        first_row.setSpacing(6)
        save_button = self._button('保存当前', self._save_current)
        rename_button = self._button('重命名', self._rename)
        delete_button = self._button('删除', self._delete)
        first_row.addWidget(save_button)
        first_row.addWidget(rename_button)
        first_row.addWidget(delete_button)
        layout.addLayout(first_row)

        second_row = QHBoxLayout()
        second_row.setContentsMargins(0, 0, 0, 0)
        second_row.setSpacing(6)
        import_button = self._button('导入', self._import)
        export_button = self._button('导出', self._export)
        second_row.addWidget(import_button)
        second_row.addWidget(export_button)
        second_row.addStretch(1)
        layout.addLayout(second_row)

        hint = QLabel('选中即套用；保存当前会把整份调色配方存成用户预设。')
        hint.setObjectName('gradeHint')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.refresh()

    @staticmethod
    def _button(text: str, callback) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName('railAction')
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(callback)
        return button

    @staticmethod
    def _preset_of(item: QListWidgetItem | None) -> GradePreset | None:
        if item is None:
            return None
        data = item.data(Qt.UserRole)
        return data if isinstance(data, GradePreset) else None

    def refresh(self, select_id: str = '') -> None:
        self._syncing = True
        try:
            current = select_id or self.current_preset_id()
            self._list.clear()
            selected = 0
            for index, preset in enumerate(self._store.all()):
                label = preset.name if not preset.builtin else f'{preset.name} · 内置'
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, preset)
                item.setToolTip('内置预设不可删除' if preset.builtin else '用户预设')
                self._list.addItem(item)
                if preset.id == current:
                    selected = index
            if self._list.count():
                self._list.setCurrentRow(selected)
        finally:
            self._syncing = False

    def current_preset_id(self) -> str:
        preset = self._preset_of(self._list.currentItem())
        return preset.id if preset is not None else ''

    def _on_selection(self) -> None:
        if self._syncing:
            return
        preset = self._preset_of(self._list.currentItem())
        if preset is not None:
            self.preset_selected.emit(preset)

    def _save_current(self) -> None:
        name, accepted = QInputDialog.getText(self, '保存预设', '预设名称')
        if not accepted or not name.strip():
            return
        try:
            preset = self._store.save(name, self._recipe_provider())
        except OSError as exc:
            self.status_message.emit(f'预设保存失败：{exc}')
            return
        self.refresh(preset.id)
        self.status_message.emit(f'已保存预设「{preset.name}」')

    def _rename(self) -> None:
        preset = self._preset_of(self._list.currentItem())
        if preset is None or preset.builtin:
            self.status_message.emit('内置预设不能重命名')
            return
        name, accepted = QInputDialog.getText(self, '重命名预设', '预设名称', text=preset.name)
        if not accepted or not name.strip():
            return
        try:
            updated = self._store.rename(preset.id, name)
        except OSError as exc:
            self.status_message.emit(f'重命名失败：{exc}')
            return
        if updated is None:
            self.status_message.emit('重命名失败')
            return
        self.refresh(updated.id)
        self.status_message.emit(f'已重命名为「{updated.name}」')

    def _delete(self) -> None:
        preset = self._preset_of(self._list.currentItem())
        if preset is None or preset.builtin:
            self.status_message.emit('内置预设不能删除')
            return
        answer = QMessageBox.question(self, '删除预设', f'删除预设「{preset.name}」？')
        if answer != QMessageBox.Yes:
            return
        try:
            deleted = self._store.delete(preset.id)
        except OSError as exc:
            self.status_message.emit(f'删除失败：{exc}')
            return
        if deleted:
            self.refresh()
            self.status_message.emit('已删除预设')

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, '导入预设', '', 'JSON (*.json)')
        if not path:
            return
        try:
            preset = self._store.import_file(path)
        except OSError as exc:
            self.status_message.emit(f'预设导入失败：{exc}')
            return
        if preset is None:
            self.status_message.emit('预设文件无法解析')
            return
        self.refresh(preset.id)
        self.status_message.emit(f'已导入预设「{preset.name}」')

    def _export(self) -> None:
        preset = self._preset_of(self._list.currentItem())
        if preset is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            '导出预设',
            f'{preset.name}.json',
            'JSON (*.json)',
        )
        if not path:
            return
        if self._store.export_file(preset.id, path):
            self.status_message.emit(f'已导出到 {path}')
        else:
            self.status_message.emit('预设导出失败')


class GradeRail(QWidget):
    lut_changed = Signal(str, float)
    preset_selected = Signal(object)
    status_message = Signal(str)

    def __init__(
        self,
        store: GradePresetStore,
        recipe_provider: Callable[[], GradeRecipe],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName('gradeRail')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(GRADE_RAIL_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tabs = Tabs(['LUT', '预设'], variant='underline')
        tab_holder = QWidget()
        tab_layout = QVBoxLayout(tab_holder)
        tab_layout.setContentsMargins(14, 8, 14, 0)
        tab_layout.addWidget(self._tabs)
        layout.addWidget(tab_holder)

        self._stack = QStackedWidget()
        self.lut_page = _LutPage()
        self.preset_page = _PresetPage(store, recipe_provider)
        self._stack.addWidget(self.lut_page)
        self._stack.addWidget(self.preset_page)
        layout.addWidget(self._stack, 1)

        self._tabs.changed.connect(self._stack.setCurrentIndex)
        self.lut_page.lut_changed.connect(self.lut_changed.emit)
        self.preset_page.preset_selected.connect(self.preset_selected.emit)
        self.lut_page.status_message.connect(self.status_message.emit)
        self.preset_page.status_message.connect(self.status_message.emit)

    def set_context(self, recipe: GradeRecipe, preset_id: str = '') -> None:
        self.lut_page.set_lut(recipe.lut.path, recipe.lut.strength)
        self.preset_page.refresh(preset_id)


class GradeDeck(QWidget):
    recipe_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('gradeDeck')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(GRADE_DECK_WIDTH)
        self._recipe = GradeRecipe()
        self._rows: dict[tuple[str, ...], RecipeSliderRow] = {}
        self._band_index = 0
        self._zone_index = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self._build_body(), 1)

    # ── 构建 ────────────────────────────────────────────────────
    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName('gradeDeckHeader')
        header.setFixedHeight(48)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(8)

        title = QLabel('调色参数')
        title.setStyleSheet(f'color: {TEXT_2}; font-size: 12px; font-weight: 600;')
        self._badge = QLabel('')
        self._badge.setObjectName('gradeBadge')
        self._badge.hide()

        reset = QPushButton('重置')
        reset.setObjectName('gradeReset')
        reset.setFixedHeight(30)
        reset.setCursor(Qt.PointingHandCursor)
        reset.setToolTip('把所有调色参数恢复为中性')
        reset.clicked.connect(self.reset)

        layout.addWidget(title, 0, Qt.AlignVCenter)
        layout.addStretch(1)
        layout.addWidget(self._badge, 0, Qt.AlignVCenter)
        layout.addWidget(reset, 0, Qt.AlignVCenter)
        return header

    def _build_body(self) -> QWidget:
        scroll = DampedScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 10, 14, 16)
        layout.setSpacing(10)

        layout.addWidget(self._build_histogram())

        self._tabs = Tabs(['光影', '色彩'], variant='segmented')
        self._tabs.changed.connect(self._show_page)
        layout.addWidget(self._tabs)

        self._stack = _ShrinkStack()
        self._stack.addWidget(self._build_light_page())
        self._stack.addWidget(self._build_color_page())
        layout.addWidget(self._stack)

        layout.addWidget(self._build_transparency_section())
        layout.addWidget(self._build_quality_section())
        layout.addWidget(self._build_optics_section())
        layout.addStretch(1)

        scroll.setWidget(content)
        return scroll

    def _build_histogram(self) -> QWidget:
        card = QFrame()
        card.setObjectName('gradeHistogram')
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        title = QLabel('直方图')
        title.setObjectName('gradeHistogramTitle')
        meta = QLabel('亮度 / RGB')
        meta.setObjectName('gradeHistogramMeta')
        head.addWidget(title, 0, Qt.AlignVCenter)
        head.addStretch(1)
        head.addWidget(meta, 0, Qt.AlignVCenter)

        self.histogram = HistogramView()
        layout.addLayout(head)
        layout.addWidget(self.histogram)
        return card

    def _new_card(self) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName('gradeCard')
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 11)
        layout.setSpacing(1)
        layout.setAlignment(Qt.AlignTop)
        return card, layout

    def _build_light_page(self) -> QWidget:
        card, layout = self._new_card()
        layout.addWidget(GroupLabel('基础'))
        for path, label, lo, hi, step, decimals, tip in (
            (('light', 'exposure'), '曝光', -5.0, 5.0, 0.01, 2, '曝光补偿（EV）'),
            (('light', 'contrast'), '对比度', -100.0, 100.0, 1.0, 0, 'S 曲线对比度'),
            (('light', 'highlights'), '高光', -100.0, 100.0, 1.0, 0, '高光区域提亮或压暗'),
            (('light', 'shadows'), '阴影', -100.0, 100.0, 1.0, 0, '阴影区域提亮或压暗'),
            (('light', 'whites'), '白色', -100.0, 100.0, 1.0, 0, '白场亮度'),
            (('light', 'blacks'), '黑色', -100.0, 100.0, 1.0, 0, '黑场亮度'),
            (('light', 'midtones'), '中间调', -100.0, 100.0, 1.0, 0, '中间调亮度'),
            (('light', 'highlight_rolloff'), '高光过渡', 0.0, 100.0, 1.0, 0, '压住高光并保留层次'),
        ):
            layout.addWidget(self._add_slider(*path, label=label, lo=lo, hi=hi, step=step, decimals=decimals, tip=tip))

        layout.addSpacing(6)
        layout.addWidget(GroupLabel('参数曲线'))
        for path, label, tip in (
            (('light', 'curve_highlights'), '高光', '参数曲线的高光段'),
            (('light', 'curve_lights'), '亮调', '参数曲线的亮调段'),
            (('light', 'curve_darks'), '暗调', '参数曲线的暗调段'),
            (('light', 'curve_shadows'), '阴影', '参数曲线的阴影段'),
        ):
            layout.addWidget(
                self._add_slider(*path, label=label, lo=-100.0, hi=100.0, step=1.0, decimals=0, tip=tip),
            )
        layout.addStretch(1)
        return card

    def _build_color_page(self) -> QWidget:
        card, layout = self._new_card()
        layout.addWidget(GroupLabel('白平衡'))
        for path, label, lo, hi, step, decimals, tip in (
            (('color', 'temperature'), '色温', -100.0, 100.0, 1.0, 0, '冷暖；正值偏暖'),
            (('color', 'tint'), '色调', -100.0, 100.0, 1.0, 0, '绿与品红；正值偏品红'),
        ):
            layout.addWidget(self._add_slider(*path, label=label, lo=lo, hi=hi, step=step, decimals=decimals, tip=tip))

        layout.addSpacing(6)
        layout.addWidget(GroupLabel('色彩'))
        for path, label, lo, hi, step, decimals, tip in (
            (('color', 'vibrance'), '自然饱和度', -100.0, 100.0, 1.0, 0, '优先提升低饱和颜色'),
            (('color', 'saturation'), '饱和度', -100.0, 100.0, 1.0, 0, '整体饱和度'),
            (('color', 'hue_shift'), '色相偏移', -180.0, 180.0, 1.0, 0, '全局色相旋转'),
            (('color', 'color_density'), '色彩密度', 0.0, 100.0, 1.0, 0, '增强颜色分离与浓度'),
        ):
            layout.addWidget(self._add_slider(*path, label=label, lo=lo, hi=hi, step=step, decimals=decimals, tip=tip))

        layout.addSpacing(6)
        layout.addWidget(GroupLabel('色彩混合'))
        chip_row = QHBoxLayout()
        chip_row.setContentsMargins(0, 4, 0, 4)
        chip_row.setSpacing(2)
        self._band_group = QButtonGroup(self)
        self._band_group.setExclusive(True)
        for index, (label, hue) in enumerate(zip(HSL_BAND_LABELS, self._band_hues())):
            chip = _BandChip(label, hue)
            self._band_group.addButton(chip, index)
            chip_row.addWidget(chip)
            if index == 0:
                chip.setChecked(True)
        chip_row.addStretch(1)
        layout.addLayout(chip_row)
        self._band_group.idClicked.connect(self._on_band_selected)
        self._band_rows: list[RecipeSliderRow] = []
        for key, label, lo, hi, step, decimals, tip in (
            ('hue', '色相', -100.0, 100.0, 1.0, 0, '该色带的色相偏移'),
            ('saturation', '饱和度', -100.0, 100.0, 1.0, 0, '该色带的饱和度'),
            ('luminance', '明度', -100.0, 100.0, 1.0, 0, '该色带的明度'),
        ):
            row = RecipeSliderRow(
                label,
                minimum=lo,
                maximum=hi,
                step=step,
                decimals=decimals,
                default=0.0,
                tooltip=tip,
            )
            row.valueChanged.connect(lambda value, field=key: self._on_band_value(field, value))
            self._band_rows.append(row)
            layout.addWidget(row)

        layout.addSpacing(6)
        layout.addWidget(GroupLabel('颜色分级'))
        self._zone_tabs = Tabs(list(GRADE_ZONE_LABELS), variant='segmented')
        self._zone_tabs.setFixedHeight(26)
        self._zone_tabs.changed.connect(self._on_zone_selected)
        layout.addWidget(self._zone_tabs)
        self._zone_rows: list[RecipeSliderRow] = []
        for key, label, lo, hi, step, decimals, tip in (
            ('hue', '色相', 0.0, 360.0, 1.0, 0, '该分区的色相'),
            ('saturation', '饱和度', 0.0, 100.0, 1.0, 0, '该分区的染色强度'),
            ('luminance', '明度', -100.0, 100.0, 1.0, 0, '该分区的明度'),
        ):
            row = RecipeSliderRow(
                label,
                minimum=lo,
                maximum=hi,
                step=step,
                decimals=decimals,
                default=0.0,
                tooltip=tip,
            )
            row.valueChanged.connect(lambda value, field=key: self._on_zone_value(field, value))
            self._zone_rows.append(row)
            layout.addWidget(row)
        for path, label, lo, hi, step, decimals, tip in (
            (('color', 'grading', 'blending'), '混合', 0.0, 100.0, 1.0, 0, '三个分区之间的过渡宽度'),
            (('color', 'grading', 'balance'), '平衡', -100.0, 100.0, 1.0, 0, '阴影/高光的权重平衡'),
        ):
            layout.addWidget(self._add_slider(*path, label=label, lo=lo, hi=hi, step=step, decimals=decimals, tip=tip))

        layout.addStretch(1)
        return card

    def _build_transparency_section(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        for path, label, tip in (
            (('transparency', 'tonal'), '明暗通透', '用最终亮度直方图的黑/白场重映射，拉开层次'),
            (('transparency', 'color'), '颜色通透', '统计高光/阴影偏色并用互补色中和'),
        ):
            layout.addWidget(
                self._add_slider(*path, label=label, lo=0.0, hi=100.0, step=1.0, decimals=0, tip=tip),
            )
        self._analysis_label = QLabel('等待画面分析…')
        self._analysis_label.setObjectName('gradeAnalysis')
        self._analysis_label.setWordWrap(True)
        layout.addWidget(self._analysis_label)
        hint = QLabel('明暗通透拉开黑场与白场；颜色通透抵消高光与阴影的偏色。')
        hint.setObjectName('gradeHint')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return self._wrap_section('通透', content)

    def _build_quality_section(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        for path, label, lo, hi, step, decimals, tip in (
            (('quality', 'clarity'), '清晰度', -100.0, 100.0, 1.0, 0, '中频局部对比，带 halo 限制'),
            (('quality', 'texture'), '纹理', -100.0, 100.0, 1.0, 0, '更细的局部对比'),
            (('quality', 'dehaze'), '去雾', -100.0, 100.0, 1.0, 0, '正值去雾，负值加雾'),
            (('quality', 'sharpen_amount'), '锐化', 0.0, 100.0, 1.0, 0, '两尺度 USM 锐化强度'),
            (('quality', 'sharpen_radius'), '锐化半径', 0.5, 3.0, 0.1, 1, '锐化作用半径'),
            (('quality', 'sharpen_threshold'), '锐化阈值', 0.0, 100.0, 1.0, 0, '忽略低对比细节'),
            (('quality', 'noise_luminance'), '亮度降噪', 0.0, 100.0, 1.0, 0, '压制亮度噪点'),
            (('quality', 'noise_color'), '色彩降噪', 0.0, 100.0, 1.0, 0, '压制彩色噪点'),
        ):
            layout.addWidget(
                self._add_slider(*path, label=label, lo=lo, hi=hi, step=step, decimals=decimals, tip=tip),
            )
        return self._wrap_section('画质', content)

    def _build_optics_section(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        for path, label, lo, hi, step, decimals, tip in (
            (('optics', 'vignette_amount'), '暗角', -100.0, 100.0, 1.0, 0, '正值压暗四角，负值提亮'),
            (('optics', 'vignette_midpoint'), '暗角中点', 0.0, 100.0, 1.0, 0, '暗角开始的位置'),
            (('optics', 'vignette_roundness'), '暗角圆度', -100.0, 100.0, 1.0, 0, '暗角形状的纵横比'),
            (('optics', 'vignette_feather'), '暗角柔和度', 0.0, 100.0, 1.0, 0, '暗角过渡宽度'),
            (('optics', 'grain_amount'), '颗粒', 0.0, 100.0, 1.0, 0, '颗粒强度'),
            (('optics', 'grain_size'), '颗粒尺寸', 0.0, 100.0, 1.0, 0, '颗粒大小'),
            (('optics', 'grain_roughness'), '颗粒粗糙度', 0.0, 100.0, 1.0, 0, '颗粒的硬边程度'),
            (('optics', 'chromatic_aberration'), '色差', 0.0, 100.0, 1.0, 0, '红/蓝通道径向错位'),
        ):
            layout.addWidget(
                self._add_slider(*path, label=label, lo=lo, hi=hi, step=step, decimals=decimals, tip=tip),
            )
        return self._wrap_section('光学', content)

    def _wrap_section(self, title: str, content: QWidget) -> QWidget:
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(CollapsibleSection(title, content, expanded=True))
        return holder

    @staticmethod
    def _band_hues() -> tuple[float, ...]:
        return HSL_BAND_HUES

    def _add_slider(
        self,
        *path: str,
        label: str,
        lo: float,
        hi: float,
        step: float,
        decimals: int,
        tip: str,
    ) -> RecipeSliderRow:
        default = float(_get_path(GradeRecipe(), tuple(path)))
        row = RecipeSliderRow(
            label,
            minimum=lo,
            maximum=hi,
            step=step,
            decimals=decimals,
            default=default,
            tooltip=tip,
        )
        row.valueChanged.connect(lambda value, key=path: self._on_row_value(key, value))
        self._rows[path] = row
        return row

    # ── 读写 ────────────────────────────────────────────────────
    def current_recipe(self) -> GradeRecipe:
        return self._recipe.clone()

    def set_recipe(self, recipe: GradeRecipe) -> None:
        self._recipe = recipe.clone()
        for path, row in self._rows.items():
            row.set_value_silent(float(_get_path(self._recipe, path)))
        self._refresh_band_rows()
        self._refresh_zone_rows()
        self._update_badge()

    def reset(self) -> None:
        self.set_recipe(GradeRecipe())
        self.recipe_changed.emit()

    def set_analysis(self, analysis: ToneAnalysis | None) -> None:
        if analysis is None:
            self._analysis_label.setText('等待画面分析…')
            return
        self._analysis_label.setText(analysis.summary)

    def update_histogram(self, image) -> None:
        self.histogram.set_array(image)

    def _on_row_value(self, path: tuple[str, ...], value: float) -> None:
        _set_path(self._recipe, path, float(value))
        self._update_badge()
        self.recipe_changed.emit()

    def _on_band_selected(self, index: int) -> None:
        self._band_index = int(index)
        self._refresh_band_rows()

    def _on_band_value(self, field: str, value: float) -> None:
        band = self._recipe.color.hsl[self._band_index]
        setattr(band, field, float(value))
        self._update_badge()
        self.recipe_changed.emit()

    def _refresh_band_rows(self) -> None:
        band = self._recipe.color.hsl[self._band_index]
        for row, field in zip(
            self._band_rows,
            ('hue', 'saturation', 'luminance'),
            strict=True,
        ):
            row.set_value_silent(float(getattr(band, field)))

    def _on_zone_selected(self, index: int) -> None:
        self._zone_index = int(index)
        self._refresh_zone_rows()

    def _on_zone_value(self, field: str, value: float) -> None:
        zone = getattr(self._recipe.color.grading, GRADE_ZONE_NAMES[self._zone_index])
        setattr(zone, field, float(value))
        self._update_badge()
        self.recipe_changed.emit()

    def _refresh_zone_rows(self) -> None:
        zone = getattr(self._recipe.color.grading, GRADE_ZONE_NAMES[self._zone_index])
        for row, field in zip(
            self._zone_rows,
            ('hue', 'saturation', 'luminance'),
            strict=True,
        ):
            row.set_value_silent(float(getattr(zone, field)))

    def _update_badge(self) -> None:
        count = self._recipe.dirty_count()
        self._badge.setText(str(count) if count else '')
        self._badge.setVisible(bool(count))

    def _show_page(self, index: int) -> None:
        self._stack.setCurrentIndex(index)


class GradePage(QWidget):
    back_requested = Signal()
    recipe_changed = Signal(dict)
    export_requested = Signal(bool)
    export_settings_requested = Signal()
    grade_image_ready = Signal(object, bool)
    status_message = Signal(str)

    def __init__(self, parent: QWidget | None = None, *, preset_path: str | Path | None = None):
        super().__init__(parent)
        self.setObjectName('gradePage')
        self.setStyleSheet(GRADE_STYLE)

        self._item: LibraryItem | None = None
        self._handoff_path = ''
        self._preview_source: np.ndarray | None = None
        self._generation = 0
        self._export_generation = 0
        self._preview_busy = False
        self._exporting = False
        self._export_direct = False
        self._preset_id = ''
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._preset_store = GradePresetStore(preset_path)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.top_bar = GradeTopBar()
        root.addWidget(self.top_bar)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(f'QSplitter::handle {{ background: {HAIRLINE}; }}')

        self.rail = GradeRail(self._preset_store, self._recipe_for_preset)
        self.rail.setStyleSheet(f'QWidget#gradeRail {{ background: {SURFACE_1}; }}')

        center = QWidget()
        center.setObjectName('gradeCanvasArea')
        center.setAttribute(Qt.WA_StyledBackground, True)
        center.setStyleSheet(f'QWidget#gradeCanvasArea {{ background: {SURFACE_0}; }}')
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        self.canvas = GradeCanvas()
        center_layout.addWidget(self.canvas, 1)
        status_row = QWidget()
        status_layout = QHBoxLayout(status_row)
        status_layout.setContentsMargins(18, 0, 18, 8)
        self._size_label = QLabel('—')
        self._size_label.setObjectName('gradeStatus')
        self._size_label.setFont(tabular_font())
        self._space_label = QLabel('sRGB · 预览')
        self._space_label.setObjectName('gradeStatus')
        status_layout.addWidget(self._size_label, 1, Qt.AlignVCenter)
        status_layout.addWidget(self._space_label, 0, Qt.AlignVCenter)
        center_layout.addWidget(status_row)

        self.deck = GradeDeck()

        splitter.addWidget(self.rail)
        splitter.addWidget(center)
        splitter.addWidget(self.deck)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        root.addWidget(splitter, 1)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(GRADE_PREVIEW_DEBOUNCE_MS)
        self._preview_timer.timeout.connect(self._start_preview_render)

        self.top_bar.back_requested.connect(self.back_requested.emit)
        self.top_bar.compare_toggled.connect(self.canvas.set_compare)
        self.top_bar.export_requested.connect(self._begin_export)
        self.top_bar.export_settings_requested.connect(self.export_settings_requested.emit)
        self.rail.lut_changed.connect(self._on_lut_changed)
        self.rail.preset_selected.connect(self._on_preset_selected)
        self.rail.status_message.connect(self.status_message.emit)
        self.deck.recipe_changed.connect(self._on_recipe_changed)

    # ── 加载 ────────────────────────────────────────────────────
    def load(
        self,
        item: LibraryItem,
        handoff_path: str | Path | None,
        recipe: GradeRecipe | None,
        *,
        preset_id: str = '',
    ) -> bool:
        self.unload()
        self._item = item
        self._handoff_path = str(handoff_path or '')
        self._preset_id = str(preset_id or '')
        loaded_recipe = recipe or GradeRecipe()
        if loaded_recipe.lut.path and not Path(loaded_recipe.lut.path).is_file():
            loaded_recipe = loaded_recipe.clone()
            loaded_recipe.lut.path = ''
            loaded_recipe.lut.strength = 100.0
        self.top_bar.set_photo(item)
        self.top_bar.set_compare_checked(False)
        self.canvas.set_compare(False)
        self.deck.set_recipe(loaded_recipe)
        self.deck.set_analysis(None)
        self.deck.update_histogram(None)
        self.rail.set_context(self.deck.current_recipe(), self._preset_id)
        self._update_status_text()

        path = Path(self._handoff_path) if self._handoff_path else None
        if path is None or not path.is_file():
            self.canvas.clear()
            self.canvas.set_message('交接图不存在，请返回显影台重新调色。')
            self.status_message.emit('交接图不存在')
            return False

        QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            image = load_handoff_image(path)
            source = prepare_source(image)
            preview = downsample_linear(source, GRADE_PREVIEW_MAX_EDGE)
        except Exception as exc:  # noqa: BLE001 - 交接图损坏时必须留在调色台并提示
            self.canvas.clear()
            self.canvas.set_message(f'交接图读取失败：{exc}')
            self.status_message.emit(f'交接图读取失败：{exc}')
            return False
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

        self._preview_source = np.ascontiguousarray(preview)
        self.canvas.set_original(srgb_encode(self._preview_source))
        self.canvas.set_message('正在生成调色预览…')
        self._update_status_text(preview)
        self._start_preview_render()
        return True

    def unload(self) -> None:
        self._preview_timer.stop()
        self._generation += 1
        self._export_generation += 1
        self._preview_source = None
        self._handoff_path = ''
        self._item = None
        self._preview_busy = False
        self._exporting = False
        self.canvas.clear()
        self.deck.set_analysis(None)
        self.deck.update_histogram(None)
        self._size_label.setText('—')
        self._space_label.setText('sRGB · 预览')
        self._sync_busy()

    # ── 配方 ────────────────────────────────────────────────────
    def recipe(self) -> GradeRecipe:
        return self.deck.current_recipe()

    def recipe_dict(self) -> dict:
        return self.recipe().to_dict()

    def preset_id(self) -> str:
        return self._preset_id

    def _recipe_for_preset(self) -> GradeRecipe:
        return self.deck.current_recipe()

    def _on_recipe_changed(self) -> None:
        self._preset_id = ''
        recipe = self.deck.current_recipe()
        self.rail.lut_page.set_lut(recipe.lut.path, recipe.lut.strength)
        self.recipe_changed.emit(recipe.to_dict())
        self._preview_timer.start()

    def _on_preset_selected(self, preset: object) -> None:
        if not isinstance(preset, GradePreset):
            return
        self.deck.set_recipe(preset.recipe)
        self._preset_id = preset.id
        self.rail.lut_page.set_lut(preset.recipe.lut.path, preset.recipe.lut.strength)
        self.recipe_changed.emit(self.recipe_dict())
        self._preview_timer.start()
        self.status_message.emit(f'已套用预设「{preset.name}」')

    def _on_lut_changed(self, path: str, strength: float) -> None:
        self._preset_id = ''
        recipe = self.deck.current_recipe()
        recipe.lut.path = str(path)
        recipe.lut.strength = float(strength)
        self.deck.set_recipe(recipe)
        self.recipe_changed.emit(self.recipe_dict())
        self._preview_timer.start()

    # ── 预览 ────────────────────────────────────────────────────
    def _sync_busy(self) -> None:
        busy = self._preview_busy or self._exporting
        self.top_bar.set_busy(busy)

    def _start_preview_render(self) -> None:
        if self._preview_source is None:
            return
        self._generation += 1
        generation = self._generation
        task = GradeRenderTask(generation, self._preview_source, self.deck.current_recipe())
        task.signals.finished.connect(self._on_preview_finished)
        task.signals.failed.connect(self._on_preview_failed)
        self._preview_busy = True
        self._sync_busy()
        self._pool.start(task)

    def _on_preview_finished(self, generation: int, image, analysis) -> None:
        if generation != self._generation:
            return
        self._preview_busy = False
        self._sync_busy()
        if image is None:
            self.canvas.set_message('预览渲染失败')
            return
        self.canvas.set_image(image)
        self.deck.set_analysis(analysis if isinstance(analysis, ToneAnalysis) else None)
        self.deck.update_histogram(image)

    def _on_preview_failed(self, generation: int, message: str) -> None:
        if generation != self._generation:
            return
        self._preview_busy = False
        self._sync_busy()
        self.canvas.set_message(f'预览渲染失败：{message}')
        self.status_message.emit(f'预览渲染失败：{message}')

    def _update_status_text(self, preview: np.ndarray | None = None) -> None:
        item = self._item
        if item is None:
            self._size_label.setText('—')
            self._space_label.setText('sRGB · 预览')
            return
        width = int(item.width or 0)
        height = int(item.height or 0)
        source = preview if preview is not None else self._preview_source
        if source is None:
            self._size_label.setText(f'{width}×{height}' if width and height else '—')
            self._space_label.setText('sRGB · 预览')
            return
        preview_height, preview_width = source.shape[:2]
        scale = 1.0
        if preview_width > 0:
            scale = max(1.0, (width or preview_width) / float(preview_width))
        size_text = f'{width}×{height}' if width and height else f'{preview_width}×{preview_height}'
        self._size_label.setText(f'{size_text} · 预览 1:{scale:.0f}')
        self._space_label.setText('sRGB · 16-bit 交接图')

    # ── 导出 ────────────────────────────────────────────────────
    def _begin_export(self, direct: bool) -> None:
        self.export_requested.emit(bool(direct))
        if self._exporting:
            return
        if not self._handoff_path or not Path(self._handoff_path).is_file():
            self.status_message.emit('交接图不存在，无法导出')
            return
        self._exporting = True
        self._export_direct = bool(direct)
        self._export_generation += 1
        generation = self._export_generation
        task = GradeFileRenderTask(generation, self._handoff_path, self.deck.current_recipe())
        task.signals.finished.connect(self._on_export_finished)
        task.signals.failed.connect(self._on_export_failed)
        self._sync_busy()
        self.status_message.emit('正在渲染全尺寸调色结果…')
        self._pool.start(task)

    def _on_export_finished(self, generation: int, image, analysis) -> None:
        if generation != self._export_generation:
            return
        self._exporting = False
        self._sync_busy()
        if image is None:
            self.status_message.emit('全尺寸渲染失败')
            return
        self.grade_image_ready.emit(image, self._export_direct)
        self.status_message.emit('全尺寸调色结果已渲染')

    def _on_export_failed(self, generation: int, message: str) -> None:
        if generation != self._export_generation:
            return
        self._exporting = False
        self._sync_busy()
        self.status_message.emit(f'全尺寸渲染失败：{message}')


__all__ = ['GradePage', 'GradeTopBar']
