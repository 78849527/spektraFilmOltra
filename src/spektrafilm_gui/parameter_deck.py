"""右侧显影台：光影 / 色彩 / 胶片 / 画面。

尺寸与层级严格对齐 oflim 的 InspectorView：
- 面板左右留白 16，顶部 14，底部 24；区块间距 10
- 行高 38，行内标签 10.5，读数 9.5 等宽且只在「改过」时变黄铜
- 分组标签 8px、字距 1.1、四级灰
- 参数内容装在 surface2 圆角 11 的卡片里，内边距 12

参数读写仍然回到 widget_sections 的原始编辑器，不改任何取值范围。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from qtpy import QtCore, QtGui, QtWidgets

from spektrafilm_gui import motion, shell_icons
from spektrafilm_gui.param_manifest import (
    CAMERA_DIFFUSION_MANIFEST,
    CAMERA_MANIFEST,
    CHEMISTRY_MANIFEST,
    DIR_COUPLERS_MANIFEST,
    DISPLAY_PANEL_FIELDS,
    ENLARGER_DIFFUSION_MANIFEST,
    GLARE_MANIFEST,
    GRAIN_MANIFEST,
    HALATION_MANIFEST,
    INPUT_GAMUT_COMPRESS_MANIFEST,
    INPUT_IMAGE_FIELDS,
    OUTPUT_GAMUT_COMPRESS_MANIFEST,
    ParamSpec,
    SCANNER_MANIFEST,
    SIMULATION_FIELDS,
    SPECIAL_FIELDS,
)
from spektrafilm_gui.quick_controls import AXES, DISABLED_REASON, disabled_axes
from spektrafilm_gui.quick_engine import QuickEngine
from spektrafilm_gui.quick_panel import QuickPanel
from spektrafilm_gui.state_bridge import apply_gui_state, collect_gui_state
from spektrafilm_gui.widget_sections import LOAD_RAW_FIELDS
from spektrafilm_gui.theme_oflim import (
    ACCENT,
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
from spektrafilm_gui.ui_names import technical_label_for, tip_for
from spektrafilm_gui.widget_primitives import WheelSafeSlider, platform_default_font, tabular_font

Qt = QtCore.Qt

ROW_HEIGHT = 44
TOGGLE_HEIGHT = 44
ENUM_HEIGHT = 44
GROUP_HEIGHT = 26
PANEL_MARGIN = 14


@dataclass(frozen=True)
class Slider:
    section: str
    leaf: str
    label: str
    lo: float
    hi: float
    step: float = 0.01
    decimals: int = 2
    group: str = ''
    # 'linear'：滑条线性映射原始值；'brightness_stops'：滑条按「档」(2^n) 标度，
    # 右=显示值更大=画面更亮，读数显示 ±档位。用于"乘性曝光、越大越暗"的引擎参数。
    mode: str = 'linear'
    enforce_range: bool = False


@dataclass(frozen=True)
class Number:
    section: str
    leaf: str
    label: str
    group: str = ''


@dataclass(frozen=True)
class Vec:
    section: str
    leaf: str
    label: str
    group: str = ''


@dataclass(frozen=True)
class Toggle:
    section: str
    leaf: str
    label: str
    group: str = ''


@dataclass(frozen=True)
class Choice:
    section: str
    leaf: str
    label: str
    group: str = ''


@dataclass(frozen=True)
class Group:
    text: str


@dataclass(frozen=True)
class Action:
    text: str
    action: str


# ── 五页内容 ────────────────────────────────────────────────────

LIGHT_PAGE = [
    Group('曝光'),
    Slider('simulation', 'print_exposure', '亮度', 0.25, 4.0, 0.01, 2, mode='brightness_stops', enforce_range=True),
    Toggle('simulation', 'print_exposure_compensation', '自动亮度补偿'),
    Slider('special', 'film_gamma_factor', '明暗对比', 0.5, 1.8, 0.01, 2, enforce_range=True),
    Slider('chemistry', 'developer_exhaustion', '高光柔和度', 0.0, 1.0, 0.01, 2, enforce_range=True),
    Slider('camera', 'exposure_compensation_ev', '曝光补偿', -5.0, 5.0, 0.25, 1, enforce_range=True),
    Toggle('camera', 'auto_exposure', '自动测光'),
    Choice('camera', 'auto_exposure_method', '测光方式'),
    Group('印相'),
    Toggle('scanner', 'white_correction', '白场校正'),
    Slider('scanner', 'white_level', '白场', 0.75, 1.0, 0.005, 3, enforce_range=True),
    Toggle('scanner', 'black_correction', '黑场校正'),
    Slider('scanner', 'black_level', '黑场', 0.001, 0.08, 0.001, 3, enforce_range=True),
    Toggle('glare', 'active', '启用眩光'),
    Slider('glare', 'percent', '眩光', 0.0, 1.0, 0.01, 2, enforce_range=True),
    Slider('glare', 'roughness', '眩光粗糙度', 0.0, 1.0, 0.01, 2, enforce_range=True),
    Slider('preflashing', 'preflash_exposure', '预闪曝光', 0.0, 0.3, 0.005, 3, enforce_range=True),
]

COLOR_PAGE = [
    Group('白平衡'),
    Slider('simulation', 'print_y_filter_shift', '冷暖', -60.0, 60.0, 1.0, 0, enforce_range=True),
    Slider('simulation', 'print_m_filter_shift', '绿与品红', -60.0, 60.0, 1.0, 0, enforce_range=True),
    Choice('simulation', 'print_illuminant', '印相光源'),
    Group('浓度'),
    Toggle('couplers', 'active', '启用成色剂'),
    Slider('couplers', 'inhibition_interlayer', '颜色浓度', 0.0, 1.5, 0.01, 2, enforce_range=True),
    Slider('couplers', 'inhibition_samelayer', '层次反差', 0.0, 1.5, 0.01, 2, enforce_range=True),
    Slider('couplers', 'amount', '成色剂强度', 0.0, 1.5, 0.01, 2, enforce_range=True),
    Slider('couplers', 'diffusion_size_um', '染色扩散', 0.0, 30.0, 1.0, 0, enforce_range=True),
    Group('分色'),
    Slider('chemistry', 'gamma_factor_red', '红色反差', 0.5, 2.0, 0.01, 2, enforce_range=True),
    Slider('chemistry', 'gamma_factor_green', '绿色反差', 0.5, 2.0, 0.01, 2, enforce_range=True),
    Slider('chemistry', 'gamma_factor_blue', '蓝色反差', 0.5, 2.0, 0.01, 2, enforce_range=True),
    Group('预闪'),
    Slider('preflashing', 'preflash_y_filter_shift', '预闪冷暖', -40.0, 40.0, 1.0, 0, enforce_range=True),
    Slider('preflashing', 'preflash_m_filter_shift', '预闪品红', -40.0, 40.0, 1.0, 0, enforce_range=True),
]

FILM_PAGE = [
    Group('型号'),
    Choice('simulation', 'film_stock', '胶片'),
    Choice('simulation', 'print_paper', '相纸'),
    Group('颗粒'),
    Toggle('grain', 'active', '启用颗粒'),
    Slider('grain', 'particle_area_um2', '颗粒粗细', 0.02, 0.8, 0.01, 2, enforce_range=True),
    Slider('grain', 'blur', '颗粒柔和', 0.0, 1.5, 0.01, 2, enforce_range=True),
    Slider('grain', 'blur_dye_clouds_um', '染料云', 0.0, 2.0, 0.05, 2, enforce_range=True),
    Group('光晕'),
    Toggle('halation', 'active', '启用光晕'),
    Slider('halation', 'halation_amount', '高光红晕', 0.0, 2.0, 0.01, 2, enforce_range=True),
    Slider('halation', 'scatter_amount', '高光辉光', 0.0, 2.0, 0.01, 2, enforce_range=True),
    Slider('halation', 'halation_spatial_scale', '红晕扩散', 0.0, 3.0, 0.05, 2, enforce_range=True),
    Slider('halation', 'boost_ev', '高光提亮', 0.0, 4.0, 0.1, 1, enforce_range=True),
    Slider('halation', 'protect_ev', '高光保护', 0.0, 6.0, 0.1, 1, enforce_range=True),
    Group('显影'),
    Toggle('chemistry', 'active', '启用显影曲线'),
    Slider('chemistry', 'gamma_factor', '显影反差', 0.5, 2.0, 0.01, 2, enforce_range=True),
    Slider('chemistry', 'gamma_factor_fast', '快层反差', 0.5, 2.0, 0.01, 2, enforce_range=True),
    Slider('chemistry', 'gamma_factor_slow', '慢层反差', 0.5, 2.0, 0.01, 2, enforce_range=True),
]

FRAME_PAGE = [
    Group('清晰'),
    Slider('scanner', 'lens_blur', '镜头柔化', 0.0, 2.0, 0.01, 2, enforce_range=True),
    Slider('camera', 'lens_blur_um', '拍摄柔化', 0.0, 10.0, 0.1, 1, enforce_range=True),
    Toggle('camera_diffusion', 'active', '启用柔光'),
    Slider('camera_diffusion', 'strength', '柔光强度', 0.0, 2.0, 0.01, 2, enforce_range=True),
    Choice('camera_diffusion', 'filter_family', '柔光类型'),
    Group('构图'),
    Slider('camera', 'film_format_mm', '画幅', 8.0, 120.0, 1.0, 0, enforce_range=True),
    Slider('display', 'white_padding', '白边', 0.0, 1.0, 0.002, 3, enforce_range=True),
    Group('输出'),
    Choice('simulation', 'output_color_space', '输出色彩空间'),
    Choice('simulation', 'saving_color_space', '保存色彩空间'),
    Toggle('simulation', 'saving_cctf_encoding', '保存时写入亮度编码'),
]

INPUT_PAGE = [
    Group('RAW 解码'),
    Choice('load_raw', 'white_balance', '白平衡'),
    Slider('load_raw', 'temperature', '色温', 1000.0, 10000.0, 100.0, 0, enforce_range=True),
    Slider('load_raw', 'tint', '色调', 0.5, 2.0, 0.01, 2, enforce_range=True),
    Toggle('load_raw', 'lens_correction', '镜头校正'),
    Action('重新解码 RAW', 'reprocess_raw'),
    Group('输入'),
    Choice('input_image', 'input_color_space', '色彩空间'),
    Toggle('input_image', 'input_cctf_decoding', 'CCTF 解码'),
    Toggle('input_image', 'crop', '裁切'),
    Vec('input_image', 'crop_center', '裁切中心'),
    Vec('input_image', 'crop_size', '裁切大小'),
    Slider('input_image', 'upscale_factor', '放大', 1.0, 4.0, 0.05, 2, enforce_range=True),
    Group('光谱上采样'),
    Choice('input_image', 'rgb_to_raw_method', '上采样方法'),
    Toggle('input_image', 'apply_hanatos2025_adaptation_window', '适应窗口'),
    Toggle('input_image', 'apply_hanatos2025_adaptation_surface', '适应表面'),
    Slider('input_image', 'spectral_gaussian_blur', '光谱模糊', 0.0, 2.0, 0.1, 2, enforce_range=True),
]

PAGES = (
    ('光影', LIGHT_PAGE),
    ('色彩', COLOR_PAGE),
    ('胶片', FILM_PAGE),
    ('画面', FRAME_PAGE),
    ('输入', INPUT_PAGE),
)
PRO_PAGE_LABEL = '高级'

_PRO_SECTION_SPECS: dict[str, tuple[ParamSpec, ...]] = {
    'grain': GRAIN_MANIFEST.fields,
    'halation': HALATION_MANIFEST.fields,
    'couplers': DIR_COUPLERS_MANIFEST.fields,
    'chemistry': CHEMISTRY_MANIFEST.fields,
    'glare': GLARE_MANIFEST.fields,
    'scanner': SCANNER_MANIFEST.fields,
    'camera_diffusion': CAMERA_DIFFUSION_MANIFEST.fields,
    'enlarger_diffusion': ENLARGER_DIFFUSION_MANIFEST.fields,
    'input_gamut_compress': INPUT_GAMUT_COMPRESS_MANIFEST.fields,
    'output_gamut_compress': OUTPUT_GAMUT_COMPRESS_MANIFEST.fields,
    'display': DISPLAY_PANEL_FIELDS,
    'special': SPECIAL_FIELDS,
    'simulation': SIMULATION_FIELDS,
    'input_image': INPUT_IMAGE_FIELDS,
    'load_raw': tuple(LOAD_RAW_FIELDS),
}

_PRO_SECTION_TITLES = {
    'grain': '颗粒高级',
    'halation': '光晕高级',
    'couplers': '成色剂高级',
    'chemistry': '显影曲线',
    'glare': '眩光',
    'scanner': '扫描',
    'camera_diffusion': '柔光高级',
    'enlarger_diffusion': '放大机扩散',
    'input_gamut_compress': '输入色域压缩',
    'output_gamut_compress': '输出色域压缩',
    'display': '显示',
    'special': '实验',
    'simulation': '流程',
    'input_image': '输入补充',
    'load_raw': 'RAW 补充',
}

_PRO_SECTION_ORDER = (
    'grain',
    'halation',
    'couplers',
    'chemistry',
    'glare',
    'scanner',
    'camera_diffusion',
    'enlarger_diffusion',
    'input_gamut_compress',
    'output_gamut_compress',
    'display',
    'special',
    'simulation',
    'input_image',
    'load_raw',
)

_SPEC_REGISTRY: dict[tuple[str, str], ParamSpec] = {}
for _section, _specs in _PRO_SECTION_SPECS.items():
    for _spec in _specs:
        _SPEC_REGISTRY[(_section, _spec.leaf)] = _spec

_DISPLAY_SKIPPED = {'preview_max_size'}

DECK_STYLE = f"""
QWidget#paramDeck {{
    background: {SURFACE_0};
    border-left: 1px solid {HAIRLINE};
}}
/* 参数页滚动条：细而无衬底，悬停可拖 */
QScrollArea QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 4px 2px 4px 0;
}}
QScrollArea QScrollBar::handle:vertical {{
    background: {rgba('#FFFFFF', 0.14)};
    border-radius: 3px;
    min-height: 32px;
}}
QScrollArea QScrollBar::handle:vertical:hover {{ background: {rgba('#FFFFFF', 0.24)}; }}
QScrollArea QScrollBar::add-line:vertical,
QScrollArea QScrollBar::sub-line:vertical,
QScrollArea QScrollBar::add-page:vertical,
QScrollArea QScrollBar::sub-page:vertical {{
    background: none;
    height: 0px;
    width: 0px;
    border: none;
}}
QWidget#deckHeader {{ background: transparent; }}
QLabel#deckBadge {{
    color: {ACCENT};
    font-size: 11px;
    font-weight: 500;
    background: {rgba(ACCENT, 0.10)};
    border-radius: 7px;
    padding: 1px 6px;
}}
QPushButton#deckReset {{
    color: {TEXT_2}; background: transparent;
    border: 1px solid {HAIRLINE}; border-radius: 8px;
    font-size: 12px; font-weight: 500;
    padding: 0px 12px;
}}
QPushButton#deckReset:hover {{ background: {SURFACE_2}; border-color: {HAIRLINE_STRONG}; color: {TEXT_1}; }}

QFrame#deckHistogram {{
    background: {SURFACE_2};
    border: 1px solid {HAIRLINE};
    border-radius: 12px;
}}
QLabel#deckHistogramTitle {{
    color: {TEXT_2}; font-size: 11px; font-weight: 500;
}}
QLabel#deckHistogramMeta {{
    color: {TEXT_3}; font-size: 11px;
}}

QFrame#deckCard {{
    background: {SURFACE_2};
    border: 1px solid {HAIRLINE};
    border-radius: 12px;
}}
QLabel#deckGroup {{
    color: {TEXT_3}; font-size: 11px; font-weight: 600;
}}
QLabel#deckLabel {{ color: {TEXT_2}; font-size: 12px; background: transparent; }}
QLabel#deckValue {{
    color: {TEXT_3}; font-size: 12px; background: transparent;
}}
QLabel#deckValue[dirty="true"] {{ color: {ACCENT}; }}

QDoubleSpinBox#deckNumber, QSpinBox#deckNumber {{
    background: transparent; border: none; color: {TEXT_2};
    font-size: 12px; padding: 0; min-height: 22px;
}}
QDoubleSpinBox#deckNumber:hover, QSpinBox#deckNumber:hover {{ color: {TEXT_1}; }}
QDoubleSpinBox#deckNumber:focus, QSpinBox#deckNumber:focus {{ color: {TEXT_1}; }}
QDoubleSpinBox#deckNumber:disabled, QSpinBox#deckNumber:disabled {{ color: {TEXT_4}; }}
QDoubleSpinBox#deckNumber[dirty="true"], QSpinBox#deckNumber[dirty="true"] {{ color: {ACCENT}; }}

QPushButton#deckAction {{
    background: {SURFACE_2}; color: {TEXT_2};
    border: 1px solid {HAIRLINE}; border-radius: 8px;
    font-size: 12px; min-height: 28px;
}}
QPushButton#deckAction:hover {{ color: {TEXT_1}; border-color: {HAIRLINE_STRONG}; }}

QSlider#deckSlider {{ background: transparent; }}
QSlider#deckSlider::groove:horizontal {{
    height: 3px; background: {SURFACE_4}; border-radius: 1.5px;
}}
/* 填充段：white 22% 叠在面板上，收进中性阶 */
QSlider#deckSlider::sub-page:horizontal {{
    height: 3px; background: {rgba('#FFFFFF', 0.22)}; border-radius: 1.5px;
}}
QSlider#deckSlider[dirty="true"]::sub-page:horizontal {{
    height: 3px; background: {ACCENT}; border-radius: 1.5px;
}}
QSlider#deckSlider::handle:horizontal {{
    width: 11px; height: 11px; margin: -5px 0;
    border-radius: 5px; background: #ECE9E2;
    border: 1px solid rgba(0, 0, 0, 0.35);
}}
QSlider#deckSlider::handle:horizontal:hover {{ background: #FFFFFF; }}

QComboBox#deckCombo {{
    color: {TEXT_2}; background: transparent;
    border: none; border-radius: 0px;
    padding: 0px 14px 0px 0px;
    font-size: 12px;
}}
QComboBox#deckCombo:hover {{ color: {TEXT_1}; }}
QComboBox#deckCombo::drop-down {{ border: none; width: 0px; background: transparent; }}
QComboBox#deckCombo::down-arrow {{ image: none; width: 0px; height: 0px; }}
QComboBox#deckCombo QAbstractItemView {{
    background: {SURFACE_2}; color: {TEXT_1};
    border: 1px solid {HAIRLINE}; border-radius: 8px;
    selection-background-color: {SURFACE_3};
    outline: none; padding: 4px;
    font-size: 12px;
}}
"""


def _editor(widgets, section: str, leaf: str):
    holder = getattr(widgets, section, None)
    if holder is None:
        return None
    editors = getattr(holder, '_editors', None)
    if editors:
        editor = editors.get(leaf)
        if editor is not None:
            return editor
    editor = getattr(holder, leaf, None)
    return editor if hasattr(editor, 'value') else None


def _refresh_signal(source):
    for name in ('valueChanged', 'toggled', 'currentTextChanged'):
        signal = getattr(source, name, None)
        if signal is not None and hasattr(signal, 'connect'):
            return signal
    return None


def _tooltip(leaf: str, label: str) -> str:
    original = technical_label_for(leaf)
    hint = tip_for(leaf)
    head = original if original and original != label else leaf
    return f'{head}\n{hint}' if hint else head


class _Row(QtWidgets.QWidget):
    """参数行：38px，上行标签 + 读数，下行控件。"""

    def __init__(self, label: str, leaf: str, *, height: int, parent=None):
        super().__init__(parent)
        self._leaf = leaf
        self.setFixedHeight(height)
        self.setAttribute(Qt.WA_Hover, True)
        tip = _tooltip(leaf, label)
        self.setToolTip(tip)

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 3, 0, 3)
        self._layout.setSpacing(6)

        self._top = QtWidgets.QHBoxLayout()
        self._top.setContentsMargins(0, 0, 0, 0)
        self._top.setSpacing(6)
        self._label = QtWidgets.QLabel(label)
        self._label.setObjectName('deckLabel')
        self._label.setToolTip(tip)
        self._value = QtWidgets.QLabel('')
        self._value.setObjectName('deckValue')
        self._value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._value.setMinimumWidth(52)
        self._value.setFont(tabular_font())
        self._top.addWidget(self._label, 1, Qt.AlignVCenter)
        self._top.addWidget(self._value, 0, Qt.AlignVCenter)
        self._layout.addLayout(self._top)

    def _hover_changed(self, hovering: bool) -> None:
        color = TEXT_1 if hovering else TEXT_2
        self._label.setStyleSheet(f'color: {color};')

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._hover_changed(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._hover_changed(False)
        super().leaveEvent(event)


class SliderRow(_Row):
    def __init__(self, spec: Slider, source, on_change, *, parent=None):
        super().__init__(spec.label, spec.leaf, height=ROW_HEIGHT, parent=parent)
        self._spec = spec
        self._source = source
        self._on_change = on_change
        self._syncing = False
        self._stops_mode = spec.mode == 'brightness_stops'
        if self._stops_mode:
            # 亮度档位标度：滑条线性走「档」，右=更亮；raw = 2**(-档)
            self._lo_stops = -math.log2(max(float(spec.hi), 1e-9))
            self._hi_stops = -math.log2(max(float(spec.lo), 1e-9))

        try:
            self._baseline = float(source.value)
        except (TypeError, ValueError):
            self._baseline = spec.lo
        if spec.enforce_range:
            self._baseline = max(spec.lo, min(spec.hi, self._baseline))
            self._write(self._baseline)

        self.slider = WheelSafeSlider(Qt.Horizontal)
        self.slider.setObjectName('deckSlider')
        self.slider.setRange(0, 1000)
        self.slider.setFixedHeight(14)
        self.slider.setCursor(Qt.PointingHandCursor)
        self.slider.setToolTip(self.toolTip())
        self._layout.addWidget(self.slider)

        self.slider.valueChanged.connect(self._on_slider)
        self.slider.sliderReleased.connect(self._commit)
        self._label.mouseDoubleClickEvent = self._reset  # type: ignore[method-assign]

        signal = _refresh_signal(source)
        if signal is not None:
            signal.connect(self.sync_from_source)
        self._pull_initial()

    # 值与位置
    def _to_position(self, value: float) -> int:
        if self._stops_mode:
            span = self._hi_stops - self._lo_stops
            if span <= 0:
                return 0
            stops = -math.log2(max(float(value), 1e-9))
            ratio = (stops - self._lo_stops) / span
            return max(0, min(1000, round(ratio * 1000)))
        span = self._spec.hi - self._spec.lo
        if span <= 0:
            return 0
        ratio = (float(value) - self._spec.lo) / span
        return max(0, min(1000, round(ratio * 1000)))

    def _from_position(self, position: int) -> float:
        if self._stops_mode:
            span = self._hi_stops - self._lo_stops
            stops = self._lo_stops + span * (position / 1000.0)
            step = self._spec.step or 0.01
            if step > 0:
                stops = round(stops / step) * step
            stops = max(self._lo_stops, min(self._hi_stops, stops))
            value = 2.0 ** (-stops)
            return max(self._spec.lo, min(self._spec.hi, value))
        span = self._spec.hi - self._spec.lo
        value = self._spec.lo + span * (position / 1000.0)
        step = self._spec.step or 0.01
        if step > 0:
            value = round(value / step) * step
        return max(self._spec.lo, min(self._spec.hi, value))

    def _format(self, value: float) -> str:
        decimals = max(0, int(self._spec.decimals))
        if self._stops_mode:
            value = max(self._spec.lo, min(self._spec.hi, float(value)))
            stops = -math.log2(max(float(value), 1e-9))
            if abs(stops) < 0.5 * 10 ** (-decimals):
                stops = 0.0  # 避免显示 -0.00
            return f'{stops:+.{decimals}f}'
        if abs(float(value)) < 0.5 * 10 ** (-decimals):
            value = 0.0  # 避免显示 -0
        text = f'{value:.{decimals}f}'
        if decimals > 0 and '.' in text:
            text = text.rstrip('0').rstrip('.')
        if value > 0 and self._spec.lo < 0:
            text = f'+{text}'
        return text

    def _pull_initial(self) -> None:
        try:
            value = float(self._source.value)
        except (TypeError, ValueError):
            value = self._spec.lo
        # 编辑器未同步/越界时钳进量程，避免档位读数发散
        value = max(self._spec.lo, min(self._spec.hi, value))
        self._apply(value)

    def _apply(self, value: float) -> None:
        self._syncing = True
        try:
            self.slider.blockSignals(True)
            self.slider.setValue(self._to_position(value))
            self.slider.blockSignals(False)
            self._value.setText(self._format(value))
            self._paint_state(value)
        finally:
            self._syncing = False

    def _paint_state(self, value: float) -> None:
        dirty = abs(float(value) - self._baseline) > 1e-6
        self._value.setProperty('dirty', 'true' if dirty else 'false')
        self._value.style().unpolish(self._value)
        self._value.style().polish(self._value)

        self.slider.setProperty('dirty', 'true' if dirty else 'false')
        self.slider.style().unpolish(self.slider)
        self.slider.style().polish(self.slider)

    def _write(self, value: float) -> None:
        try:
            self._source.value = float(value)
        except (TypeError, ValueError, AttributeError):
            return

    def _on_slider(self, position: int) -> None:
        if self._syncing:
            return
        value = self._from_position(position)
        self._value.setText(self._format(value))
        self._paint_state(value)
        self._write(value)

    def _commit(self) -> None:
        if self._on_change is not None:
            self._on_change()

    def _reset(self, event) -> None:  # noqa: N802 - Qt API name
        self._apply(self._baseline)
        self._write(self._baseline)
        self._commit()
        motion.fade_in(self._value, duration=140, start=0.3)
        event.accept()

    def sync_from_source(self, *_args) -> None:
        if self._syncing:
            return
        try:
            value = float(self._source.value)
        except (TypeError, ValueError):
            return
        if self._spec.enforce_range and (value < self._spec.lo or value > self._spec.hi):
            value = max(self._spec.lo, min(self._spec.hi, value))
            self._syncing = True
            try:
                self._write(value)
            finally:
                self._syncing = False
        # 外部改值（换胶片相纸预设、重置、打开照片）即新基准，
        # 否则脏参数高亮会一直指向构造时的旧基准。
        self._baseline = value
        self._apply(value)

    def is_dirty(self) -> bool:
        try:
            return abs(float(self._source.value) - self._baseline) > 1e-6
        except (TypeError, ValueError):
            return False


class NumberRow(_Row):
    """无界数值行：精确输入框，不强行套一个会偷偷收窄范围的滑块。"""

    def __init__(self, spec: Number, source, on_change, *, parent=None):
        super().__init__(spec.label, spec.leaf, height=ROW_HEIGHT, parent=parent)
        self._spec = spec
        self._source = source
        self._on_change = on_change
        self._syncing = False
        self._integer = _is_integer_value(getattr(source, 'value', 0.0))
        try:
            self._baseline = float(source.value)
        except (TypeError, ValueError):
            self._baseline = 0.0
        self._value.hide()
        self.spin: QtWidgets.QAbstractSpinBox = self._build_spin(source, integer=self._integer)
        self.spin.setObjectName('deckNumber')
        self.spin.setFixedHeight(22)
        self.spin.setMaximumWidth(96)
        self.spin.setKeyboardTracking(False)
        self.spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.spin.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._top.addWidget(self.spin, 0, Qt.AlignVCenter)
        self.spin.valueChanged.connect(self._on_spin)
        signal = _refresh_signal(source)
        if signal is not None:
            signal.connect(self.sync_from_source)
        self.sync_from_source()

    @staticmethod
    def _build_spin(source, *, integer: bool) -> QtWidgets.QAbstractSpinBox:
        spin_source = getattr(source, '_spin', source)
        if integer:
            spin = QtWidgets.QSpinBox()
            if hasattr(spin_source, 'minimum') and hasattr(spin_source, 'maximum'):
                spin.setRange(int(spin_source.minimum()), int(spin_source.maximum()))
            if hasattr(spin_source, 'singleStep'):
                spin.setSingleStep(max(1, int(spin_source.singleStep())))
        else:
            spin = QtWidgets.QDoubleSpinBox()
            decimals = int(getattr(spin_source, 'decimals', lambda: 2)()) if hasattr(spin_source, 'decimals') else 2
            spin.setDecimals(max(0, min(6, decimals)))
            if hasattr(spin_source, 'minimum') and hasattr(spin_source, 'maximum'):
                spin.setRange(float(spin_source.minimum()), float(spin_source.maximum()))
            if hasattr(spin_source, 'singleStep'):
                spin.setSingleStep(max(float(spin_source.singleStep()), 1e-6))
        return spin

    def _on_spin(self, value) -> None:
        if self._syncing:
            return
        self._write(value)
        self._paint_state(float(value))
        if self._on_change is not None:
            self._on_change()

    def _write(self, value) -> None:
        try:
            self._source.value = int(round(float(value))) if self._integer else float(value)
        except (TypeError, ValueError, AttributeError):
            return

    def sync_from_source(self, *_args) -> None:
        if self._syncing:
            return
        try:
            value = float(self._source.value)
        except (TypeError, ValueError):
            return
        self._baseline = value
        self._syncing = True
        try:
            self.spin.blockSignals(True)
            self.spin.setValue(int(round(value)) if self._integer else value)
            self.spin.blockSignals(False)
        finally:
            self._syncing = False
        self._paint_state(value)

    def _paint_state(self, value: float) -> None:
        dirty = abs(float(value) - self._baseline) > 1e-6
        self.spin.setProperty('dirty', 'true' if dirty else 'false')
        self.spin.style().unpolish(self.spin)
        self.spin.style().polish(self.spin)

    def is_dirty(self) -> bool:
        try:
            return abs(float(self._source.value) - self._baseline) > 1e-6
        except (TypeError, ValueError):
            return False


class VecRow(_Row):
    """二元/三元向量行：每个分量一个小输入框，绑定到源编辑器的元组值。"""

    def __init__(self, spec: Vec, source, on_change, *, parent=None):
        super().__init__(spec.label, spec.leaf, height=52, parent=parent)
        self._spec = spec
        self._source = source
        self._on_change = on_change
        self._syncing = False
        try:
            self._baseline = tuple(float(value) for value in source.value)
        except (TypeError, ValueError):
            self._baseline = ()
        self._value.hide()
        self._component_editors = list(getattr(source, 'editors', ()) or ())
        self._component_spins: list[QtWidgets.QAbstractSpinBox] = []
        self._component_integers: list[bool] = []
        self._spins_layout = QtWidgets.QHBoxLayout()
        self._spins_layout.setContentsMargins(0, 0, 0, 0)
        self._spins_layout.setSpacing(4)
        self._layout.addLayout(self._spins_layout)
        self._build_components()
        signal = _refresh_signal(source)
        if signal is not None:
            signal.connect(self.sync_from_source)
        self.sync_from_source()

    def _build_components(self) -> None:
        count = len(self._baseline) or len(self._component_editors)
        if count <= 0:
            return
        for index in range(count):
            component = self._component_editors[index] if index < len(self._component_editors) else None
            integer = _is_integer_value(getattr(component, 'value', 0.0)) if component is not None else False
            if component is not None:
                spin = NumberRow._build_spin(component, integer=integer)
            else:
                spin = QtWidgets.QDoubleSpinBox()
                spin.setRange(-1_000_000.0, 1_000_000.0)
                spin.setDecimals(3)
            spin.setObjectName('deckNumber')
            spin.setFixedHeight(20)
            spin.setMinimumWidth(0)
            spin.setMaximumWidth(140)
            spin.setKeyboardTracking(False)
            spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            spin.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            spin.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            spin.valueChanged.connect(self._on_component)
            self._spins_layout.addWidget(spin, 1)
            self._component_spins.append(spin)
            self._component_integers.append(integer)

    def _on_component(self, *_args) -> None:
        if self._syncing:
            return
        values = tuple(
            int(round(spin.value())) if integer else float(spin.value())
            for spin, integer in zip(self._component_spins, self._component_integers)
        )
        try:
            self._source.value = values
        except (TypeError, ValueError, AttributeError):
            return
        self._paint_state(values)
        if self._on_change is not None:
            self._on_change()

    def sync_from_source(self, *_args) -> None:
        if self._syncing:
            return
        try:
            values = tuple(self._source.value)
        except (TypeError, ValueError):
            return
        self._baseline = tuple(float(value) for value in values)
        self._syncing = True
        try:
            for spin, value in zip(self._component_spins, values):
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
        finally:
            self._syncing = False
        self._paint_state(values)

    def _paint_state(self, values) -> None:
        for index, (spin, value) in enumerate(zip(self._component_spins, values)):
            baseline = self._baseline[index] if index < len(self._baseline) else float(value)
            dirty = abs(float(value) - float(baseline)) > 1e-6
            spin.setProperty('dirty', 'true' if dirty else 'false')
            spin.style().unpolish(spin)
            spin.style().polish(spin)

    def is_dirty(self) -> bool:
        try:
            values = tuple(float(value) for value in self._source.value)
        except (TypeError, ValueError):
            return False
        if len(values) != len(self._baseline):
            return True
        return any(abs(value - baseline) > 1e-6 for value, baseline in zip(values, self._baseline))


def _is_integer_value(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return False
    try:
        return int(value) == value and not isinstance(value, float)
    except (TypeError, ValueError):
        return False


class ToggleSwitch(QtWidgets.QAbstractButton):
    WIDTH = 32
    HEIGHT = 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self._position = 0.0
        self._follow = motion.FollowValue(self, rate=26.0)
        self._follow.valueChanged.connect(self._on_follow)
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        self._follow.move_to(1.0 if checked else 0.0)

    def _on_follow(self, value: float) -> None:
        self._position = value
        self.update()

    def set_value(self, checked: bool) -> None:
        self.blockSignals(True)
        self.setChecked(bool(checked))
        self.blockSignals(False)
        self._position = 1.0 if checked else 0.0
        self._follow.snap_to(self._position)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            if not self.isEnabled():
                painter.setOpacity(0.45)
            rect = QtCore.QRectF(0.5, 0.5, self.WIDTH - 1, self.HEIGHT - 1)
            off = QtGui.QColor('#3D3D3B')
            on = QtGui.QColor(ACCENT)
            color = QtGui.QColor(
                round(off.red() + (on.red() - off.red()) * self._position),
                round(off.green() + (on.green() - off.green()) * self._position),
                round(off.blue() + (on.blue() - off.blue()) * self._position),
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

            knob = self.HEIGHT - 4
            travel = self.WIDTH - knob - 4
            x = 2 + travel * self._position
            painter.setBrush(QtGui.QColor('#FFFFFF'))
            painter.drawEllipse(QtCore.QRectF(x, 2, knob, knob))
        finally:
            painter.end()


class ToggleRow(_Row):
    def __init__(self, spec: Toggle, source, on_change, *, parent=None):
        super().__init__(spec.label, spec.leaf, height=TOGGLE_HEIGHT, parent=parent)
        self._spec = spec
        self._source = source
        self._on_change = on_change
        self.switch = ToggleSwitch()
        self.switch.setToolTip(self.toolTip())
        self._top.addWidget(self.switch, 0, Qt.AlignVCenter)
        self.switch.toggled.connect(self._on_toggled)
        signal = _refresh_signal(source)
        if signal is not None:
            signal.connect(self.sync_from_source)
        self.sync_from_source()

    def _on_toggled(self, checked: bool) -> None:
        try:
            self._source.value = bool(checked)
        except (TypeError, ValueError, AttributeError):
            return
        if self._on_change is not None:
            self._on_change()

    def sync_from_source(self, *_args) -> None:
        try:
            value = bool(self._source.value)
        except (TypeError, ValueError):
            return
        if self.switch.isChecked() != value:
            self.switch.set_value(value)

    def is_dirty(self) -> bool:
        return False


class EnumRow(_Row):
    def __init__(
        self,
        spec: Choice,
        source,
        on_change,
        *,
        on_activate: Callable[[str], None] | None = None,
        parent=None,
    ):
        super().__init__(spec.label, spec.leaf, height=ENUM_HEIGHT, parent=parent)
        self._spec = spec
        self._source = source
        self._on_change = on_change
        self._on_activate = on_activate

        self.combo = QtWidgets.QComboBox()
        self.combo.setObjectName('deckCombo')
        self.combo.setCursor(Qt.PointingHandCursor)
        self.combo.setToolTip(self.toolTip())
        self.combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToContents)
        self.combo.setMinimumContentsLength(6)
        self.combo.setMaximumWidth(198)
        self.combo.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Fixed)
        values = [source.itemText(index) for index in range(source.count())]
        translate = getattr(source, 'display_text_for_value', None)
        for raw in values:
            shown = translate(str(raw)) if callable(translate) else str(raw)
            self.combo.addItem(str(shown), str(raw))
        self.combo.currentTextChanged.connect(self._update_combo_tooltip)
        self._update_combo_tooltip(self.combo.currentText())

        self._chevron = QtWidgets.QLabel(self.combo)
        self._chevron.setPixmap(shell_icons.icon('chevron_down', TEXT_3, 8).pixmap(8, 8))
        self._chevron.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.combo.installEventFilter(self)

        self._top.addWidget(self.combo, 0, Qt.AlignVCenter)
        self.combo.currentIndexChanged.connect(self._on_index)
        if self._on_activate is not None:
            self.combo.textActivated.connect(self._on_text_activated)
        self.sync_from_source()

    def _update_combo_tooltip(self, text: str) -> None:
        tip = self.toolTip()
        self.combo.setToolTip(f'{tip}\n当前：{text}' if tip else text)

    def _on_text_activated(self, text: str) -> None:
        if self._on_activate is None:
            return
        raw = self.combo.currentData()
        self._on_activate(str(raw) if raw is not None else str(text))

    def eventFilter(self, obj, event):  # noqa: N802 - Qt API name
        if obj is self.combo and event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Show):
            self._place_chevron()
        return super().eventFilter(obj, event)

    def _place_chevron(self) -> None:
        self._chevron.move(max(0, self.combo.width() - 10), max(0, (self.combo.height() - 8) // 2))
        self._chevron.raise_()

    def _on_index(self, index: int) -> None:
        text = self.combo.itemData(index) or self.combo.itemText(index)
        try:
            self._source.value = text
        except (TypeError, ValueError, AttributeError):
            return
        if self._on_change is not None:
            self._on_change()

    def sync_from_source(self, *_args) -> None:
        try:
            current = str(self._source.value)
        except (TypeError, ValueError):
            return
        for index in range(self.combo.count()):
            if str(self.combo.itemData(index)) == current:
                if index != self.combo.currentIndex():
                    self.combo.blockSignals(True)
                    self.combo.setCurrentIndex(index)
                    self.combo.blockSignals(False)
                return

    def is_dirty(self) -> bool:
        return False


class GroupLabel(QtWidgets.QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName('deckGroup')
        self.setFixedHeight(GROUP_HEIGHT)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)


class HistogramView(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self._histograms: list | None = None

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
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            rect = QtCore.QRectF(0, 2, self.width(), self.height() - 4)
            if not self._histograms:
                painter.setPen(QtGui.QColor(TEXT_4))
                painter.drawText(rect, Qt.AlignCenter, '等待预览')
                return
            maximum = max(float(hist.max(initial=0.0)) for hist in self._histograms) or 1.0
            for histogram, color in zip(self._histograms, ('#B46B5C', '#8A9B78', '#7C8DA0')):
                path = QtGui.QPainterPath()
                count = len(histogram)
                path.moveTo(rect.left(), rect.bottom())
                for index, value in enumerate(histogram):
                    x = rect.left() + rect.width() * index / max(count - 1, 1)
                    normalized = (float(value) / maximum) ** 0.55
                    path.lineTo(x, rect.bottom() - normalized * rect.height())
                path.lineTo(rect.right(), rect.bottom())
                path.closeSubpath()
                fill = QtGui.QColor(color)
                fill.setAlpha(46)
                painter.fillPath(path, fill)
                painter.setPen(QtGui.QPen(QtGui.QColor(color), 0.9))
                painter.drawPath(path)
        finally:
            painter.end()


class Tabs(QtWidgets.QWidget):
    """两种分段：segmented 用于模式切换，underline 用于页面切换。"""

    changed = QtCore.Signal(int)
    HEIGHT = 32

    def __init__(self, labels: list[str], *, variant: str = 'segmented', parent=None):
        super().__init__(parent)
        self._variant = variant
        self._height = 30 if variant == 'underline' else 32
        self.setFixedHeight(self._height)
        self._labels = labels
        self._index = 0
        self._position = 0.0
        self._follow = motion.FollowValue(self, rate=22.0)
        self._follow.valueChanged.connect(self._on_follow)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self._font = platform_default_font()
        self._font.setPixelSize(12)
        self._font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, 0.2)
        self._font_selected = QtGui.QFont(self._font)
        self._font_selected.setWeight(QtGui.QFont.Medium)

    def set_current(self, index: int) -> None:
        if index == self._index:
            return
        self._index = max(0, min(len(self._labels) - 1, index))
        self._follow.move_to(float(self._index))
        self.changed.emit(self._index)
        self.update()

    def _on_follow(self, value: float) -> None:
        self._position = value
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() != Qt.LeftButton:
            return
        track = self.rect().adjusted(3, 3, -3, -3)
        width = track.width() / max(1, len(self._labels))
        index = int((event.position().x() - track.left()) // max(1.0, width))
        self.set_current(max(0, min(len(self._labels) - 1, index)))

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            if self._variant == 'underline':
                self._paint_underline(painter)
            else:
                self._paint_segmented(painter)
        finally:
            painter.end()

    def _paint_segmented(self, painter: QtGui.QPainter) -> None:
        track = QtCore.QRectF(0.5, 0.5, self.width() - 1, self._height - 1)
        painter.setPen(QtGui.QPen(QtGui.QColor(HAIRLINE), 1))
        painter.setBrush(QtGui.QColor(SURFACE_0))
        painter.drawRoundedRect(track, 9, 9)

        inner = track.adjusted(3, 3, -3, -3)
        count = max(1, len(self._labels))
        seg = inner.width() / count
        pill = QtCore.QRectF(inner.left() + seg * self._position, inner.top(), seg, inner.height())
        painter.setPen(QtGui.QPen(QtGui.QColor(HAIRLINE_STRONG), 1))
        painter.setBrush(QtGui.QColor(SURFACE_3))
        painter.drawRoundedRect(pill, 7, 7)

        for index, label in enumerate(self._labels):
            rect = QtCore.QRectF(inner.left() + seg * index, inner.top(), seg, inner.height())
            active = index == self._index
            painter.setFont(self._font_selected if active else self._font)
            painter.setPen(QtGui.QColor(TEXT_1 if active else TEXT_3))
            painter.drawText(rect, Qt.AlignCenter, label)

    def _paint_underline(self, painter: QtGui.QPainter) -> None:
        count = max(1, len(self._labels))
        seg = self.width() / count
        for index, label in enumerate(self._labels):
            rect = QtCore.QRectF(seg * index, 0, seg, self._height - 4)
            active = index == self._index
            painter.setFont(self._font_selected if active else self._font)
            painter.setPen(QtGui.QColor(TEXT_1 if active else TEXT_3))
            painter.drawText(rect, Qt.AlignCenter, label)

        metrics = QtGui.QFontMetrics(self._font_selected)
        label = self._labels[self._index]
        width = min(metrics.horizontalAdvance(label) + 8, seg - 12)
        center = (self._position + 0.5) * seg
        painter.setPen(QtGui.QPen(QtGui.QColor(ACCENT), 2))
        y = self._height - 2.0
        painter.drawLine(QtCore.QPointF(center - width / 2, y), QtCore.QPointF(center + width / 2, y))


class ParameterDeck(QtWidgets.QWidget):
    reset_requested = QtCore.Signal()
    profile_changed = QtCore.Signal(str, str)
    quick_changed = QtCore.Signal()

    def __init__(self, widgets, controller, *, parent=None):
        super().__init__(parent)
        self.setObjectName('paramDeck')
        self.setMinimumWidth(300)
        self._widgets = widgets
        self._controller = controller
        self._rows: dict[tuple[str, str], _Row] = {}
        self._used_keys: set[tuple[str, str]] = set()
        self._raw_action_button: QtWidgets.QPushButton | None = None
        self._condition_pairs: list[tuple[ToggleRow, list[_Row]]] = []
        self._mode = 'pro'
        self._quick_engine = QuickEngine()
        self._quick_panel: QuickPanel | None = None
        self._build()

    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self._build_body(), 1)
        self.setStyleSheet(DECK_STYLE)

    def _build_header(self) -> QtWidgets.QWidget:
        header = QtWidgets.QWidget()
        header.setObjectName('deckHeader')
        header.setFixedHeight(48)
        layout = QtWidgets.QHBoxLayout(header)
        layout.setContentsMargins(14, 0, 12, 0)
        layout.setSpacing(8)

        self._mode_tabs = Tabs(['快速', '专业'], variant='segmented')
        self._mode_tabs.setFixedWidth(176)

        self._badge = QtWidgets.QLabel('')
        self._badge.setObjectName('deckBadge')
        self._badge.setVisible(False)

        reset = QtWidgets.QPushButton('重置')
        reset.setObjectName('deckReset')
        reset.setCursor(Qt.PointingHandCursor)
        reset.setFixedHeight(26)
        reset.setToolTip('把这张照片的全部参数恢复为出厂值')
        reset.clicked.connect(self.reset_requested.emit)

        layout.addWidget(self._mode_tabs, 0, Qt.AlignVCenter)
        layout.addStretch(1)
        layout.addWidget(self._badge, 0, Qt.AlignVCenter)
        layout.addWidget(reset, 0, Qt.AlignVCenter)
        return header

    def _build_body(self) -> QtWidgets.QWidget:
        body = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(body)
        layout.setContentsMargins(PANEL_MARGIN, 10, PANEL_MARGIN, 10)
        layout.setSpacing(10)

        layout.addWidget(self._build_histogram())

        self._quick_page = self._build_quick_page()

        self._tabs = Tabs([name for name, _ in PAGES] + [PRO_PAGE_LABEL], variant='underline')
        self._tabs.changed.connect(self._show_page)
        self._stack = QtWidgets.QStackedWidget()
        for _name, spec in PAGES:
            self._stack.addWidget(self._build_page(spec))
        self._stack.addWidget(self._build_page(self._pro_entries()))

        self._pro_page = QtWidgets.QWidget()
        pro_layout = QtWidgets.QVBoxLayout(self._pro_page)
        pro_layout.setContentsMargins(0, 0, 0, 0)
        pro_layout.setSpacing(8)
        pro_layout.addWidget(self._tabs)
        pro_layout.addWidget(self._stack, 1)

        self._mode_stack = QtWidgets.QStackedWidget()
        self._mode_stack.addWidget(self._quick_page)
        self._mode_stack.addWidget(self._pro_page)
        layout.addWidget(self._mode_stack, 1)

        self._wire_conditions()
        self._update_raw_availability()
        self._mode_tabs.changed.connect(self._show_mode)
        self._mode_tabs.set_current(1)
        return body

    def _build_quick_page(self) -> QtWidgets.QWidget:
        self._quick_panel = QuickPanel()
        self._quick_panel.axis_changed.connect(self._on_quick_axis)
        self._quick_panel.reset_all_requested.connect(self._reset_quick)
        return self._quick_panel

    def _build_histogram(self) -> QtWidgets.QWidget:
        card = QtWidgets.QFrame()
        card.setObjectName('deckHistogram')
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        head = QtWidgets.QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        title = QtWidgets.QLabel('直方图')
        title.setObjectName('deckHistogramTitle')
        meta = QtWidgets.QLabel('亮度 / RGB')
        meta.setObjectName('deckHistogramMeta')
        head.addWidget(title, 0, Qt.AlignVCenter)
        head.addStretch(1)
        head.addWidget(meta, 0, Qt.AlignVCenter)

        self.histogram = HistogramView()
        layout.addLayout(head)
        layout.addWidget(self.histogram)
        return card

    def _build_page(self, spec) -> QtWidgets.QWidget:
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

        on_change = self._on_change
        for entry in spec:
            if isinstance(entry, Group):
                if inner.count() > 0:
                    inner.addSpacing(6)
                inner.addWidget(GroupLabel(entry.text))
                continue
            if isinstance(entry, Action):
                button = QtWidgets.QPushButton(entry.text)
                button.setObjectName('deckAction')
                button.setCursor(Qt.PointingHandCursor)
                button.clicked.connect(
                    lambda _checked=False, action=entry.action: self._run_action(action)
                )
                if entry.action == 'reprocess_raw':
                    self._raw_action_button = button
                inner.addWidget(button)
                continue
            source = _editor(self._widgets, entry.section, entry.leaf)
            if source is None:
                continue
            row: _Row
            if isinstance(entry, Slider):
                row = SliderRow(entry, source, on_change)
            elif isinstance(entry, Number):
                row = NumberRow(entry, source, on_change)
            elif isinstance(entry, Vec):
                row = VecRow(entry, source, on_change)
            elif isinstance(entry, Toggle):
                row = ToggleRow(entry, source, on_change)
            else:
                on_activate = None
                if entry.leaf in {'film_stock', 'print_paper'}:
                    on_activate = lambda value, leaf=entry.leaf: self._on_profile_change(leaf, value)
                row = EnumRow(entry, source, on_change, on_activate=on_activate)
            key = (entry.section, entry.leaf)
            self._rows[key] = row
            self._used_keys.add(key)
            inner.addWidget(row)

        inner.addStretch(1)
        outer.addWidget(card)
        scroll.setWidget(content)
        return scroll

    def _pro_entries(self) -> list:
        entries: list = []
        for section in _PRO_SECTION_ORDER:
            section_entries: list = []
            for spec in _PRO_SECTION_SPECS.get(section, ()):
                key = (section, spec.leaf)
                if key in self._used_keys:
                    continue
                if section == 'display' and spec.leaf in _DISPLAY_SKIPPED:
                    continue
                source = _editor(self._widgets, section, spec.leaf)
                if source is None:
                    continue
                label = spec.label or technical_label_for(spec.leaf) or spec.leaf.replace('_', ' ')
                type_name = type(source).__name__
                if type_name == 'BoolEditor':
                    entry = Toggle(section, spec.leaf, label)
                elif type_name in {'EnumEditor', 'ProfileEnumEditor'}:
                    entry = Choice(section, spec.leaf, label)
                elif type_name in {'FloatTupleEditor', 'IntTupleEditor'}:
                    entry = Vec(section, spec.leaf, label)
                elif type_name == 'IntEditor':
                    entry = Number(section, spec.leaf, label)
                elif type_name in {'FloatEditor', 'SliderRowEditor'}:
                    if spec.min is not None and spec.max is not None and float(spec.max) > float(spec.min):
                        span = float(spec.max) - float(spec.min)
                        step = float(spec.step) if spec.step else span / 200.0
                        decimals = spec.decimals if spec.decimals is not None else 2
                        entry = Slider(
                            section,
                            spec.leaf,
                            label,
                            float(spec.min),
                            float(spec.max),
                            step,
                            int(decimals),
                        )
                    else:
                        entry = Number(section, spec.leaf, label)
                else:
                    continue
                section_entries.append(entry)
            if section_entries:
                entries.append(Group(_PRO_SECTION_TITLES.get(section, section)))
                entries.extend(section_entries)
        return entries

    def _on_change(self) -> None:
        if self._mode == 'quick':
            self._refresh_quick_status()
        self._update_badge()
        request = getattr(self._controller, 'request_auto_preview', None)
        if callable(request):
            request()

    def _on_quick_axis(self, name: str, value: float) -> None:
        state = collect_gui_state(widgets=self._widgets)
        if self._quick_engine.profile_changed(state):
            state = self._quick_engine.rebase(state)
        state = self._quick_engine.set_axis(state, name, value)
        apply_gui_state(state, widgets=self._widgets)
        self._quick_panel.set_intent(name, value)
        self._sync_pro_rows()
        self._apply_conditions()
        self._refresh_quick_availability(state)
        self._on_change()
        self.quick_changed.emit()

    def _reset_quick(self) -> None:
        state = collect_gui_state(widgets=self._widgets)
        if self._quick_engine.profile_changed(state):
            self._quick_engine.capture(state)
        state = self._quick_engine.restore_baseline(state)
        apply_gui_state(state, widgets=self._widgets)
        self._quick_panel.set_intents(self._quick_engine.intent)
        self._sync_pro_rows()
        self._apply_conditions()
        self._refresh_quick_availability(state)
        self._on_change()
        self.quick_changed.emit()

    def _refresh_quick_status(self, state=None) -> None:
        if self._quick_panel is None:
            return
        if state is None:
            # 还没建立基线、且不在快速页时，没必要为专业编辑去收集整份状态。
            if self._quick_engine.profile is None and self._mode != 'quick':
                return
            state = collect_gui_state(widgets=self._widgets)
        self._quick_panel.set_statuses(self._quick_engine.statuses(state))
        self._quick_panel.set_native_details(
            {name: self._quick_engine.native_summary(state, name) for name in AXES}
        )

    def set_quick_state(self, raw) -> None:
        state = collect_gui_state(widgets=self._widgets)
        self._quick_engine.load(raw, state)
        if self._quick_panel is not None:
            self._quick_panel.set_intents(self._quick_engine.intent)
        self._refresh_quick_availability(state)
        self._refresh_quick_status(state)
        self._update_badge()

    def quick_state_dict(self) -> dict:
        return self._quick_engine.to_dict()

    def reset_quick_state(self) -> None:
        state = collect_gui_state(widgets=self._widgets)
        self._quick_engine.capture(state, clear_intent=True)
        if self._quick_panel is not None:
            self._quick_panel.set_intents(self._quick_engine.intent)
        self._refresh_quick_availability(state)
        self._refresh_quick_status(state)
        self._update_badge()

    def _sync_pro_rows(self) -> None:
        for row in self._rows.values():
            row.sync_from_source()

    def _show_mode(self, index: int) -> None:
        mode = 'quick' if index == 0 else 'pro'
        self._mode = mode
        self._mode_stack.setCurrentIndex(index)
        self._refresh_quick_status()
        self._refresh_quick_availability()
        self._update_badge()
        page = self._mode_stack.currentWidget()
        if page is not None:
            motion.fade_in(page, duration=motion.DURATION_QUICK)

    def _run_action(self, action: str) -> None:
        if action != 'reprocess_raw':
            return
        from spektrafilm_gui.library_store import is_raw_image

        load_raw = getattr(self._widgets, 'load_raw', None)
        file_path = getattr(load_raw, 'file_path', None)
        path = file_path.text().strip() if hasattr(file_path, 'text') else ''
        if not path or not is_raw_image(path):
            return
        load = getattr(self._controller, 'load_raw_image', None)
        if callable(load):
            load(path)

    def _on_profile_change(self, leaf: str, raw: str) -> None:
        apply = getattr(self._controller, 'apply_profile_defaults', None)
        if callable(apply):
            apply(raw)
        self.refresh()
        self.profile_changed.emit(leaf, str(raw))
        request = getattr(self._controller, 'request_auto_preview', None)
        if callable(request):
            request()

    def _wire_conditions(self) -> None:
        def section_rows(section: str, *, exclude: str = '') -> list[_Row]:
            return [
                row
                for (row_section, leaf), row in self._rows.items()
                if row_section == section and leaf != exclude
            ]

        pairs: list[tuple[tuple[str, str], list[_Row]]] = [
            (('grain', 'active'), section_rows('grain', exclude='active')),
            (('halation', 'active'), section_rows('halation', exclude='active')),
            (('couplers', 'active'), section_rows('couplers', exclude='active')),
            (('chemistry', 'active'), section_rows('chemistry', exclude='active')),
            (('glare', 'active'), section_rows('glare', exclude='active')),
            (('camera_diffusion', 'active'), section_rows('camera_diffusion', exclude='active')),
            (('enlarger_diffusion', 'active'), section_rows('enlarger_diffusion', exclude='active')),
            (('scanner', 'white_correction'), [self._rows.get(('scanner', 'white_level'))]),
            (('scanner', 'black_correction'), [self._rows.get(('scanner', 'black_level'))]),
            (('camera', 'auto_exposure'), [
                self._rows.get(('camera', 'auto_exposure_method')),
                self._rows.get(('camera', 'exposure_compensation_ev')),
            ]),
            (('input_image', 'crop'), [
                self._rows.get(('input_image', 'crop_center')),
                self._rows.get(('input_image', 'crop_size')),
            ]),
        ]
        for key, dependents in pairs:
            toggle_row = self._rows.get(key)
            if not isinstance(toggle_row, ToggleRow):
                continue
            available = [row for row in dependents if row is not None]
            if available:
                self._condition_pairs.append((toggle_row, available))
                self._link_enabled(toggle_row, available)

    def _apply_conditions(self) -> None:
        for toggle_row, dependents in self._condition_pairs:
            enabled = toggle_row.switch.isChecked()
            for row in dependents:
                row.setEnabled(enabled)

    @staticmethod
    def _link_enabled(toggle_row: ToggleRow, dependents: list[_Row]) -> None:
        def apply(enabled: bool) -> None:
            for row in dependents:
                row.setEnabled(bool(enabled))

        toggle_row.switch.toggled.connect(apply)
        apply(toggle_row.switch.isChecked())

    def _update_badge(self) -> None:
        if self._mode == 'quick':
            count = self._quick_engine.dirty_count()
        else:
            count = sum(1 for row in self._rows.values() if row.is_dirty())
        self._badge.setText(str(count) if count else '')
        self._badge.setVisible(bool(count))

    # ── 对外 ────────────────────────────────────────────────
    def _show_page(self, index: int) -> None:
        if index < 0 or index >= self._stack.count():
            return
        if self._stack.currentIndex() == index:
            return
        self._stack.setCurrentIndex(index)
        page = self._stack.currentWidget()
        motion.fade_in(page, duration=motion.DURATION_QUICK)

    def show_page(self, name: str) -> None:
        labels = [title for title, _spec in PAGES] + [PRO_PAGE_LABEL]
        for index, title in enumerate(labels):
            if title == name:
                self._mode_tabs.set_current(1)
                self._mode_stack.setCurrentIndex(1)
                self._tabs.set_current(index)
                return

    def refresh(self) -> None:
        state = None
        if self._mode == 'quick' or self._quick_engine.profile is not None:
            state = collect_gui_state(widgets=self._widgets)
            if self._quick_engine.profile_changed(state):
                state = self._quick_engine.rebase(state)
                apply_gui_state(state, widgets=self._widgets)
                if self._quick_panel is not None:
                    self._quick_panel.set_intents(self._quick_engine.intent)
        self._sync_pro_rows()
        self._apply_conditions()
        self._refresh_quick_status(state)
        self._refresh_quick_availability(state)
        self._update_raw_availability()
        self._update_badge()

    def _refresh_quick_availability(self, state=None) -> None:
        if self._quick_panel is None:
            return
        if state is None:
            if self._quick_engine.profile is None and self._mode != 'quick':
                return
            state = collect_gui_state(widgets=self._widgets)
        scan_film = bool(getattr(state.simulation.io, 'scan_film', False))
        disabled = {
            name: DISABLED_REASON for name in disabled_axes(scan_film=scan_film)
        }
        self._quick_panel.set_availability(disabled)

    def _update_raw_availability(self) -> None:
        from spektrafilm_gui.library_store import is_raw_image

        load_raw = getattr(self._widgets, 'load_raw', None)
        file_path = getattr(load_raw, 'file_path', None)
        path = file_path.text().strip() if hasattr(file_path, 'text') else ''
        available = bool(path) and is_raw_image(path)
        for leaf in ('white_balance', 'temperature', 'tint', 'lens_correction'):
            row = self._rows.get(('load_raw', leaf))
            if row is not None:
                row.setEnabled(available)
        if self._raw_action_button is not None:
            self._raw_action_button.setEnabled(available)

    def set_histogram(self, array) -> None:
        self.histogram.set_array(array)

    def row(self, leaf: str, section: str | None = None):
        if section is not None:
            return self._rows.get((section, leaf))
        for (_section, row_leaf), row in self._rows.items():
            if row_leaf == leaf:
                return row
        return None
