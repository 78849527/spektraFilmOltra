"""新壳层（照片库 + 调整页）的 QSS。

只描述外观，不碰任何控件逻辑。所有选择器都带 objectName，避免级联污染
旧参数面板的样式。
"""

from __future__ import annotations

from spektrafilm_gui.theme_oflim import (
    ACCENT,
    ACCENT_DIM,
    ACCENT_ON,
    ACCENT_STRONG,
    DANGER,
    HAIRLINE,
    HAIRLINE_STRONG,
    R_MEDIUM,
    R_SMALL,
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

SHELL_STYLE_SHEET = f"""
QWidget#libraryPage,
QWidget#editorPage,
QWidget#editorCenter,
QWidget#presetRail,
QWidget#inspectorPanel {{
    background: {SURFACE_0};
    color: {TEXT_1};
}}

/* 照片库的完整视觉规范在 theme_library，这里只保留与编辑页共享的壳层 */

/* 主页与预设台的滚动一律靠滚轮/触控板，滚动条本身不占视觉 */
QScrollArea#railScroll QScrollBar:vertical,
QScrollArea#filmstripScroll QScrollBar:horizontal {{
    width: 0px;
    height: 0px;
    background: transparent;
    border: none;
}}

/* 滚动区视口不吃调色板底色，永远透出页面底 */
QScrollArea#railScroll,
QScrollArea#railScroll > QWidget > QWidget,
QScrollArea#filmstripScroll,
QScrollArea#filmstripScroll > QWidget > QWidget {{
    background: transparent;
    border: none;
}}

QLabel#presetMeta,
QLabel#editorMeta {{
    color: {TEXT_3};
    font-size: 11px;
}}

QPushButton#ghostAction {{
    background: transparent;
    color: {TEXT_2};
    border: none;
    border-radius: {R_SMALL}px;
    padding: 0px 8px;
    min-height: 26px;
    max-height: 26px;
    font-size: 12px;
}}
QPushButton#ghostAction:hover {{ color: {TEXT_1}; background: {rgba('#FFFFFF', 0.06)}; }}
QPushButton#ghostAction:pressed {{ color: {TEXT_1}; background: {rgba('#FFFFFF', 0.04)}; }}
QPushButton#ghostAction:checked {{ color: {ACCENT}; background: {rgba(ACCENT, 0.12)}; }}
QPushButton#ghostAction::menu-indicator {{ image: none; width: 0px; }}

QPushButton#backAction {{
    background: transparent;
    border: none;
    padding: 4px;
}}
QPushButton#backAction:hover {{ background: {rgba('#FFFFFF', 0.07)}; border-radius: 8px; }}

QPushButton#iconButton {{
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 0px;
    min-height: 28px;
    max-height: 28px;
}}
QPushButton#iconButton:hover {{ background: {rgba('#FFFFFF', 0.08)}; }}
QPushButton#iconButton:pressed {{ background: {rgba('#FFFFFF', 0.05)}; }}
QPushButton#iconButton:checked {{ background: {rgba(ACCENT, 0.16)}; }}
QPushButton#favoriteButton {{
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 0px;
    min-height: 30px;
    max-height: 30px;
}}
QPushButton#favoriteButton:hover {{ background: {rgba('#FFFFFF', 0.08)}; }}
QPushButton#favoriteButton:checked {{ background: {rgba(ACCENT, 0.16)}; }}

QLineEdit#presetSearch {{
    background: {SURFACE_2};
    color: {TEXT_1};
    border: 1px solid {HAIRLINE};
    border-radius: {R_SMALL}px;
    padding: 0px 10px;
    min-height: 30px;
    max-height: 30px;
    font-size: 12px;
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_ON};
}}
QLineEdit#presetSearch:focus {{ border-color: {rgba(ACCENT, 0.45)}; }}

QWidget#editorTopBar {{
    background: {SURFACE_0};
    border-bottom: 1px solid {HAIRLINE};
}}
QLabel#editorTitle {{ color: {TEXT_1}; font-size: 14px; font-weight: 500; }}
QLabel#editorMeta {{ color: {TEXT_3}; font-size: 11px; }}
QLabel#editorBusy {{ color: {ACCENT}; font-size: 11px; }}
QPushButton#compactBack {{
    color: {TEXT_2};
    background: transparent;
    border: 1px solid {HAIRLINE};
    border-radius: 8px;
    padding: 0px 12px;
    min-height: 28px;
    max-height: 28px;
    font-size: 12px;
    font-weight: 500;
}}
QPushButton#compactBack:hover {{ background: {SURFACE_2}; border-color: {HAIRLINE_STRONG}; color: {TEXT_1}; }}
QPushButton#compactBack:pressed {{ background: {SURFACE_1}; }}

QWidget#previewStage {{
    background: {SURFACE_0};
}}
/* 画布浮动层：一条工具条 + 一行纯文字信息，不再有多个盒子 */
QLabel#previewChip {{
    background: {rgba(SURFACE_1, 0.92)};
    color: {TEXT_2};
    border: 1px solid {HAIRLINE_STRONG};
    border-radius: 12px;
    padding: 4px 11px;
    font-size: 11px;
}}
QLabel#floatInfo {{
    background: transparent;
    border: none;
    color: {TEXT_3};
    font-size: 11px;
}}
QWidget#floatBar {{
    background: {rgba(SURFACE_1, 0.94)};
    border: 1px solid {HAIRLINE_STRONG};
    border-radius: 12px;
}}
QPushButton#scalePill {{
    background: transparent;
    color: {TEXT_2};
    border: none;
    border-radius: 9px;
    padding: 0px 8px;
    min-height: 26px;
    max-height: 26px;
    font-size: 11px;
}}
QPushButton#scalePill:hover {{ color: {TEXT_1}; background: {rgba('#FFFFFF', 0.07)}; }}
QPushButton#scalePill::menu-indicator {{ image: none; width: 0px; }}
QWidget#floatBar QPushButton#iconButton {{
    padding: 0px;
    min-height: 26px;
    max-height: 26px;
}}
QWidget#floatBar QPushButton#ghostAction {{
    padding: 0px 8px;
}}
QFrame#floatDivider {{
    background: {HAIRLINE_STRONG};
    border: none;
}}

QWidget#presetRail {{
    background: {SURFACE_0};
    border-right: 1px solid {HAIRLINE};
}}
QPushButton#modeTab {{
    color: {TEXT_3};
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 0px 12px;
    min-height: 26px;
    max-height: 26px;
    font-size: 12px;
}}
QPushButton#modeTab:hover {{ color: {TEXT_1}; background: {SURFACE_2}; }}
QPushButton#modeTab:checked {{
    color: {TEXT_1};
    background: {SURFACE_3};
    border-color: {HAIRLINE_STRONG};
    font-weight: 500;
}}
QPushButton#brandChip {{
    background: transparent;
    color: {TEXT_3};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 0px 10px;
    min-height: 26px;
    max-height: 26px;
    font-size: 12px;
}}
QPushButton#brandChip:hover {{ color: {TEXT_1}; background: {SURFACE_2}; }}
QPushButton#brandChip:checked {{
    color: {ACCENT};
    border-color: {rgba(ACCENT, 0.28)};
    background: {rgba(ACCENT, 0.09)};
    font-weight: 500;
}}

QLineEdit#presetSearch {{
    background: {SURFACE_2};
    color: {TEXT_1};
    border: 1px solid {HAIRLINE};
    border-radius: 8px;
    padding: 0px 10px;
    min-height: 30px;
    max-height: 30px;
    font-size: 12px;
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_ON};
}}

QFrame#presetCard {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
}}
QFrame#presetCard:hover {{ background: {SURFACE_2}; border-color: {HAIRLINE}; }}
QFrame#presetCard[selected="true"] {{
    background: {SURFACE_3};
    border-color: {rgba(ACCENT, 0.55)};
}}
QLabel#presetName {{ color: {TEXT_1}; font-size: 13px; font-weight: 500; }}
QFrame#presetCard[selected="true"] QLabel#presetName {{ color: {ACCENT_STRONG}; }}
QLabel#presetMeta {{ color: {TEXT_3}; font-size: 11px; }}
QLabel#presetBrand {{
    color: {TEXT_4}; font-size: 11px; font-weight: 500;
    letter-spacing: 0.4px;
}}

QWidget#inspectorPanel {{
    background: {SURFACE_0};
    border-left: 1px solid {HAIRLINE};
}}
QWidget#histogramCard {{
    background: {SURFACE_2};
    border: 1px solid {HAIRLINE};
    border-radius: {R_MEDIUM}px;
}}

QLabel#paramLabel {{
    color: {TEXT_2};
    font-size: 12px;
}}
QLabel#inspectorSectionLabel {{
    color: {TEXT_3};
    font-size: 11px;
    font-weight: 600;
}}
QDoubleSpinBox#paramValue {{
    background: transparent;
    border: none;
    color: {TEXT_2};
    padding: 0px;
    font-size: 11.5px;
}}
QDoubleSpinBox#paramValue:hover,
QDoubleSpinBox#paramValue:focus {{
    color: {TEXT_1};
}}
QPushButton#segmentButton {{
    background: transparent;
    color: {TEXT_3};
    border: none;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 11.5px;
}}
QPushButton#segmentButton:hover {{ color: {TEXT_1}; }}
QPushButton#segmentButton:checked {{
    color: {TEXT_1};
    background: {SURFACE_3};
}}

QWidget#filmstrip {{
    background: {SURFACE_0};
    border-top: 1px solid {HAIRLINE};
}}
QFrame#filmThumb {{
    background: {SURFACE_2};
    border: 1px solid transparent;
    border-radius: {R_SMALL}px;
}}
QFrame#filmThumb:hover {{ border-color: {HAIRLINE_STRONG}; }}
QFrame#filmThumb[selected="true"] {{ border-color: {rgba(ACCENT, 0.85)}; }}
QPushButton#filmAddThumb {{
    background: transparent;
    border: 1px solid {HAIRLINE_STRONG};
    border-radius: {R_SMALL}px;
    min-height: 69px;
    max-height: 69px;
    min-width: 92px;
    max-width: 92px;
}}
QPushButton#filmAddThumb:hover {{
    background: {rgba(ACCENT, 0.08)};
    border-color: {rgba(ACCENT, 0.55)};
}}
QPushButton#filmAddThumb:pressed {{
    background: {rgba(ACCENT, 0.14)};
}}

/* 导出：实心黄铜主按钮 + 独立幽灵箭头，去掉描边胶囊壳 */
QWidget#exportBox {{
    background: transparent;
    border: none;
}}
QPushButton#exportButton {{
    background: {ACCENT};
    color: {ACCENT_ON};
    border: none;
    border-radius: 8px;
    padding: 0px 15px;
    min-height: 28px;
    max-height: 28px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#exportButton:hover {{ background: {ACCENT_STRONG}; }}
QPushButton#exportButton:pressed {{ background: {ACCENT_DIM}; }}
QPushButton#exportButton:disabled {{ background: {SURFACE_3}; color: {TEXT_3}; }}
QPushButton#exportMenu {{
    background: transparent;
    border: none;
    border-radius: 8px;
    min-height: 28px;
    max-height: 28px;
    min-width: 22px;
    max-width: 22px;
}}
QPushButton#exportMenu:hover {{ background: {rgba('#FFFFFF', 0.08)}; }}
QPushButton#exportMenu:pressed {{ background: {rgba('#FFFFFF', 0.05)}; }}
QPushButton#exportMenu::menu-indicator {{ image: none; width: 0px; }}

QMenu {{
    background: {SURFACE_2};
    color: {TEXT_1};
    border: 1px solid {HAIRLINE_STRONG};
    padding: 5px;
}}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 5px; font-size: 12px; }}
QMenu::item:selected {{ background: {SURFACE_4}; }}
QMenu::separator {{ height: 1px; background: {HAIRLINE}; margin: 4px 6px; }}

QLabel#dangerLabel {{ color: {DANGER}; }}

QStatusBar {{
    background: {SURFACE_1};
    color: {TEXT_3};
    border-top: 1px solid {HAIRLINE};
    font-size: 11px;
}}
QStatusBar::item {{ border: none; }}

/* ── 对话框：暗色消息框，避免 Qt 默认的黑底默认按钮 ────────── */
QMessageBox {{
    background: {SURFACE_1};
}}
QMessageBox QLabel {{
    color: {TEXT_1};
    font-size: 12.5px;
    background: transparent;
}}
QMessageBox QPushButton {{
    background: {SURFACE_3};
    color: {TEXT_1};
    border: 1px solid {HAIRLINE_STRONG};
    border-radius: {R_SMALL}px;
    padding: 5px 16px;
    min-width: 72px;
    min-height: 26px;
    font-size: 12px;
    font-weight: 500;
}}
QMessageBox QPushButton:hover {{ background: {SURFACE_4}; }}
QMessageBox QPushButton:pressed {{ background: {SURFACE_2}; }}
QMessageBox QPushButton:default {{
    background: {ACCENT};
    color: {ACCENT_ON};
    border-color: {ACCENT};
}}
QMessageBox QPushButton:default:hover {{ background: {ACCENT_STRONG}; }}
"""
