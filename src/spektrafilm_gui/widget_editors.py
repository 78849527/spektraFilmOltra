from __future__ import annotations

from functools import lru_cache
from typing import Any

from qtpy import QtCore, QtGui, QtWidgets

QPointF = getattr(QtCore, 'QPointF')
QRect = getattr(QtCore, 'QRect')
QSize = getattr(QtCore, 'QSize')
QStyle = QtWidgets.QStyle
QStyleOptionComboBox = QtWidgets.QStyleOptionComboBox
QStyledItemDelegate = QtWidgets.QStyledItemDelegate
QStylePainter = QtWidgets.QStylePainter

from spektrafilm.profiles.io import load_profile
from spektrafilm_gui.theme_palette import (
    ACCENT_COLOR_TEXT,
    ACCENT_COLOR_TEXT_SECONDARY,
    BOOL_EDITOR_BORDER_CHECKED,
    BOOL_EDITOR_BORDER_UNCHECKED,
    BOOL_EDITOR_CHECKED_DISABLED,
    BOOL_EDITOR_CHECKED_ENABLED,
    BOOL_EDITOR_CHECKMARK,
    BOOL_EDITOR_FILL_DISABLED,
    BOOL_EDITOR_FILL_ENABLED,
    BOOL_EDITOR_HOVER_BG,
    TEXT_FAINT,
    TEXT_PRIMARY,
    TEXT_SOFT,
)
from spektrafilm_gui.theme import resolve_theme_qcolor
from spektrafilm_gui.ui_names import enum_display, profile_display_name


def _make_compressible(combo: QtWidgets.QComboBox) -> None:
    """长选项不让下拉框撑爆侧栏宽度。"""
    combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(8)
    combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)


@lru_cache(maxsize=None)
def _profile_use_text_and_color(profile_name: str) -> tuple[str, str]:
    if not profile_name:
        return '', ACCENT_COLOR_TEXT
    try:
        profile = load_profile(profile_name)
    except (FileNotFoundError, TypeError, ValueError):
        return '', ACCENT_COLOR_TEXT
    if profile.is_cine:
        return '电影', ACCENT_COLOR_TEXT_SECONDARY
    if profile.is_still:
        return '静态', ACCENT_COLOR_TEXT
    return '', ACCENT_COLOR_TEXT


def _draw_profile_display_text(
    painter: QtGui.QPainter,
    rect: QtCore.QRect,
    *,
    profile_name: str,
    base_color: QtGui.QColor,
    font: QtGui.QFont,
    display_name: str | None = None,
) -> None:
    del profile_name
    painter.setPen(base_color)
    painter.setFont(font)
    painter.drawText(
        rect,
        QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft | QtCore.Qt.TextSingleLine,
        display_name or '',
    )


class ProfileEnumItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:  # noqa: N802 - Qt API name
        display_value = index.data(QtCore.Qt.DisplayRole) or ''
        style_option = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(style_option, index)
        style_option.text = ''

        style = style_option.widget.style() if style_option.widget is not None else QtWidgets.QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, style_option, painter, style_option.widget)

        text_color = style_option.palette.color(
            QtGui.QPalette.HighlightedText if style_option.state & QStyle.State_Selected else QtGui.QPalette.Text,
        )
        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, style_option, style_option.widget)
        kind = getattr(style_option.widget, '_profile_kind', None)
        _draw_profile_display_text(
            painter,
            text_rect.adjusted(0, 0, -4, 0),
            profile_name=display_value,
            display_name=profile_display_name(display_value, kind),
            base_color=text_color,
            font=style_option.font,
        )


class ProfileEnumEditor(QtWidgets.QComboBox):
    def __init__(self, values: list[str], *, kind: str | None = None):
        super().__init__()
        self._profile_kind = kind
        self.addItems(values)
        self.setItemDelegate(ProfileEnumItemDelegate(self))
        _make_compressible(self)
        if self.count() > 0 and self.currentIndex() < 0:
            self.setCurrentIndex(0)

    @staticmethod
    def display_text_for_value(value: str, kind: str | None = None) -> str:
        return profile_display_name(value, kind)

    @property
    def value(self) -> str:
        return self.currentText()

    @value.setter
    def value(self, value: str) -> None:
        index = self.findText(value)
        if index >= 0:
            self.setCurrentIndex(index)
        else:
            raise ValueError(f"{value!r} is not a valid option")

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        current_value = self.currentText() or (self.itemText(0) if self.count() > 0 else '')
        option.currentText = ''
        painter.drawComplexControl(QStyle.CC_ComboBox, option)
        painter.drawControl(QStyle.CE_ComboBoxLabel, option)
        text_rect = self.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxEditField, self)
        _draw_profile_display_text(
            painter,
            text_rect.adjusted(1, 0, -1, 0),
            profile_name=current_value,
            display_name=profile_display_name(current_value, self._profile_kind),
            base_color=option.palette.color(QtGui.QPalette.Text),
            font=self.font(),
        )


class FloatEditor(QtWidgets.QDoubleSpinBox):
    def __init__(self, *, decimals: int = 2, minimum: float = -1_000_000.0, maximum: float = 1_000_000.0):
        super().__init__()
        self.setDecimals(decimals)
        self.setMinimum(minimum)
        self.setMaximum(maximum)
        self.setKeyboardTracking(False)
        self.setFixedHeight(24)

    @property
    def value(self) -> float:
        return super().value()

    @value.setter
    def value(self, value: float) -> None:
        self.setValue(value)


class IntEditor(QtWidgets.QSpinBox):
    def __init__(self, *, minimum: int = -1_000_000, maximum: int = 1_000_000):
        super().__init__()
        self.setMinimum(minimum)
        self.setMaximum(maximum)
        self.setKeyboardTracking(False)
        self.setFixedHeight(24)

    @property
    def value(self) -> int:
        return super().value()

    @value.setter
    def value(self, value: int) -> None:
        self.setValue(value)


class BoolEditor(QtWidgets.QCheckBox):
    def __init__(self):
        super().__init__()
        self.setText('')
        self.setMouseTracking(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.setFixedHeight(24)
        # 自绘控件：背景交给父级卡片，避免露出窗口底色
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)

    @property
    def value(self) -> bool:
        return self.isChecked()

    @value.setter
    def value(self, value: bool) -> None:
        self.setChecked(value)

    def sizeHint(self):  # noqa: N802 - Qt API name
        return QSize(24, 24)

    def minimumSizeHint(self):  # noqa: N802 - Qt API name
        return self.sizeHint()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

            indicator_rect = self._indicator_rect()
            is_enabled = self.isEnabled()
            is_hovered = is_enabled and self.underMouse()
            fill_color = resolve_theme_qcolor(
                BOOL_EDITOR_HOVER_BG if is_hovered else BOOL_EDITOR_FILL_ENABLED if is_enabled else BOOL_EDITOR_FILL_DISABLED,
            )
            checked_color = resolve_theme_qcolor(
                BOOL_EDITOR_HOVER_BG if is_hovered else BOOL_EDITOR_CHECKED_ENABLED if is_enabled else BOOL_EDITOR_CHECKED_DISABLED,
            )
            border_color = resolve_theme_qcolor(BOOL_EDITOR_BORDER_CHECKED if self.isChecked() else BOOL_EDITOR_BORDER_UNCHECKED)

            painter.setPen(QtGui.QPen(border_color, 1))
            painter.setBrush(checked_color if self.isChecked() else fill_color)
            painter.drawRect(indicator_rect)

            if self.isChecked():
                self._draw_check_mark(painter, indicator_rect)
        finally:
            painter.end()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().leaveEvent(event)
        self.update()

    def _indicator_rect(self):
        return QRect(1, max(1, (self.height() - 14) // 2), 14, 14)

    @staticmethod
    def _draw_check_mark(painter: QtGui.QPainter, indicator_rect) -> None:
        painter.setPen(
            QtGui.QPen(resolve_theme_qcolor(BOOL_EDITOR_CHECKMARK), 1.6, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin),
        )
        painter.drawLine(
            QPointF(indicator_rect.left() + 3.0, indicator_rect.center().y() + 0.5),
            QPointF(indicator_rect.left() + 6.0, indicator_rect.bottom() - 3.5),
        )
        painter.drawLine(
            QPointF(indicator_rect.left() + 6.0, indicator_rect.bottom() - 3.5),
            QPointF(indicator_rect.right() - 2.5, indicator_rect.top() + 3.5),
        )


class EnumItemDelegate(QStyledItemDelegate):
    """下拉列表：显示中文，条目数据仍是原值。"""

    def paint(self, painter, option, index) -> None:  # noqa: N802 - Qt API name
        raw_value = index.data(QtCore.Qt.DisplayRole) or ''
        style_option = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(style_option, index)
        style_option.text = ''

        style = style_option.widget.style() if style_option.widget is not None else QtWidgets.QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, style_option, painter, style_option.widget)

        text_color = style_option.palette.color(
            QtGui.QPalette.HighlightedText if style_option.state & QStyle.State_Selected else QtGui.QPalette.Text,
        )
        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, style_option, style_option.widget)
        enum_name = getattr(style_option.widget, '_enum_name', None)
        painter.setPen(text_color)
        painter.setFont(style_option.font)
        painter.drawText(
            text_rect.adjusted(0, 0, -4, 0),
            QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft | QtCore.Qt.TextSingleLine,
            enum_display(enum_name, raw_value),
        )


class EnumEditor(QtWidgets.QComboBox):
    def __init__(self, values: list[str], *, enum_name: str | None = None):
        super().__init__()
        self._enum_name = enum_name
        self.addItems(values)
        self.setItemDelegate(EnumItemDelegate(self))
        _make_compressible(self)

    def display_text_for_value(self, value: str) -> str:
        return enum_display(self._enum_name, value)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        raw_text = self.currentText() or (self.itemText(0) if self.count() > 0 else '')
        option.currentText = ''
        painter.drawComplexControl(QStyle.CC_ComboBox, option)
        painter.drawControl(QStyle.CE_ComboBoxLabel, option)
        text_rect = self.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxEditField, self)
        text_rect = text_rect.adjusted(1, 0, -1, 0)
        display_text = self.display_text_for_value(raw_text)
        elided = self.fontMetrics().elidedText(display_text, QtCore.Qt.ElideRight, max(text_rect.width(), 10))
        painter.setPen(option.palette.color(QtGui.QPalette.Text))
        painter.setFont(self.font())
        painter.drawText(text_rect, QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft | QtCore.Qt.TextSingleLine, elided)

    @property
    def value(self) -> str:
        return self.currentText()

    @value.setter
    def value(self, value: str) -> None:
        index = self.findText(value)
        if index >= 0:
            self.setCurrentIndex(index)
        else:
            raise ValueError(f"{value!r} is not a valid option")


class TupleEditor(QtWidgets.QWidget):
    def __init__(self, editors: list[QtWidgets.QWidget]):
        super().__init__()
        self._editors = editors
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for editor in self._editors:
            editor.setMinimumWidth(56)
            editor.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
            layout.addWidget(editor)
        self.setLayout(layout)

    @property
    def editors(self) -> tuple[QtWidgets.QWidget, ...]:
        return tuple(self._editors)

    @property
    def value(self) -> tuple[Any, ...]:
        return tuple(editor.value for editor in self._editors)

    @value.setter
    def value(self, value: tuple[Any, ...]) -> None:
        for editor, component in zip(self._editors, value, strict=True):
            editor.value = component

    def setToolTip(self, text: str) -> None:  # noqa: N802 - Qt API name
        super().setToolTip(text)
        for editor in self._editors:
            editor.setToolTip(text)


class FloatTupleEditor(TupleEditor):
    def __init__(self, length: int, *, decimals: int = 2, minimum: float = -1_000_000.0, maximum: float = 1_000_000.0):
        super().__init__([FloatEditor(decimals=decimals, minimum=minimum, maximum=maximum) for _ in range(length)])


class IntTupleEditor(TupleEditor):
    def __init__(self, length: int, *, minimum: int = -1_000_000, maximum: int = 1_000_000):
        super().__init__([IntEditor(minimum=minimum, maximum=maximum) for _ in range(length)])


class SliderRowEditor(QtWidgets.QWidget):
    """oflim 滑块行：上行「标签 + 可编辑数值」，下行细轨道滑块。

    数值框保留精确输入能力（科学参数需要），滑块负责快速粗调；
    两者双向同步，对外只暴露 ``value`` / ``valueChanged``。
    """

    valueChanged = QtCore.Signal(float)

    def __init__(self, *, minimum: float = 0.0, maximum: float = 100.0, step: float = 1.0, decimals: int = 2, suffix: str = ''):
        super().__init__()
        self._minimum = float(minimum)
        self._maximum = float(maximum)
        self._step = float(step) if step and step > 0 else 0.01
        self._decimals = decimals
        self._suffix = suffix
        self._syncing = False

        self._title = QtWidgets.QLabel('')
        title_font = self._title.font()
        title_font.setPointSizeF(max(title_font.pointSizeF() - 0.5, 8.0))
        self._title.setFont(title_font)
        self._title.setStyleSheet(f'color: {TEXT_SOFT}; background: transparent;')
        self._title.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

        self._spin = QtWidgets.QDoubleSpinBox()
        self._spin.setDecimals(decimals)
        self._spin.setRange(self._minimum, self._maximum)
        self._spin.setSingleStep(self._step)
        self._spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self._spin.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self._spin.setFixedHeight(18)
        self._spin.setMinimumWidth(58)
        self._spin.setMaximumWidth(74)
        self._spin.setKeyboardTracking(False)
        if suffix:
            self._spin.setSuffix(suffix)
        value_font = self._spin.font()
        value_font.setPointSizeF(max(value_font.pointSizeF() - 0.5, 8.0))
        value_font.setFamily(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont).family())
        self._spin.setFont(value_font)
        self._spin.setStyleSheet(
            f'QDoubleSpinBox {{ background: transparent; border: none; color: {TEXT_SOFT}; '
            'padding: 0px; }'
            f'QDoubleSpinBox:hover {{ color: {TEXT_PRIMARY}; }}'
            f'QDoubleSpinBox:focus {{ color: {TEXT_PRIMARY}; }}'
        )

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        header.addWidget(self._title, 0, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        header.addStretch(1)
        header.addWidget(self._spin, 0, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        self._slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._slider.setRange(0, self._n_steps())
        self._slider.setFixedHeight(16)
        self._slider.setCursor(QtCore.Qt.PointingHandCursor)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(2)
        layout.addLayout(header)
        layout.addWidget(self._slider)

        self._slider.valueChanged.connect(self._on_slider_changed)
        self._spin.valueChanged.connect(self._on_spin_changed)

    def set_label_text(self, text: str) -> None:
        self._title.setText(text)

    def _n_steps(self) -> int:
        span = self._maximum - self._minimum
        if span <= 0 or self._step <= 0:
            return 0
        return max(1, int(round(span / self._step)))

    def _on_slider_changed(self, tick: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            value = self._minimum + tick * self._step
            self._spin.setValue(min(value, self._maximum))
        finally:
            self._syncing = False
        self.valueChanged.emit(self.value)

    def _on_spin_changed(self, value: float) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            tick = int(round((float(value) - self._minimum) / self._step))
            self._slider.setValue(max(0, min(self._slider.maximum(), tick)))
        finally:
            self._syncing = False
        self.valueChanged.emit(float(value))

    @property
    def value(self) -> float:
        return float(self._spin.value())

    @value.setter
    def value(self, v: float) -> None:
        self._syncing = True
        try:
            self._spin.setValue(float(v))
            tick = int(round((float(v) - self._minimum) / self._step))
            self._slider.setValue(max(0, min(self._slider.maximum(), tick)))
        finally:
            self._syncing = False

    def setMinimum(self, v: float) -> None:
        self._minimum = float(v)
        self._spin.setMinimum(self._minimum)
        self._slider.setRange(0, self._n_steps())

    def setMaximum(self, v: float) -> None:
        self._maximum = float(v)
        self._spin.setMaximum(self._maximum)
        self._slider.setRange(0, self._n_steps())

    def setSingleStep(self, v: float) -> None:
        self._step = float(v) if v and v > 0 else 0.01
        self._spin.setSingleStep(self._step)
        self._slider.setRange(0, self._n_steps())

    def setToolTip(self, text: str) -> None:
        super().setToolTip(text)
        self._slider.setToolTip(text)
        self._spin.setToolTip(text)
        self._title.setToolTip(text)


class SliderFloatEditor(QtWidgets.QWidget):
    """oflim 形态的滑块行：上行「标签 + 数值」，下行细轨道滑块。"""

    valueChanged = QtCore.Signal(float)

    def __init__(self, *, minimum: float = 0.0, maximum: float = 100.0, step: float = 1.0, decimals: int = 0, suffix: str = ''):
        super().__init__()
        self._minimum = minimum
        self._maximum = maximum
        self._step = step
        self._decimals = decimals
        self._suffix = suffix

        self._title = QtWidgets.QLabel('')
        title_font = self._title.font()
        title_font.setPointSizeF(max(title_font.pointSizeF() - 0.5, 8.0))
        self._title.setFont(title_font)
        self._title.setStyleSheet(f'color: {TEXT_SOFT}; background: transparent;')
        self._title.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

        self._label = QtWidgets.QLabel()
        self._label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        value_font = self._label.font()
        value_font.setPointSizeF(max(value_font.pointSizeF() - 0.5, 8.0))
        value_font.setFamily(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont).family())
        self._label.setFont(value_font)
        self._label.setMinimumWidth(46)
        self._label.setStyleSheet(f'color: {TEXT_SOFT}; background: transparent;')

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        header.addWidget(self._title, 0, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        header.addStretch(1)
        header.addWidget(self._label, 0, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        self._slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._slider.setRange(0, self._n_steps())
        self._slider.setFixedHeight(16)
        self._slider.setCursor(QtCore.Qt.PointingHandCursor)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(2)
        layout.addLayout(header)
        layout.addWidget(self._slider)

        self._slider.valueChanged.connect(self._on_slider_changed)
        self._update_label()

    def set_label_text(self, text: str) -> None:
        self._title.setText(text)

    def _n_steps(self) -> int:
        if self._step <= 0:
            return 0
        return int(round((self._maximum - self._minimum) / self._step))

    def _on_slider_changed(self, _tick: int) -> None:
        self._update_label()
        self.valueChanged.emit(self.value)

    def _update_label(self) -> None:
        self._label.setText(f'{self.value:.{self._decimals}f}{self._suffix}')

    @property
    def value(self) -> float:
        return self._minimum + self._slider.value() * self._step

    @value.setter
    def value(self, v: float) -> None:
        tick = int(round((v - self._minimum) / self._step))
        tick = max(0, min(self._slider.maximum(), tick))
        was_blocked = self._slider.blockSignals(True)
        self._slider.setValue(tick)
        self._slider.blockSignals(was_blocked)
        self._update_label()

    def setMinimum(self, v: float) -> None:
        self._minimum = v
        self._slider.setRange(0, self._n_steps())

    def setMaximum(self, v: float) -> None:
        self._maximum = v
        self._slider.setRange(0, self._n_steps())

    def setSingleStep(self, v: float) -> None:
        self._step = v
        self._slider.setRange(0, self._n_steps())

    def setToolTip(self, text: str) -> None:
        super().setToolTip(text)
        self._slider.setToolTip(text)
        self._label.setToolTip(text)
        self._title.setToolTip(text)