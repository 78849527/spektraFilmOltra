from __future__ import annotations

from spektrafilm_gui.theme_oflim import (
    ACCENT,
    ACCENT_DIM,
    ACCENT_ON,
    ACCENT_STRONG,
    HAIRLINE,
    HAIRLINE_STRONG,
    R_MEDIUM,
    R_CONTROL,
    SURFACE_0,
    SURFACE_1,
    SURFACE_2,
    SURFACE_3,
    TEXT_1,
    TEXT_2,
    TEXT_3,
    rgba,
)
from spektrafilm_gui.theme_palette import (
    BASE_BG,
    BUTTON_ACCENT_BG,
    BUTTON_ACCENT_BG_HOVER,
    BUTTON_ACCENT_BG_PRESSED,
    CHECKED_BG,
    CONTROL_BG,
    CONTROL_BG_HOVER,
    CONTROL_BG_PRESSED,
    CONTROL_MENU_BG,
    CONTROL_SELECTION_BG,
    DISABLED_BG,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_SEMIBOLD,
    HEADER_BG,
    PANEL_BG,
    PANEL_BG_ACTIVE,
    SCROLLBAR_HANDLE_BG,
    SIZE_BUTTON_MIN_HEIGHT,
    SIZE_BUTTON_PADDING,
    SIZE_CHECKBOX_INDICATOR,
    SIZE_CHECKBOX_SPACING,
    SIZE_COMBO_DROPDOWN_WIDTH,
    SIZE_COMPACT_BUTTON_MIN_HEIGHT,
    SIZE_CONTROL_MIN_HEIGHT,
    SIZE_CONTROL_PADDING,
    SIZE_FOOTER_MIN_HEIGHT,
    SIZE_FORM_SPACING,
    SIZE_HEADER_PADDING,
    SIZE_SCROLLBAR_HANDLE_MIN,
    SIZE_SPIN_BUTTON_WIDTH,
    SIZE_TAB_MARGIN_RIGHT,
    SIZE_TAB_PADDING,
    SIZE_TAB_STRIP_OFFSET,
    SIZE_TOOLBUTTON_PADDING,
    SIZE_TOOLBUTTON_POPUP_PADDING_RIGHT,
    SPLITTER_BG,
    STATUS_BG,
    TAB_SELECTED_BG,
    TAB_TEXT_ACCENT,
    TEXT_ACCENT,
    TEXT_BRIGHT,
    TEXT_CONTROL,
    TEXT_HEADER,
    TEXT_HEADER_SECTION,
    TEXT_PRIMARY,
    TEXT_SELECTION_BG,
    TEXT_SOFT,
    TEXT_STATUS,
)


def join_style_sections(*sections: str) -> str:
    return '\n\n'.join(section.strip() for section in sections if section.strip())


WINDOW_STYLE = f"""
QMainWindow {{
    background: {BASE_BG};
    color: {TEXT_PRIMARY};
}}

QWidget#appCentral {{
    background: {BASE_BG};
}}

QWidget {{
    background: {BASE_BG};
    color: {TEXT_PRIMARY};
}}

QFrame#sidebarPanel {{
    background: {PANEL_BG};
    border: none;
    border-radius: 0;
}}

QFrame#viewerPanel {{
    background: {BASE_BG};
    border: none;
    border-radius: 0;
}}

QFrame {{
    background: {PANEL_BG};
    border: none;
}}

/* ── 顶栏：品牌条 ─────────────────────────────────────────── */
QWidget#appTopBar {{
    background: {SURFACE_0};
    border: none;
}}
QWidget#appTopBar QLabel {{
    background: transparent;
}}
QLabel#brandWordmark {{
    color: {TEXT_2};
    font-size: 10px;
    font-weight: {FONT_WEIGHT_SEMIBOLD};
    letter-spacing: 2px;
}}
QLabel#brandDot {{
    color: {ACCENT};
    font-size: 13px;
}}
QLabel#topBarStatus {{
    color: {TEXT_3};
    font-size: 10px;
    letter-spacing: 0.3px;
}}
QFrame#topBarDivider {{
    background: {HAIRLINE};
    border: none;
}}

/* ── 侧栏页眉：显影 ───────────────────────────────────────── */
QWidget#inspectorHeader {{
    background: {PANEL_BG};
    border: none;
}}
QLabel#inspectorEyebrow {{
    color: {TEXT_2};
    font-size: 10px;
    font-weight: {FONT_WEIGHT_SEMIBOLD};
    letter-spacing: 2px;
    background: transparent;
}}
QPushButton#headerResetButton {{
    background: transparent;
    color: {TEXT_3};
    border: 1px solid {HAIRLINE};
    border-radius: {R_CONTROL}px;
    font-size: 10px;
    padding: 2px 10px;
    min-height: 20px;
}}

QPushButton#headerResetButton:hover {{
    background: {SURFACE_3};
    color: {ACCENT};
    border: 1px solid {rgba(ACCENT, 0.4)};
}}

QLabel#inspectorCount {{
    color: {ACCENT};
    font-size: 9px;
    background: transparent;
}}
QLabel#sidebarEyebrow {{
    color: {TEXT_HEADER};
    font-weight: {FONT_WEIGHT_SEMIBOLD};
    letter-spacing: 0.08em;
}}
"""

TAB_STYLE = f"""
QTabWidget,
QTabWidget#controlsTabWidget {{
    background: {PANEL_BG};
}}

QTabWidget::pane,
QTabWidget#controlsTabWidget::pane {{
    border: none;
    border-radius: 0;
    background: {PANEL_BG};
    top: {SIZE_TAB_STRIP_OFFSET};
}}

QTabWidget::tab-bar {{
    alignment: left;
    left: 0px;
}}

QTabBar {{
    background: {SURFACE_1};
}}

QTabWidget#controlsTabWidget > QWidget {{
    background: {PANEL_BG};
}}

QTabWidget#controlsTabWidget QStackedWidget > QWidget {{
    background: {PANEL_BG};
}}

/* 胶囊式分段控件：选中项落在 surface2 上，仅用黄铜字与 24% 描边提示 */
QTabBar::tab {{
    background: transparent;
    color: {TEXT_3};
    border: 1px solid transparent;
    border-radius: {R_CONTROL}px;
    font-size: 10px;
    font-weight: {FONT_WEIGHT_SEMIBOLD};
    letter-spacing: 1px;
    padding: {SIZE_TAB_PADDING};
    margin-right: {SIZE_TAB_MARGIN_RIGHT};
    margin-top: 4px;
    margin-bottom: 4px;
    min-height: 18px;
}}

QTabBar::tab:selected {{
    background: {TAB_SELECTED_BG};
    color: {TAB_TEXT_ACCENT};
    border: 1px solid {rgba(ACCENT, 0.24)};
}}

QTabBar::tab:hover:!selected {{
    background: {rgba('#FFFFFF', 0.03)};
    color: {TEXT_2};
}}

/* ── 折叠区标题 ───────────────────────────────────────────── */
QToolButton[role="sectionToggle"] {{
    color: {ACCENT};
    background: transparent;
    border: none;
    padding: 0;
    min-height: 0;
    font-size: 9px;
    font-weight: {FONT_WEIGHT_SEMIBOLD};
    letter-spacing: 1.1px;
}}

QToolButton[role="sectionToggle"]:hover,
QToolButton[role="sectionToggle"]:pressed,
QToolButton[role="sectionToggle"]:checked {{
    background: transparent;
    border: none;
}}

QFrame#sectionCard {{
    background: {SURFACE_2};
    border: 1px solid {HAIRLINE};
    border-radius: {R_MEDIUM}px;
}}

/* 分页大卡：一张卡装下该阶段所有参数组（oflim 的 tabContent 形态） */
QFrame#tabCard {{
    background: {SURFACE_2};
    border: 1px solid {HAIRLINE};
    border-radius: {R_MEDIUM}px;
}}

/* 扁平组：不再重复画卡片，只留标题行与发丝分隔 */
QFrame#sectionFlat {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {HAIRLINE};
}}

QWidget#sectionCardBody {{
    background: transparent;
    border: none;
}}

QWidget#sectionContent {{
    background: transparent;
    border: none;
}}

QWidget#paramFieldHolder {{
    background: transparent;
    border: none;
}}

QWidget#sectionHeader {{
    background: transparent;
    border: none;
}}

/* ── 按钮 ─────────────────────────────────────────────────── */
QPushButton[role="accentAction"] {{
    background: {BUTTON_ACCENT_BG};
    color: {ACCENT_ON};
    font-weight: {FONT_WEIGHT_SEMIBOLD};
    border: none;
    border-radius: {R_CONTROL}px;
}}

QPushButton[role="accentAction"]:hover {{
    background: {BUTTON_ACCENT_BG_HOVER};
}}

QPushButton[role="accentAction"]:pressed {{
    background: {BUTTON_ACCENT_BG_PRESSED};
}}

/* 次级动作：与主操作同尺寸，但只靠表面色区分（oflim 的单一强调色原则） */
QPushButton[role="secondaryAction"] {{
    background: {SURFACE_2};
    color: {TEXT_2};
    font-weight: {FONT_WEIGHT_SEMIBOLD};
    border: 1px solid {HAIRLINE};
    border-radius: {R_CONTROL}px;
}}

QPushButton[role="secondaryAction"]:hover {{
    background: {SURFACE_3};
    border: 1px solid {HAIRLINE_STRONG};
    color: {TEXT_1};
}}

QPushButton[role="secondaryAction"]:pressed {{
    background: {SURFACE_1};
}}

QPushButton[role="secondaryAction"]:disabled {{
    background: {SURFACE_1};
    color: {rgba('#FFFFFF', 0.22)};
    border: 1px solid {HAIRLINE};
}}

QPushButton[role="accentAction"]:disabled {{
    background: {rgba(ACCENT, 0.22)};
    color: {rgba(ACCENT_ON, 0.6)};
}}

/* 画布页脚的小工具按钮 */
QPushButton#rotateCcwButton,
QPushButton#rotateCwButton,
QPushButton#zoom100Button,
QPushButton#zoom200Button,
QPushButton#zoom400Button,
QPushButton#homeViewButton {{
    background: transparent;
    color: {TEXT_3};
    border: 1px solid transparent;
    border-radius: {R_CONTROL}px;
    font-size: 9px;
    letter-spacing: 0.6px;
    padding: 0px 8px;
}}

QPushButton#rotateCcwButton:hover,
QPushButton#rotateCwButton:hover,
QPushButton#zoom100Button:hover,
QPushButton#zoom200Button:hover,
QPushButton#zoom400Button:hover,
QPushButton#homeViewButton:hover {{
    background: {SURFACE_2};
    color: {TEXT_1};
    border: 1px solid {HAIRLINE};
}}
"""

CONTROL_STYLE = f"""
QPushButton,
QToolButton,
QComboBox,
QLineEdit,
QAbstractSpinBox,
QTextEdit,
QPlainTextEdit,
QListView,
QTreeView,
QScrollArea,
QGroupBox,
QMenu {{
    background: {CONTROL_BG};
    color: {TEXT_CONTROL};
    border: 1px solid {HAIRLINE};
    border-radius: {R_CONTROL}px;
    outline: none;
}}

QPushButton,
QToolButton,
QComboBox,
QLineEdit,
QAbstractSpinBox {{
    min-height: {SIZE_CONTROL_MIN_HEIGHT};
    padding: {SIZE_CONTROL_PADDING};
}}

QPushButton {{
    min-height: {SIZE_BUTTON_MIN_HEIGHT};
    padding: {SIZE_BUTTON_PADDING};
    text-align: center;
    font-size: 11px;
}}

QPushButton[role="compactAction"] {{
    min-height: {SIZE_COMPACT_BUTTON_MIN_HEIGHT};
    padding: {SIZE_CONTROL_PADDING};
    font-size: 10px;
}}

QPushButton:hover,
QToolButton:hover,
QComboBox:hover,
QLineEdit:hover,
QAbstractSpinBox:hover {{
    background: {CONTROL_BG_HOVER};
    border: 1px solid {HAIRLINE_STRONG};
}}

QPushButton:pressed,
QToolButton:pressed,
QComboBox:on {{
    background: {CONTROL_BG_PRESSED};
}}

QPushButton:focus,
QToolButton:focus,
QComboBox:focus,
QLineEdit:focus,
QAbstractSpinBox:focus,
QCheckBox:focus,
QTabBar::tab:focus {{
    border: 1px solid {rgba(ACCENT, 0.4)};
    outline: none;
}}

QPushButton:disabled,
QToolButton:disabled,
QComboBox:disabled,
QAbstractSpinBox:disabled {{
    background: {DISABLED_BG};
    color: {rgba('#FFFFFF', 0.22)};
    border: 1px solid {HAIRLINE};
}}

QLineEdit,
QAbstractSpinBox,
QTextEdit,
QPlainTextEdit {{
    selection-background-color: {TEXT_SELECTION_BG};
    selection-color: {TEXT_BRIGHT};
}}

QLineEdit,
QAbstractSpinBox {{
    font-size: 11px;
}}

/* 数值输入：比卡片表面深一档，作为「可编辑」的视觉暗示 */
QSpinBox,
QDoubleSpinBox {{
    background: {SURFACE_1};
    color: {TEXT_2};
    border: 1px solid {HAIRLINE};
    border-radius: {R_CONTROL}px;
    padding: 2px 6px;
    min-height: 20px;
    selection-background-color: {rgba(ACCENT, 0.28)};
    selection-color: {TEXT_1};
}}

QSpinBox:hover,
QDoubleSpinBox:hover {{
    background: {SURFACE_1};
    border: 1px solid {HAIRLINE_STRONG};
    color: {TEXT_1};
}}

QSpinBox:focus,
QDoubleSpinBox:focus {{
    border: 1px solid {rgba(ACCENT, 0.45)};
    color: {TEXT_1};
}}

QComboBox {{
    font-size: 10.5px;
}}

QComboBox::drop-down {{
    border: none;
    width: {SIZE_COMBO_DROPDOWN_WIDTH};
    background: transparent;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 4px solid {TEXT_3};
    width: 0px;
    height: 0px;
    margin-right: 5px;
}}

QComboBox::down-arrow:hover {{
    border-top: 4px solid {ACCENT};
}}

QAbstractSpinBox::up-button,
QAbstractSpinBox::down-button {{
    background: transparent;
    border: none;
    width: {SIZE_SPIN_BUTTON_WIDTH};
    subcontrol-origin: border;
}}

QAbstractSpinBox::up-button:hover,
QAbstractSpinBox::down-button:hover,
QAbstractSpinBox::up-button:pressed,
QAbstractSpinBox::down-button:pressed {{
    background: {rgba('#FFFFFF', 0.05)};
    border: none;
}}

QComboBox QAbstractItemView {{
    background: {CONTROL_MENU_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {HAIRLINE_STRONG};
    border-radius: {R_CONTROL}px;
    padding: 4px;
    selection-background-color: {CONTROL_SELECTION_BG};
    selection-color: {TEXT_1};
    outline: none;
}}

QComboBox QAbstractItemView::item {{
    border-radius: 4px;
    padding: 3px 6px;
    min-height: 18px;
}}

QComboBox QAbstractItemView::item:selected {{
    background: {CONTROL_SELECTION_BG};
}}

QMenu {{
    background: {CONTROL_MENU_BG};
    border: 1px solid {HAIRLINE_STRONG};
    border-radius: {R_CONTROL}px;
    padding: 4px;
}}

QMenu::item {{
    border-radius: 4px;
    padding: 4px 14px 4px 10px;
}}

QMenu::item:selected {{
    background: {CONTROL_SELECTION_BG};
    color: {TEXT_1};
}}

QAbstractItemView {{
    alternate-background-color: {CONTROL_BG_HOVER};
    selection-background-color: {CONTROL_SELECTION_BG};
    selection-color: {TEXT_BRIGHT};
    border: none;
    outline: none;
}}

QAbstractItemView::item:selected {{
    background: {CONTROL_SELECTION_BG};
}}

QHeaderView::section {{
    background: {HEADER_BG};
    color: {TEXT_HEADER_SECTION};
    border: none;
    padding: {SIZE_HEADER_PADDING};
    font-size: 9px;
    letter-spacing: 0.8px;
}}

/* ── 滑块：细轨道 + 圆形把手 ──────────────────────────────── */
QSlider {{
    background: transparent;
    border: none;
    min-height: 16px;
}}

QSlider::groove:horizontal {{
    height: 3px;
    background: {rgba('#FFFFFF', 0.10)};
    border: none;
    border-radius: 1px;
    margin: 0px 0px;
}}

QSlider::sub-page:horizontal {{
    background: {rgba(ACCENT, 0.55)};
    border: none;
    border-radius: 1px;
}}

QSlider::add-page:horizontal {{
    background: {rgba('#FFFFFF', 0.08)};
    border: none;
    border-radius: 1px;
}}

QSlider::handle:horizontal {{
    background: {TEXT_1};
    border: none;
    width: 10px;
    height: 10px;
    margin: -4px 0px;
    border-radius: 5px;
}}

QSlider::handle:horizontal:hover {{
    background: {ACCENT_STRONG};
    width: 12px;
    height: 12px;
    margin: -5px 0px;
    border-radius: 6px;
}}

QSlider::handle:horizontal:pressed {{
    background: {ACCENT};
}}

QSlider::handle:horizontal:disabled {{
    background: {rgba('#FFFFFF', 0.2)};
}}

QSlider::groove:horizontal:disabled {{
    background: {rgba('#FFFFFF', 0.05)};
}}

/* ── 复选框：14px 圆角方块，选中为黄铜 ───────────────────── */
QCheckBox {{
    spacing: {SIZE_CHECKBOX_SPACING};
    background: transparent;
    border: none;
    color: {TEXT_2};
    font-size: 10.5px;
}}

QCheckBox::indicator {{
    width: {SIZE_CHECKBOX_INDICATOR};
    height: {SIZE_CHECKBOX_INDICATOR};
    border: 1px solid {HAIRLINE_STRONG};
    border-radius: 4px;
    background: {SURFACE_1};
}}

QCheckBox::indicator:hover {{
    border: 1px solid {rgba(ACCENT, 0.5)};
    background: {SURFACE_2};
}}

QCheckBox::indicator:checked {{
    background: {CHECKED_BG};
    border: 1px solid {CHECKED_BG};
}}

QCheckBox::indicator:checked:disabled,
QCheckBox::indicator:unchecked:disabled {{
    background: {DISABLED_BG};
    border: 1px solid {HAIRLINE};
}}

QToolButton {{
    background: transparent;
    border: none;
    padding: {SIZE_TOOLBUTTON_PADDING};
}}

QToolButton:hover,
QToolButton:checked,
QToolButton:pressed {{
    background: {rgba('#FFFFFF', 0.04)};
}}

QToolButton[popupMode="1"] {{
    padding-right: {SIZE_TOOLBUTTON_POPUP_PADDING_RIGHT};
}}

QFormLayout {{
    spacing: {SIZE_FORM_SPACING};
}}

QLabel {{
    background: transparent;
    border: none;
    color: {TEXT_2};
    font-size: 10.5px;
}}

QToolTip {{
    background: {SURFACE_3};
    color: {TEXT_1};
    border: 1px solid {HAIRLINE_STRONG};
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 10px;
}}
"""

CHROME_STYLE = f"""
QSplitter::handle {{
    background: {HAIRLINE};
    width: 1px;
}}

QSplitter::handle:horizontal {{
    margin: 0px;
}}

QScrollBar:vertical {{
    background: transparent;
    border: none;
    width: 8px;
    margin: 2px 2px 2px 0px;
}}

QScrollBar:horizontal {{
    background: transparent;
    border: none;
    height: 8px;
    margin: 0px 2px 2px 2px;
}}

QScrollBar::handle:vertical,
QScrollBar::handle:horizontal {{
    background: {SCROLLBAR_HANDLE_BG};
    border: none;
    border-radius: 3px;
    min-height: {SIZE_SCROLLBAR_HANDLE_MIN};
    min-width: {SIZE_SCROLLBAR_HANDLE_MIN};
}}

QScrollBar::handle:vertical:hover,
QScrollBar::handle:horizontal:hover {{
    background: {rgba('#FFFFFF', 0.2)};
}}

QScrollBar::add-line,
QScrollBar::sub-line,
QScrollBar::add-page,
QScrollBar::sub-page {{
    background: transparent;
    border: none;
    height: 0px;
    width: 0px;
}}

QFrame,
QGroupBox,
QDockWidget,
QToolBox,
QWidget[class="qt-scrollarea-viewport"] {{
    border: none;
}}

QStatusBar {{
    background: transparent;
    color: {TEXT_STATUS};
    border: none;
    min-height: {SIZE_FOOTER_MIN_HEIGHT};
    font-size: 10px;
    letter-spacing: 0.4px;
}}

QStatusBar::item {{
    border: none;
}}

QScrollArea {{
    background: transparent;
    border: none;
}}
"""
