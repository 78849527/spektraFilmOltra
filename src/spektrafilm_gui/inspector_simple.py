"""右侧调整台：直方图 + 胶片身份 + 基础参数 + 专业参数。

基础面板的每一行都是“代理控件”，真正读写仍落在原有编辑器上，
因此参数范围、步进、信号与持久化完全不经过第二套逻辑。
"""

from __future__ import annotations

from typing import Any

from qtpy import QtCore, QtGui, QtWidgets

from spektrafilm_gui.param_manifest import (
    CHEMISTRY_MANIFEST,
    DIR_COUPLERS_MANIFEST,
    GRAIN_MANIFEST,
    HALATION_MANIFEST,
    SIMULATION_ENLARGER_PANEL_FIELDS,
    SIMULATION_EXPOSURE_PANEL_FIELDS,
    TUNE_PANEL_FIELDS,
    _diffusion_manifest,
    SCANNER_MANIFEST,
)
from spektrafilm_gui.parameters_panel import build_professional_panel
from spektrafilm_gui.theme_oflim import ACCENT, TEXT_2, TEXT_3, TEXT_4
from spektrafilm_gui.ui_names import label_for, tip_for
from spektrafilm_gui.widget_editors import BoolEditor, EnumEditor, FloatEditor, SliderRowEditor
from spektrafilm_gui.widget_lookcard import FilmLookCard
from spektrafilm_gui.widget_primitives import CollapsibleSection

QCheckBox = QtWidgets.QCheckBox
QDoubleSpinBox = QtWidgets.QDoubleSpinBox
QFrame = QtWidgets.QFrame
QHBoxLayout = QtWidgets.QHBoxLayout
QLabel = QtWidgets.QLabel
QPainter = QtGui.QPainter
QPainterPath = QtGui.QPainterPath
QPushButton = QtWidgets.QPushButton
QScrollArea = QtWidgets.QScrollArea
QSizePolicy = QtWidgets.QSizePolicy
QStackedWidget = QtWidgets.QStackedWidget
QVBoxLayout = QtWidgets.QVBoxLayout
QWidget = QtWidgets.QWidget
Qt = QtCore.Qt
Signal = QtCore.Signal

_HIST_RED = '#C7705D'
_HIST_GREEN = '#7D9B76'
_HIST_BLUE = '#6B8CAE'


def _spec_from(manifest_or_fields, leaf: str):
    fields = getattr(manifest_or_fields, 'fields', manifest_or_fields)
    for spec in fields:
        if spec.leaf == leaf:
            return spec
    return None


class _Binding:
    """代理控件 ↔ 原始编辑器，单向写入 + 反向同步。"""

    def __init__(
        self,
        source: Any,
        *,
        proxy_signal,
        read_proxy,
        write_proxy,
        on_user_change,
    ):
        self.source = source
        self._read_proxy = read_proxy
        self._write_proxy = write_proxy
        self._on_user_change = on_user_change
        self._guard = False
        proxy_signal.connect(self._on_proxy)
        source_signal = self._source_signal(source)
        if source_signal is not None:
            source_signal.connect(self._on_source)
        self.refresh()

    @staticmethod
    def _source_signal(source: Any):
        toggled = getattr(source, 'toggled', None)
        if toggled is not None and hasattr(toggled, 'connect') and getattr(source, 'isCheckable', lambda: False)():
            return toggled
        for name in ('valueChanged', 'currentTextChanged', 'toggled'):
            signal = getattr(source, name, None)
            if signal is not None and hasattr(signal, 'connect'):
                return signal
        return None

    def _on_proxy(self, *_args) -> None:
        if self._guard:
            return
        value = self._read_proxy()
        self._guard = True
        try:
            self.source.value = value
        finally:
            self._guard = False
        self._on_user_change()

    def _on_source(self, *_args) -> None:
        if self._guard:
            return
        self.refresh()

    def refresh(self) -> None:
        self._guard = True
        try:
            self._write_proxy(self.source.value)
        finally:
            self._guard = False


class _DragSpin(QDoubleSpinBox):
    """无按钮数值框：左右拖动调值，双击输入。不设任何额外范围。"""

    def __init__(self, *, decimals: int = 2, minimum: float = -1_000_000.0, maximum: float = 1_000_000.0, step: float = 0.01):
        super().__init__()
        self.setObjectName('paramValue')
        self.setDecimals(decimals)
        self.setRange(minimum, maximum)
        self.setSingleStep(step)
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setKeyboardTracking(False)
        self.setFixedHeight(22)
        self.setFixedWidth(70)
        self.setCursor(Qt.SizeHorCursor)
        self.setToolTip('左右拖动调整，双击可直接输入')
        self._drag_origin = None

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.LeftButton:
            self._drag_origin = (event.position().x(), float(self.value()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._drag_origin is not None and event.buttons() & Qt.LeftButton:
            start_x, start_value = self._drag_origin
            factor = 0.1 if event.modifiers() & Qt.ShiftModifier else 10.0 if event.modifiers() & Qt.AltModifier else 1.0
            delta = (event.position().x() - start_x) * float(self.singleStep()) * factor
            self.setValue(start_value + delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._drag_origin = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._drag_origin = None
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().paintEvent(event)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, False)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 22), 1))
            y = self.height() - 1
            painter.drawLine(0, y, self.width(), y)
        finally:
            painter.end()


class _LabeledRow(QWidget):
    def __init__(self, label: str, control: QWidget, *, tooltip: str = '', parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(30)
        text = QLabel(label)
        text.setObjectName('paramLabel')
        if tooltip:
            text.setToolTip(tooltip)
            control.setToolTip(tooltip)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(text, 1, Qt.AlignVCenter)
        layout.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)


class FloatRow(_LabeledRow):
    def __init__(self, label: str, source: Any, *, tooltip: str = ''):
        decimals = int(getattr(source, 'decimals', lambda: 2)())
        minimum = float(getattr(source, 'minimum', lambda: -1_000_000.0)())
        maximum = float(getattr(source, 'maximum', lambda: 1_000_000.0)())
        step = float(getattr(source, 'singleStep', lambda: 0.01)())
        self.spin = _DragSpin(decimals=decimals, minimum=minimum, maximum=maximum, step=step)
        super().__init__(label, self.spin, tooltip=tooltip)
        self.binding = _Binding(
            source,
            proxy_signal=self.spin.valueChanged,
            read_proxy=lambda: self.spin.value(),
            write_proxy=lambda value: self.spin.setValue(float(value)),
            on_user_change=lambda: None,
        )

    def set_on_change(self, callback) -> None:
        self.binding._on_user_change = callback


class SliderRow(QWidget):
    def __init__(self, label: str, source: Any, spec, *, tooltip: str = ''):
        super().__init__()
        self.slider = SliderRowEditor(
            minimum=float(spec.min),
            maximum=float(spec.max),
            step=float(spec.step or 0.01),
            decimals=int(spec.decimals if spec.decimals is not None else 2),
        )
        self.slider.set_label_text(label)
        if tooltip:
            self.slider.setToolTip(tooltip)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.slider)
        self.binding = _Binding(
            source,
            proxy_signal=self.slider.valueChanged,
            read_proxy=lambda: self.slider.value,
            write_proxy=lambda value: setattr(self.slider, 'value', float(value)),
            on_user_change=lambda: None,
        )

    def set_on_change(self, callback) -> None:
        self.binding._on_user_change = callback


class ToggleRow(_LabeledRow):
    def __init__(self, label: str, source: Any, *, tooltip: str = ''):
        self.toggle = BoolEditor()
        super().__init__(label, self.toggle, tooltip=tooltip)
        self.binding = _Binding(
            source,
            proxy_signal=self.toggle.toggled,
            read_proxy=lambda: bool(self.toggle.value),
            write_proxy=lambda value: setattr(self.toggle, 'value', bool(value)),
            on_user_change=lambda: None,
        )

    def set_on_change(self, callback) -> None:
        self.binding._on_user_change = callback


class EnumRow(_LabeledRow):
    def __init__(self, label: str, source: Any, *, tooltip: str = ''):
        values = [source.itemText(index) for index in range(source.count())]
        self.combo = EnumEditor(values, enum_name=getattr(source, '_enum_name', None))
        self.combo.setFixedWidth(150)
        super().__init__(label, self.combo, tooltip=tooltip)
        self.binding = _Binding(
            source,
            proxy_signal=self.combo.currentTextChanged,
            read_proxy=lambda: self.combo.currentText(),
            write_proxy=lambda value: setattr(self.combo, 'value', str(value)),
            on_user_change=lambda: None,
        )

    def set_on_change(self, callback) -> None:
        self.binding._on_user_change = callback


class HistogramWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumHeight(58)
        self.setMaximumHeight(74)
        self._histograms: list[Any] | None = None

    def set_array(self, array) -> None:
        if array is None:
            self._histograms = None
            self.update()
            return
        try:
            import numpy as np

            data = np.asarray(array)
            if data.ndim == 2:
                data = np.repeat(data[..., None], 3, axis=2)
            data = data[..., :3]
            if data.dtype.kind == 'f':
                data = np.clip(data, 0.0, 1.0) * 255.0
            data = data.astype(np.uint8, copy=False)
            step = max(1, min(data.shape[0], data.shape[1]) // 256)
            sample = data[::step, ::step]
            histograms = []
            for channel in range(3):
                histogram, _edges = np.histogram(sample[..., channel], bins=128, range=(0, 255))
                histograms.append(histogram.astype(np.float32))
            self._histograms = histograms
        except (ValueError, TypeError, MemoryError):
            self._histograms = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            rect = self.rect().adjusted(0, 2, 0, -2)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 12), 1))
            for fraction in (0.25, 0.5, 0.75):
                x = rect.left() + rect.width() * fraction
                painter.drawLine(QtCore.QPointF(x, rect.top()), QtCore.QPointF(x, rect.bottom()))

            if not self._histograms:
                painter.setPen(QtGui.QColor(TEXT_4))
                painter.drawText(rect, Qt.AlignCenter, '等待预览')
                return

            maximum = max(float(hist.max(initial=0.0)) for hist in self._histograms) or 1.0
            colors = (_HIST_RED, _HIST_GREEN, _HIST_BLUE)
            for histogram, color in zip(self._histograms, colors):
                path = QPainterPath()
                count = len(histogram)
                path.moveTo(rect.left(), rect.bottom())
                for index, value in enumerate(histogram):
                    x = rect.left() + rect.width() * index / max(count - 1, 1)
                    normalized = float(value) / maximum
                    normalized = normalized ** 0.55
                    y = rect.bottom() - normalized * rect.height()
                    path.lineTo(x, y)
                path.lineTo(rect.right(), rect.bottom())
                path.closeSubpath()
                fill = QtGui.QColor(color)
                fill.setAlpha(64)
                painter.fillPath(path, fill)
                pen = QtGui.QPen(QtGui.QColor(color), 1.1)
                painter.setPen(pen)
                painter.drawPath(path)
        finally:
            painter.end()


class InspectorPanel(QWidget):
    reset_requested = Signal()

    def __init__(self, widgets, controller, viewer, *, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('inspectorPanel')
        self.setMinimumWidth(300)
        self._widgets = widgets
        self._controller = controller
        self._viewer = viewer
        self._bindings: list[_Binding] = []
        self._rows: dict[str, QWidget] = {}
        self._build_ui()

    def _editor(self, section: str, leaf: str):
        section_widget = getattr(self._widgets, section)
        return section_widget._editors[leaf]

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(14, 8, 14, 8)
        top_layout.setSpacing(8)
        top_layout.addWidget(self._build_histogram_card())
        look_card = getattr(self._widgets.simulation, 'look_card', None)
        if isinstance(look_card, FilmLookCard):
            top_layout.addWidget(look_card)
        top_layout.addWidget(self._build_segments())
        root.addWidget(top)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_basic_panel())
        self._stack.addWidget(self._build_professional_panel())
        root.addWidget(self._stack, 1)
        self._set_mode(0)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName('inspectorHeader')
        header.setFixedHeight(44)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(8)
        title = QLabel('调整')
        title.setObjectName('inspectorEyebrow')
        reset = QPushButton('重置')
        reset.setObjectName('headerResetButton')
        reset.setToolTip('把这张照片的参数恢复为默认')
        reset.setCursor(Qt.PointingHandCursor)
        reset.clicked.connect(self.reset_requested.emit)
        layout.addWidget(title, 0, Qt.AlignVCenter)
        layout.addStretch(1)
        layout.addWidget(reset, 0, Qt.AlignVCenter)
        return header

    def _build_histogram_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName('histogramCard')
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        caption = QLabel('亮度分布')
        caption.setObjectName('paramLabel')
        self.histogram = HistogramWidget()
        layout.addWidget(caption)
        layout.addWidget(self.histogram)
        return card

    def _build_segments(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._segment_group = QtWidgets.QButtonGroup(self)
        self._segment_group.setExclusive(True)
        self._basic_button = QPushButton('基础')
        self._professional_button = QPushButton('专业')
        for index, button in enumerate((self._basic_button, self._professional_button)):
            button.setObjectName('segmentButton')
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, target=index: self._set_mode(target))
            self._segment_group.addButton(button)
            layout.addWidget(button)
        layout.addStretch(1)
        return row

    def _build_basic_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 4, 14, 18)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignTop)

        layout.addWidget(self._section_title('光线'))
        auto = self._add_toggle(layout, '光线', '自动亮度补偿', 'simulation', 'print_exposure_compensation',
                                tip_for('print_exposure_compensation'))
        self._add_float(layout, None, '亮度', 'simulation', 'print_exposure', tip_for('print_exposure'))
        self._add_float(layout, None, '对比度', 'special', 'film_gamma_factor', tip_for('film_gamma_factor'))
        self._add_slider(layout, None, '高光柔化', 'chemistry', 'developer_exhaustion',
                         _spec_from(CHEMISTRY_MANIFEST, 'developer_exhaustion'), tip_for('developer_exhaustion'))

        layout.addWidget(self._section_title('色彩'))
        self._add_float(layout, None, '色温', 'simulation', 'print_y_filter_shift', tip_for('print_y_filter_shift'))
        self._add_float(layout, None, '色调', 'simulation', 'print_m_filter_shift', tip_for('print_m_filter_shift'))
        self._add_float(layout, None, '色彩浓度', 'couplers', 'inhibition_interlayer', tip_for('inhibition_interlayer'))

        layout.addWidget(self._section_title('质感'))
        grain_toggle = self._add_toggle(layout, None, '颗粒', 'grain', 'active', '给画面加入胶片颗粒。')
        grain_size = self._add_float(layout, None, '颗粒大小', 'grain', 'particle_area_um2', tip_for('particle_area_um2'))
        self._link_enabled(grain_toggle, [grain_size])

        halation_toggle = self._add_toggle(layout, None, '高光光晕', 'halation', 'active', '高光边缘的红橙色光晕。')
        halation_amount = self._add_float(layout, None, '光晕强度', 'halation', 'halation_amount', tip_for('halation_amount'))
        self._link_enabled(halation_toggle, [halation_amount])

        diffusion_toggle = self._add_toggle(layout, None, '柔光镜', 'camera_diffusion', 'active', '给高光加一层柔光。')
        diffusion_strength = self._add_slider(
            layout, None, '柔光强度', 'camera_diffusion', 'strength',
            _spec_from(_diffusion_manifest('Diffusion', 'camera.diffusion_filter'), 'strength'),
            tip_for('strength'),
        )
        diffusion_family = self._add_enum(layout, None, '柔光类型', 'camera_diffusion', 'filter_family', tip_for('filter_family'))
        self._link_enabled(diffusion_toggle, [diffusion_strength, diffusion_family])

        layout.addWidget(self._section_title('印相'))
        white_toggle = self._add_toggle(layout, None, '白场校正', 'scanner', 'white_correction', tip_for('white_correction'))
        white_level = self._add_slider(layout, None, '白场', 'scanner', 'white_level',
                                       _spec_from(SCANNER_MANIFEST, 'white_level'), tip_for('white_level'))
        self._link_enabled(white_toggle, [white_level])
        black_toggle = self._add_toggle(layout, None, '黑场校正', 'scanner', 'black_correction', tip_for('black_correction'))
        black_level = self._add_slider(layout, None, '黑场', 'scanner', 'black_level',
                                       _spec_from(SCANNER_MANIFEST, 'black_level'), tip_for('black_level'))
        self._link_enabled(black_toggle, [black_level])
        self._add_toggle(layout, None, '查看底片', 'simulation', 'scan_film', tip_for('scan_film'))

        scroll.setWidget(content)
        return scroll

    def _build_professional_panel(self) -> QWidget:
        return build_professional_panel(self._viewer, self._widgets)

    # ── 行构建 ──────────────────────────────────────────────────
    def _section_title(self, title: str) -> QWidget:
        label = QLabel(title)
        label.setObjectName('inspectorSectionLabel')
        label.setContentsMargins(0, 10, 0, 2)
        return label

    def _on_change(self) -> None:
        request = getattr(self._controller, 'request_auto_preview', None)
        if callable(request):
            request()

    def _register(self, leaf: str, row: QWidget, binding: _Binding) -> QWidget:
        binding._on_user_change = self._on_change
        self._bindings.append(binding)
        self._rows[leaf] = row
        return row

    def _add_float(self, layout, section_title, label: str, section: str, leaf: str, tooltip: str) -> QWidget:
        source = self._editor(section, leaf)
        row = FloatRow(label, source, tooltip=tooltip)
        self._register(leaf, row, row.binding)
        layout.addWidget(row)
        return row

    def _add_slider(self, layout, section_title, label: str, section: str, leaf: str, spec, tooltip: str) -> QWidget:
        if spec is None or spec.min is None or spec.max is None:
            return self._add_float(layout, section_title, label, section, leaf, tooltip)
        source = self._editor(section, leaf)
        row = SliderRow(label, source, spec, tooltip=tooltip)
        self._register(leaf, row, row.binding)
        layout.addWidget(row)
        return row

    def _add_toggle(self, layout, section_title, label: str, section: str, leaf: str, tooltip: str) -> QWidget:
        source = self._editor(section, leaf)
        row = ToggleRow(label, source, tooltip=tooltip)
        self._register(leaf, row, row.binding)
        layout.addWidget(row)
        return row

    def _add_enum(self, layout, section_title, label: str, section: str, leaf: str, tooltip: str) -> QWidget:
        source = self._editor(section, leaf)
        row = EnumRow(label, source, tooltip=tooltip)
        self._register(leaf, row, row.binding)
        layout.addWidget(row)
        return row

    @staticmethod
    def _link_enabled(toggle_row: QWidget, dependents: list[QWidget]) -> None:
        def apply(enabled: bool) -> None:
            for widget in dependents:
                widget.setEnabled(enabled)

        toggle = getattr(toggle_row, 'toggle', None)
        if toggle is None:
            return
        toggle.toggled.connect(apply)
        apply(bool(toggle.value))

    # ── 模式 / 刷新 ─────────────────────────────────────────────
    def _set_mode(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self._basic_button.setChecked(index == 0)
        self._professional_button.setChecked(index == 1)
        if index == 0:
            self.refresh()

    def set_mode(self, mode: str) -> None:
        self._set_mode(0 if mode == 'basic' else 1)

    def refresh(self) -> None:
        for binding in self._bindings:
            binding.refresh()

    def set_histogram(self, array) -> None:
        self.histogram.set_array(array)

    def row(self, leaf: str) -> QWidget | None:
        return self._rows.get(leaf)
