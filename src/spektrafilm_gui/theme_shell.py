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
    R_LARGE,
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

QWidget#libraryHeader {{
    background: {SURFACE_0};
    border-bottom: 1px solid {HAIRLINE};
}}

QScrollArea#libraryScroll,
QWidget#libraryBody {{
    background: transparent;
    border: none;
}}
QScrollArea#libraryScroll > QWidget > QWidget {{ background: transparent; }}
QWidget#photoGrid {{ background: transparent; }}

QLabel#libraryTitle {{
    color: {TEXT_1};
    font-size: 26px;
    font-weight: 500;
    letter-spacing: 0.2px;
}}

QLabel#librarySubtitle,
QLabel#librarySectionCount,
QLabel#photoMeta,
QLabel#folderCount,
QLabel#presetMeta,
QLabel#editorMeta {{
    color: {TEXT_3};
    font-size: 11px;
}}

QLabel#librarySectionTitle {{
    color: {TEXT_1};
    font-size: 18px;
    font-weight: 500;
}}

QLabel#folderName {{
    color: {TEXT_1};
    font-size: 12px;
    font-weight: 500;
}}

QLabel#photoName {{
    color: {TEXT_1};
    font-size: 11.5px;
}}

QPushButton#primaryAction {{
    background: transparent;
    color: {ACCENT};
    border: 1px solid {rgba(ACCENT, 0.55)};
    border-radius: {R_SMALL}px;
    padding: 7px 18px;
    font-size: 12px;
    font-weight: 500;
}}
QPushButton#primaryAction:hover {{ background: {rgba(ACCENT, 0.10)}; border-color: {rgba(ACCENT, 0.8)}; }}
QPushButton#primaryAction:pressed {{ background: {rgba(ACCENT, 0.16)}; border-color: {rgba(ACCENT, 0.8)}; }}
QPushButton#primaryAction:focus {{ border-color: {rgba(ACCENT, 0.8)}; }}
QPushButton#primaryAction:disabled {{ background: transparent; color: {rgba(ACCENT, 0.32)}; border-color: {rgba(ACCENT, 0.2)}; }}

QPushButton#secondaryAction {{
    background: transparent;
    color: {TEXT_2};
    border: 1px solid {HAIRLINE_STRONG};
    border-radius: {R_SMALL}px;
    padding: 7px 16px;
    font-size: 12px;
    font-weight: 500;
}}
QPushButton#secondaryAction:hover {{
    background: {rgba('#FFFFFF', 0.04)};
    border-color: {rgba('#FFFFFF', 0.22)};
    color: {TEXT_1};
}}
QPushButton#secondaryAction:pressed {{ background: {rgba('#FFFFFF', 0.02)}; }}
QPushButton#secondaryAction:disabled {{ background: transparent; color: {rgba('#FFFFFF', 0.22)}; }}

QPushButton#ghostAction {{
    background: transparent;
    color: {TEXT_2};
    border: none;
    border-radius: {R_SMALL}px;
    padding: 6px 9px;
    font-size: 11.5px;
}}
QPushButton#ghostAction:hover {{ color: {TEXT_1}; background: {rgba('#FFFFFF', 0.06)}; }}
QPushButton#ghostAction:pressed {{ color: {TEXT_1}; background: {rgba('#FFFFFF', 0.04)}; }}
QPushButton#ghostAction:checked {{ color: {ACCENT}; background: {rgba(ACCENT, 0.12)}; }}

QPushButton#backAction {{
    background: transparent;
    border: none;
    padding: 4px;
}}
QPushButton#backAction:hover {{ background: {rgba('#FFFFFF', 0.07)}; border-radius: 8px; }}

QPushButton#iconButton {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 3px;
}}
QPushButton#iconButton:hover {{ background: {rgba('#FFFFFF', 0.08)}; }}
QPushButton#iconButton:pressed {{ background: {rgba('#FFFFFF', 0.05)}; }}
QPushButton#iconButton:checked {{ background: {rgba(ACCENT, 0.16)}; }}

QLineEdit#librarySearch,
QLineEdit#presetSearch {{
    background: {SURFACE_2};
    color: {TEXT_1};
    border: 1px solid {HAIRLINE};
    border-radius: {R_SMALL}px;
    padding: 6px 10px;
    font-size: 12px;
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_ON};
}}
QLineEdit#librarySearch:focus,
QLineEdit#presetSearch:focus {{ border-color: {rgba(ACCENT, 0.45)}; }}

QComboBox#librarySort {{
    background: {SURFACE_2};
    color: {TEXT_2};
    border: 1px solid {HAIRLINE};
    border-radius: {R_SMALL}px;
    padding: 5px 10px;
    font-size: 11.5px;
}}
QComboBox#librarySort:hover {{ color: {TEXT_1}; border-color: {HAIRLINE_STRONG}; }}
QComboBox#librarySort::drop-down {{ border: none; width: 18px; }}
QComboBox#librarySort QAbstractItemView {{
    background: {SURFACE_2};
    color: {TEXT_1};
    border: 1px solid {HAIRLINE_STRONG};
    selection-background-color: {SURFACE_4};
    padding: 4px;
}}

QPushButton#filterChip {{
    background: transparent;
    color: {TEXT_3};
    border: 1px solid transparent;
    border-radius: 13px;
    padding: 5px 13px;
    font-size: 11.5px;
}}
QPushButton#filterChip:hover {{ color: {TEXT_1}; background: {rgba('#FFFFFF', 0.05)}; }}
QPushButton#filterChip:checked {{
    color: {TEXT_1};
    background: {SURFACE_3};
    border-color: {HAIRLINE_STRONG};
}}

QFrame#folderCard {{
    background: {SURFACE_2};
    border: 1px solid {HAIRLINE};
    border-radius: {R_MEDIUM}px;
}}
QFrame#folderCard:hover {{
    background: {SURFACE_3};
    border-color: {HAIRLINE_STRONG};
}}
QFrame#folderCard[selected="true"] {{
    border-color: {rgba(ACCENT, 0.75)};
    background: {SURFACE_3};
}}

QFrame#photoCard {{
    background: transparent;
    border: none;
}}
QFrame#photoCard[selected="true"] QLabel#photoName {{ color: {ACCENT}; }}
QFrame#photoCard[missing="true"] QLabel#photoName {{ color: {TEXT_3}; }}

QLabel#photoThumb {{
    background: {SURFACE_2};
    border: 1px solid transparent;
    border-radius: 10px;
}}
QFrame#photoCard:hover QLabel#photoThumb {{
    background: {SURFACE_3};
    border-color: {HAIRLINE_STRONG};
}}
QFrame#photoCard[selected="true"] QLabel#photoThumb {{
    border-color: {rgba(ACCENT, 0.85)};
}}

QPushButton#starButton {{
    background: {rgba('#0B0B0B', 0.55)};
    border: none;
    border-radius: 11px;
    padding: 3px;
}}
QPushButton#starButton:hover {{ background: {rgba('#0B0B0B', 0.8)}; }}
QPushButton#colorButton {{
    background: {rgba('#0B0B0B', 0.55)};
    border: none;
    border-radius: 11px;
    padding: 3px;
}}

QWidget#emptyState {{
    background: transparent;
}}
QFrame#emptyCard {{
    background: {SURFACE_1};
    border: 1px solid {HAIRLINE_STRONG};
    border-radius: {R_LARGE}px;
}}
QWidget#emptyButtons {{
    background: transparent;
}}
QLabel#emptyTitle {{ color: {TEXT_1}; font-size: 17px; font-weight: 500; }}
QLabel#emptyHint {{ color: {TEXT_3}; font-size: 12px; }}
QLabel#emptyFormats {{
    color: {TEXT_3};
    font-size: 10.5px;
    letter-spacing: 0.4px;
}}

QWidget#editorTopBar {{
    background: {SURFACE_0};
    border-bottom: 1px solid {HAIRLINE};
}}
QLabel#editorTitle {{ color: {TEXT_1}; font-size: 12px; font-weight: 500; }}
QLabel#editorMeta {{ color: {TEXT_3}; font-size: 10.5px; }}
QPushButton#compactBack {{
    color: {TEXT_1};
    background: {SURFACE_1};
    border: 1px solid {HAIRLINE};
    border-radius: 7px;
    padding: 0px 11px;
    font-size: 11px;
    font-weight: 500;
}}
QPushButton#compactBack:hover {{ background: {SURFACE_2}; border-color: {HAIRLINE_STRONG}; }}
QPushButton#compactBack:pressed {{ background: {SURFACE_1}; }}

QWidget#previewStage {{
    background: {SURFACE_0};
}}
/* 画布浮动层：信息与工具不做通栏条，悬浮在画面上 */
QLabel#previewChip {{
    background: {rgba('#0B0B0B', 0.72)};
    color: {TEXT_2};
    border: 1px solid {HAIRLINE_STRONG};
    border-radius: 11px;
    padding: 4px 10px;
    font-size: 10.5px;
}}
QLabel#floatInfo {{
    background: {rgba('#0B0B0B', 0.66)};
    color: {TEXT_2};
    border: 1px solid {HAIRLINE_STRONG};
    border-radius: 10px;
    padding: 4px 11px;
    font-size: 10.5px;
}}
QWidget#floatToolbar {{
    background: {rgba('#0B0B0B', 0.66)};
    border: 1px solid {HAIRLINE_STRONG};
    border-radius: 16px;
}}
QWidget#floatToolbar QPushButton#iconButton {{
    padding: 4px;
}}
QWidget#floatToolbar QPushButton#ghostAction {{
    padding: 5px 8px;
    font-size: 10.5px;
}}

QWidget#presetRail {{
    background: {SURFACE_1};
    border-right: 1px solid {HAIRLINE};
}}
QPushButton#modeTab {{
    color: {TEXT_3};
    background: transparent;
    border: 1px solid {HAIRLINE};
    border-radius: 6px;
    padding: 0px 9px;
    font-size: 10.5px;
}}
QPushButton#modeTab:hover {{ color: {TEXT_2}; background: {rgba(SURFACE_2, 0.7)}; }}
QPushButton#modeTab:checked {{
    color: {ACCENT};
    background: {SURFACE_2};
    border-color: {rgba(ACCENT, 0.3)};
    font-weight: 500;
}}
QPushButton#brandChip {{
    background: transparent;
    color: {TEXT_3};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 0px 8px;
    font-size: 10.5px;
}}
QPushButton#brandChip:hover {{ color: {TEXT_1}; background: {rgba('#FFFFFF', 0.04)}; }}
QPushButton#brandChip:checked {{
    color: {ACCENT};
    border-color: {rgba(ACCENT, 0.3)};
    background: {rgba(ACCENT, 0.08)};
}}

QLineEdit#presetSearch {{
    background: {SURFACE_0};
    color: {TEXT_1};
    border: 1px solid {HAIRLINE};
    border-radius: 7px;
    padding: 0px 9px;
    font-size: 11px;
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_ON};
}}

QFrame#presetCard {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
}}
QFrame#presetCard:hover {{ background: {SURFACE_2}; }}
QFrame#presetCard[selected="true"] {{
    background: {SURFACE_3};
    border-color: {rgba(ACCENT, 0.72)};
}}
QLabel#presetName {{ color: {TEXT_2}; font-size: 12.5px; }}
QFrame#presetCard[selected="true"] QLabel#presetName {{ color: {ACCENT_STRONG}; font-weight: 500; }}
QLabel#presetMeta {{ color: {TEXT_3}; font-size: 10.5px; }}
QLabel#presetBrand {{
    color: {TEXT_3}; font-size: 9px; font-weight: 500;
    letter-spacing: 0.9px;
}}

QWidget#inspectorPanel {{
    background: {SURFACE_1};
    border-left: 1px solid {HAIRLINE};
}}
QWidget#histogramCard {{
    background: {SURFACE_2};
    border: 1px solid {HAIRLINE};
    border-radius: {R_MEDIUM}px;
}}

QLabel#paramLabel {{
    color: {TEXT_2};
    font-size: 11.5px;
}}
QLabel#inspectorSectionLabel {{
    color: {TEXT_3};
    font-size: 10.5px;
    font-weight: 600;
}}
QDoubleSpinBox#paramValue {{
    background: transparent;
    border: none;
    color: {TEXT_2};
    padding: 0px;
    font-size: 11px;
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
    background: {SURFACE_1};
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
    background: {SURFACE_2};
    border: 1px dashed {HAIRLINE_STRONG};
    border-radius: {R_SMALL}px;
}}
QPushButton#filmAddThumb:hover {{
    background: {SURFACE_3};
    border-color: {rgba(ACCENT, 0.55)};
}}

/* 导出：黄铜描边胶囊，内部两段全透明 */
QWidget#exportBox {{
    background: transparent;
    border: 1px solid {rgba(ACCENT, 0.55)};
    border-radius: 7px;
}}
QPushButton#exportButton {{
    background: transparent;
    color: {ACCENT};
    border: none;
    border-top-left-radius: 6px;
    border-bottom-left-radius: 6px;
    padding: 0px 12px;
    font-size: 11.5px;
    font-weight: 500;
}}
QPushButton#exportButton:hover {{ background: {rgba(ACCENT, 0.10)}; }}
QPushButton#exportButton:pressed {{ background: {rgba(ACCENT, 0.16)}; }}
QPushButton#exportButton:disabled {{ background: transparent; color: {TEXT_3}; }}
QPushButton#exportMenu {{
    background: transparent;
    border: none;
    border-left: 1px solid {rgba(ACCENT, 0.35)};
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}}
QPushButton#exportMenu:hover {{ background: {rgba(ACCENT, 0.10)}; }}
QPushButton#exportMenu:pressed {{ background: {rgba(ACCENT, 0.16)}; }}
QPushButton#exportMenu:disabled {{ background: transparent; }}
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
