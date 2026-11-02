"""快速模式面板：12 个轴按 3 组排列，印相色彩使用二维色盘。"""

from __future__ import annotations

from typing import Mapping

from qtpy import QtCore, QtGui, QtWidgets

from spektrafilm_gui import motion
from spektrafilm_gui.quick_controls import AXES, PAD_CC_FULL_SCALE, QUICK_LAYOUT, QuickAxis
from spektrafilm_gui.quick_engine import STATUS_CUSTOM
from spektrafilm_gui.theme_oflim import (
    ACCENT,
    HAIRLINE_STRONG,
    SURFACE_3,
    TEXT_4,
    rgba,
)
from spektrafilm_gui.widget_primitives import WheelSafeSlider, tabular_font

Qt = QtCore.Qt
Signal = QtCore.Signal

PAD_CC_PER_UNIT = PAD_CC_FULL_SCALE / 100.0


def _format_value(axis: QuickAxis, value: float) -> str:
    decimals = max(0, int(axis.decimals))
    value = float(value)
    if abs(value) < 0.5 * 10 ** (-decimals):
        value = 0.0
    text = f'{value:.{decimals}f}'
    if decimals > 0 and '.' in text:
        text = text.rstrip('0').rstrip('.')
    if axis.lo < 0 and value > 0:
        text = f'+{text}'
    return f'{text}{axis.suffix}'


def _format_cc(value: float) -> str:
    """快速轴 q 值换算成 Kodak CC：满量程 ±100 对应 ±60 CC。"""
    cc = float(value) * PAD_CC_PER_UNIT
    if abs(cc) < 0.05:
        cc = 0.0
    text = f'{cc:.1f}'
    if text.endswith('.0'):
        text = text[:-2]
    if cc > 0:
        text = f'+{text}'
    return f'{text} CC'


class _StatusDot(QtWidgets.QLabel):
    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__('●', parent)
        self.setFixedWidth(10)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(f'color: {ACCENT}; font-size: 8px; background: transparent;')
        self.hide()


class QuickAxisRow(QtWidgets.QWidget):
    """一行快速轴：标签 / Custom 点 / 读数 / 滑块。"""

    def __init__(self, axis: QuickAxis, on_change, *, parent=None):
        super().__init__(parent)
        self._axis = axis
        self._on_change = on_change
        self._value = 0.0
        self._syncing = False
        self._available = True
        self._reason = ''
        self._custom_detail = ''
        self._native_detail = ''
        self.setFixedHeight(46)
        self.setToolTip(axis.tooltip)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(6)

        top = QtWidgets.QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)

        self._label = QtWidgets.QLabel(axis.label)
        self._label.setObjectName('deckLabel')
        self._label.setToolTip(axis.tooltip)
        self._dot = _StatusDot(self)
        self._readout = QtWidgets.QLabel('0')
        self._readout.setObjectName('deckValue')
        self._readout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._readout.setMinimumWidth(56)
        self._readout.setFont(tabular_font())

        top.addWidget(self._label, 1, Qt.AlignVCenter)
        top.addWidget(self._dot, 0, Qt.AlignVCenter)
        top.addWidget(self._readout, 0, Qt.AlignVCenter)
        layout.addLayout(top)

        self.slider = WheelSafeSlider(Qt.Horizontal)
        self.slider.setObjectName('deckSlider')
        self.slider.setRange(0, 1000)
        self.slider.setFixedHeight(14)
        self.slider.setCursor(Qt.PointingHandCursor)
        self.slider.setToolTip(axis.tooltip)
        layout.addWidget(self.slider)

        self.slider.valueChanged.connect(self._on_slider)
        self.slider.sliderReleased.connect(self._commit)
        self._label.mouseDoubleClickEvent = self._reset  # type: ignore[method-assign]
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._commit)

        self.set_value(0.0)

    def set_value(self, value: float) -> None:
        value = max(self._axis.lo, min(self._axis.hi, float(value)))
        self._value = value
        self._syncing = True
        try:
            self.slider.blockSignals(True)
            self.slider.setValue(self._to_position(value))
            self.slider.blockSignals(False)
        finally:
            self._syncing = False
        self._paint()

    def value(self) -> float:
        return float(self._value)

    def _to_position(self, value: float) -> int:
        span = self._axis.hi - self._axis.lo
        if span <= 0:
            return 0
        ratio = (float(value) - self._axis.lo) / span
        return max(0, min(1000, round(ratio * 1000)))

    def _from_position(self, position: int) -> float:
        span = self._axis.hi - self._axis.lo
        value = self._axis.lo + span * (position / 1000.0)
        step = self._axis.step or 0.01
        value = round(value / step) * step
        return max(self._axis.lo, min(self._axis.hi, value))

    def _on_slider(self, position: int) -> None:
        if self._syncing:
            return
        self._value = self._from_position(position)
        self._paint()
        self._timer.start()

    def _commit(self) -> None:
        self._timer.stop()
        if not self._available:
            return
        if self._on_change is not None:
            self._on_change(self._axis.name, self.value())

    def _reset(self, event) -> None:  # noqa: N802 - Qt API name
        if not self._available:
            event.accept()
            return
        self._timer.stop()
        self.set_value(0.0)
        self._commit()
        motion.fade_in(self._readout, duration=140, start=0.3)
        event.accept()

    def _paint(self) -> None:
        self._readout.setText(_format_value(self._axis, self._value))
        dirty = abs(self._value) > 1e-9
        for widget in (self._readout, self.slider):
            widget.setProperty('dirty', 'true' if dirty else 'false')
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def set_status(self, status: str, detail: str = '') -> None:
        custom = status == STATUS_CUSTOM
        self._dot.setVisible(custom)
        self._dot.setToolTip(detail)
        self._custom_detail = detail if custom else ''
        self._apply_tooltip()

    def set_native_detail(self, detail: str) -> None:
        self._native_detail = str(detail)
        self._apply_tooltip()

    def set_available(self, available: bool, reason: str = '') -> None:
        self._available = bool(available)
        self._reason = '' if self._available else str(reason)
        self.slider.setEnabled(self._available)
        color = '' if self._available else f'color: {TEXT_4};'
        self._label.setStyleSheet(color)
        self._readout.setStyleSheet(color)
        self._apply_tooltip()

    def _apply_tooltip(self) -> None:
        parts = [self._axis.tooltip]
        if self._native_detail:
            parts.append(f'当前原生值：\n{self._native_detail}')
        if not self._available and self._reason:
            parts.append(self._reason)
        if self._custom_detail:
            parts.append(self._custom_detail)
        tip = '\n'.join(parts)
        self.setToolTip(tip)
        self._label.setToolTip(tip)
        self.slider.setToolTip(tip)


class QuickColorPad(QtWidgets.QWidget):
    """印相色彩二维色盘。x = 暖冷，y = 品红/绿。"""

    preview_changed = Signal(float, float)
    committed = Signal(float, float)

    def __init__(self, *, parent=None):
        super().__init__(parent)
        self.setFixedSize(168, 112)
        self.setCursor(Qt.CrossCursor)
        self._tooltip = '拖动调整印相色彩；双击回到中心。方向以灰卡标定为准。'
        self.setToolTip(self._tooltip)
        self._x = 0.0
        self._y = 0.0
        self._dragging = False
        self._available = True
        self._reason = ''
        self._native_detail = ''
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._commit)

    def set_available(self, available: bool, reason: str = '') -> None:
        self._available = bool(available)
        self._reason = '' if self._available else str(reason)
        self.setEnabled(self._available)
        self._apply_tooltip()
        self.update()

    def set_native_detail(self, detail: str) -> None:
        self._native_detail = str(detail)
        self._apply_tooltip()

    def _apply_tooltip(self) -> None:
        parts = [self._tooltip]
        if self._native_detail:
            parts.append(f'当前原生值：\n{self._native_detail}')
        if self._reason:
            parts.append(self._reason)
        self.setToolTip('\n'.join(parts))

    def values(self) -> tuple[float, float]:
        return self._x, self._y

    def set_values(self, x: float, y: float) -> None:
        self._x = max(-100.0, min(100.0, float(x)))
        self._y = max(-100.0, min(100.0, float(y)))
        self.update()

    def _point_to_value(self, point: QtCore.QPointF) -> tuple[float, float]:
        width = max(float(self.width()), 1.0)
        height = max(float(self.height()), 1.0)
        x = (float(point.x()) / width) * 200.0 - 100.0
        y = 100.0 - (float(point.y()) / height) * 200.0
        return max(-100.0, min(100.0, x)), max(-100.0, min(100.0, y))

    def _value_to_point(self) -> QtCore.QPointF:
        width = float(self.width())
        height = float(self.height())
        x = (self._x + 100.0) / 200.0 * width
        y = (100.0 - self._y) / 200.0 * height
        return QtCore.QPointF(x, y)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() != Qt.LeftButton:
            return
        self._dragging = True
        self._update_from_point(event.position())
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if not self._dragging:
            return
        self._update_from_point(event.position())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() != Qt.LeftButton or not self._dragging:
            return
        self._dragging = False
        self._update_from_point(event.position())
        self._commit()
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() != Qt.LeftButton:
            return
        self.set_values(0.0, 0.0)
        self._commit()
        event.accept()

    def _update_from_point(self, point: QtCore.QPointF) -> None:
        self._x, self._y = self._point_to_value(point)
        self.update()
        self.preview_changed.emit(self._x, self._y)
        self._timer.start()

    def _commit(self) -> None:
        self._timer.stop()
        self.committed.emit(self._x, self._y)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        if not self._available:
            painter.setOpacity(0.45)

        rect = QtCore.QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        painter.setPen(QtGui.QPen(QtGui.QColor(HAIRLINE_STRONG), 1))
        painter.setBrush(QtGui.QColor(SURFACE_3))
        painter.drawRoundedRect(rect, 10, 10)

        center_x = self.width() / 2.0
        center_y = self.height() / 2.0
        grid_pen = QtGui.QPen(QtGui.QColor(rgba('#FFFFFF', 0.10)), 1)
        painter.setPen(grid_pen)
        painter.drawLine(QtCore.QPointF(center_x, 18), QtCore.QPointF(center_x, self.height() - 18))
        painter.drawLine(QtCore.QPointF(30, center_y), QtCore.QPointF(self.width() - 30, center_y))

        strong_pen = QtGui.QPen(QtGui.QColor(rgba('#FFFFFF', 0.22)), 1)
        painter.setPen(strong_pen)
        painter.drawEllipse(QtCore.QPointF(center_x, center_y), 3.0, 3.0)

        point = self._value_to_point()
        painter.setPen(QtGui.QPen(QtGui.QColor(rgba(ACCENT, 0.65)), 1))
        painter.drawEllipse(point, 7.0, 7.0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QtGui.QColor(ACCENT))
        painter.drawEllipse(point, 3.5, 3.5)

        painter.setPen(QtGui.QColor(TEXT_4))
        font = painter.font()
        font.setPointSizeF(9.0)
        painter.setFont(font)
        # 上品红 / 下绿 / 左暖 / 右冷：与原生 Y、M 位移的正负方向一致。
        painter.drawText(
            QtCore.QRectF(0, 3, self.width(), 14),
            Qt.AlignHCenter | Qt.AlignVCenter,
            '品红',
        )
        painter.drawText(
            QtCore.QRectF(0, self.height() - 17, self.width(), 14),
            Qt.AlignHCenter | Qt.AlignVCenter,
            '绿',
        )
        painter.drawText(QtCore.QRectF(4, center_y - 8, 26, 16), Qt.AlignLeft | Qt.AlignVCenter, '暖')
        painter.drawText(
            QtCore.QRectF(self.width() - 30, center_y - 8, 26, 16),
            Qt.AlignRight | Qt.AlignVCenter,
            '冷',
        )
        painter.end()


class QuickPanel(QtWidgets.QWidget):
    axis_changed = Signal(str, float)
    reset_all_requested = Signal()

    def __init__(self, *, parent=None):
        super().__init__(parent)
        self._rows: dict[str, QuickAxisRow] = {}
        self._pad: QuickColorPad | None = None
        self._pad_status: _StatusDot | None = None
        self._pad_readouts: dict[str, QtWidgets.QLabel] = {}
        self._syncing = False
        self._build()

    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(content)
        outer.setContentsMargins(0, 0, 0, 16)
        outer.setSpacing(0)

        card = QtWidgets.QFrame()
        card.setObjectName('deckCard')
        inner = QtWidgets.QVBoxLayout(card)
        inner.setContentsMargins(12, 10, 12, 11)
        inner.setSpacing(3)
        inner.setAlignment(Qt.AlignTop)

        for group_title, entries in QUICK_LAYOUT:
            if inner.count() > 0:
                inner.addSpacing(6)
            inner.addWidget(self._group_label(group_title))
            for entry in entries:
                if entry[0] == 'pad':
                    inner.addWidget(self._build_pad_block(entry))
                    continue
                axis = AXES[entry[1]]
                row = QuickAxisRow(axis, self._on_row_change)
                self._rows[axis.name] = row
                inner.addWidget(row)

        reset = QtWidgets.QPushButton('重置快速')
        reset.setObjectName('deckAction')
        reset.setCursor(Qt.PointingHandCursor)
        reset.setFixedHeight(28)
        reset.setToolTip('把快速模式负责的字段恢复到进入工程时的基线，不影响其他专业参数')
        reset.clicked.connect(self.reset_all_requested.emit)
        inner.addSpacing(8)
        inner.addWidget(reset)

        outer.addWidget(card)
        outer.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll)

    @staticmethod
    def _group_label(text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setObjectName('deckGroup')
        return label

    def _build_pad_block(self, entry: tuple) -> QtWidgets.QWidget:
        block = QtWidgets.QWidget()
        block.setObjectName('quickPadBlock')
        block.setAttribute(Qt.WA_StyledBackground, True)
        block.setStyleSheet('QWidget#quickPadBlock { background: transparent; }')
        layout = QtWidgets.QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        head = QtWidgets.QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(4)
        title = QtWidgets.QLabel(str(entry[1]))
        title.setObjectName('deckLabel')
        self._pad_status = _StatusDot(block)
        head.addWidget(title, 1, Qt.AlignVCenter)
        head.addWidget(self._pad_status, 0, Qt.AlignVCenter)
        layout.addLayout(head)

        self._pad = QuickColorPad(parent=block)
        self._pad.preview_changed.connect(self._on_pad_preview)
        self._pad.committed.connect(self._on_pad_commit)
        layout.addWidget(self._pad, 0, Qt.AlignHCenter)

        readouts = QtWidgets.QHBoxLayout()
        readouts.setContentsMargins(0, 0, 0, 0)
        readouts.setSpacing(8)
        for key, text in (('print_balance_y', '冷暖'), ('print_balance_m', '品红')):
            label = QtWidgets.QLabel(f'{text} 0 CC')
            label.setObjectName('deckValue')
            label.setFont(tabular_font())
            label.setAlignment(Qt.AlignCenter)
            self._pad_readouts[key] = label
            readouts.addWidget(label, 1)
        layout.addLayout(readouts)
        return block

    # ── 事件 ────────────────────────────────────────────────
    def _on_row_change(self, name: str, value: float) -> None:
        if self._syncing:
            return
        self.axis_changed.emit(name, value)

    def _on_pad_preview(self, x: float, y: float) -> None:
        self._update_pad_readouts(x, y)

    def _on_pad_commit(self, x: float, y: float) -> None:
        if self._syncing:
            return
        self.axis_changed.emit('print_balance_y', x)
        self.axis_changed.emit('print_balance_m', y)

    def _update_pad_readouts(self, x: float, y: float) -> None:
        for key, value in (('print_balance_y', x), ('print_balance_m', y)):
            label = self._pad_readouts.get(key)
            if label is None:
                continue
            prefix = '冷暖' if key == 'print_balance_y' else '品红'
            label.setText(f'{prefix} {_format_cc(value)}')

    # ── 对外 ────────────────────────────────────────────────
    def set_intents(self, intent: Mapping[str, float]) -> None:
        self._syncing = True
        try:
            for name, row in self._rows.items():
                row.set_value(float(intent.get(name, 0.0)))
            if self._pad is not None:
                self._pad.set_values(
                    float(intent.get('print_balance_y', 0.0)),
                    float(intent.get('print_balance_m', 0.0)),
                )
                self._update_pad_readouts(
                    float(intent.get('print_balance_y', 0.0)),
                    float(intent.get('print_balance_m', 0.0)),
                )
        finally:
            self._syncing = False

    def set_intent(self, name: str, value: float) -> None:
        row = self._rows.get(name)
        if row is not None:
            row.set_value(value)
        if self._pad is not None and name in {'print_balance_y', 'print_balance_m'}:
            x, y = self._pad.values()
            if name == 'print_balance_y':
                x = value
            else:
                y = value
            self._pad.set_values(x, y)
            self._update_pad_readouts(x, y)

    def set_availability(self, disabled: Mapping[str, str]) -> None:
        disabled = dict(disabled or {})
        for name, row in self._rows.items():
            reason = str(disabled.get(name, ''))
            row.set_available(not reason, reason)
        if self._pad is not None:
            reason = str(
                disabled.get('print_balance_y') or disabled.get('print_balance_m') or ''
            )
            self._pad.set_available(not reason, reason)

    def set_native_details(self, details: Mapping[str, str]) -> None:
        for name, row in self._rows.items():
            row.set_native_detail(str(details.get(name, '')))
        if self._pad is not None:
            parts = [
                str(details.get(key, '')).strip()
                for key in ('print_balance_y', 'print_balance_m')
            ]
            self._pad.set_native_detail('\n'.join(part for part in parts if part))

    def set_statuses(self, statuses: Mapping[str, str]) -> None:
        for name, row in self._rows.items():
            status = statuses.get(name, 'normal')
            detail = '' if status == 'normal' else '专业模式改动了该控制拥有的字段；拖动本行会覆盖这些改动。'
            row.set_status(status, detail)
        if self._pad is not None and self._pad_status is not None:
            custom_names = [
                name
                for name in ('print_balance_y', 'print_balance_m')
                if statuses.get(name, 'normal') != 'normal'
            ]
            self._pad_status.setVisible(bool(custom_names))
            if custom_names:
                self._pad_status.setToolTip(
                    '专业模式改动了印相滤色片字段；拖动色盘会覆盖这些改动。'
                )

    def dirty_count(self) -> int:
        count = sum(1 for row in self._rows.values() if abs(row.value()) > 1e-9)
        if self._pad is not None:
            x, y = self._pad.values()
            count += int(abs(x) > 1e-9) + int(abs(y) > 1e-9)
        return count

    def row(self, name: str) -> QuickAxisRow | None:
        return self._rows.get(name)


__all__ = ['QuickAxisRow', 'QuickColorPad', 'QuickPanel']
