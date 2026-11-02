"""照片库设计系统。

只描述照片库的视觉语言（网格密度、卡片比例、控件尺寸、字号、状态），
不承载任何业务逻辑。所有尺寸集中在这里，页面与 QSS 共享同一套数值，
避免"卡片一个宽度、缩略图另一个宽度"的漂移。
"""

from __future__ import annotations

from spektrafilm_gui.theme_oflim import (
    ACCENT,
    ACCENT_DIM,
    ACCENT_ON,
    ACCENT_STRONG,
    CONTROL_HEIGHT,
    CONTROL_HEIGHT_SMALL,
    FONT_BODY,
    FONT_CAPTION,
    FONT_MICRO,
    FONT_SECTION,
    FONT_TITLE,
    HAIRLINE,
    HAIRLINE_STRONG,
    SURFACE_0,
    SURFACE_1,
    SURFACE_2,
    SURFACE_3,
    TEXT_1,
    TEXT_2,
    TEXT_3,
    TEXT_4,
    rgba,
)

# ── 网格与卡片 ──────────────────────────────────────────────────
CARD_MIN_WIDTH = 260
CARD_MAX_WIDTH = 340
CARD_GAP_X = 20
CARD_GAP_Y = 22
CARD_RADIUS = 9
THUMB_ASPECT = 3.0 / 4.0  # 统一 4:3

NAME_HEIGHT = 18
META_HEIGHT = 15
CARD_TEXT_GAP = 9
CARD_TEXT_STACK = CARD_TEXT_GAP + NAME_HEIGHT + 3 + META_HEIGHT

# ── 列表视图 ────────────────────────────────────────────────────
LIST_ROW_HEIGHT = 76
LIST_THUMB_WIDTH = 96
LIST_THUMB_HEIGHT = 72  # 96 × 72 = 4:3

# ── 页面节奏 ────────────────────────────────────────────────────
PAGE_MARGIN_X = 28
PAGE_MARGIN_TOP = 15
PAGE_MARGIN_BOTTOM = 30

COLOR_TONES = {
    'red': '#C7705D',
    'yellow': '#C8A97E',
    'green': '#7D9B76',
    'blue': '#6B8CAE',
}


def card_height(card_width: int) -> int:
    return round(card_width * THUMB_ASPECT) + CARD_TEXT_STACK


LIBRARY_STYLE_SHEET = f"""
/* ══ 页面骨架 ══════════════════════════════════════════════════ */
QWidget#libraryHeader {{
    background: {SURFACE_0};
    border-bottom: 1px solid {HAIRLINE};
}}
QScrollArea#libraryScroll,
QWidget#libraryBody,
QWidget#libraryContent,
QWidget#listBody,
QWidget#photoGrid,
QWidget#emptyState {{
    background: transparent;
    border: none;
}}
QScrollArea#libraryScroll > QWidget > QWidget {{ background: transparent; }}
QScrollArea#libraryScroll QScrollBar:vertical {{
    width: 0px;
    background: transparent;
    border: none;
}}

/* ══ 字体层级 ══════════════════════════════════════════════════ */
QLabel#libraryTitle {{
    color: {TEXT_1};
    font-size: {FONT_TITLE}px;
    font-weight: 500;
    letter-spacing: 0.4px;
}}
QLabel#librarySubtitle {{
    color: {TEXT_3};
    font-size: {FONT_CAPTION}px;
    letter-spacing: 0.1px;
}}
QLabel#librarySectionTitle {{
    color: {TEXT_2};
    font-size: {FONT_SECTION}px;
    font-weight: 600;
    letter-spacing: 0.3px;
}}
QLabel#librarySectionCount {{
    color: {TEXT_3};
    font-size: {FONT_CAPTION}px;
}}
QLabel#photoName {{
    color: {TEXT_1};
    font-size: {FONT_BODY}px;
}}
QLabel#photoMeta {{
    color: {TEXT_3};
    font-size: {FONT_CAPTION}px;
}}

/* ══ 顶部工具栏 ════════════════════════════════════════════════ */
QPushButton#primaryAction {{
    background: {ACCENT};
    color: {ACCENT_ON};
    border: none;
    border-radius: 8px;
    padding: 0px 14px;
    min-height: {CONTROL_HEIGHT}px;
    max-height: {CONTROL_HEIGHT}px;
    font-size: {FONT_BODY}px;
    font-weight: 600;
}}
QPushButton#primaryAction:hover {{ background: {ACCENT_STRONG}; }}
QPushButton#primaryAction:pressed {{ background: {ACCENT_DIM}; }}
QPushButton#primaryAction:focus {{ background: {ACCENT_STRONG}; }}
QPushButton#primaryAction:disabled {{ background: {SURFACE_3}; color: {TEXT_4}; }}

QPushButton#secondaryAction {{
    background: transparent;
    color: {TEXT_2};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 0px 10px;
    min-height: {CONTROL_HEIGHT}px;
    max-height: {CONTROL_HEIGHT}px;
    font-size: {FONT_BODY}px;
    font-weight: 500;
}}
QPushButton#secondaryAction:hover {{
    color: {TEXT_1};
    background: {rgba('#FFFFFF', 0.06)};
}}
QPushButton#secondaryAction:pressed {{ background: {rgba('#FFFFFF', 0.03)}; }}
QPushButton#secondaryAction:focus {{ border-color: {rgba(ACCENT, 0.45)}; }}
QPushButton#secondaryAction:disabled {{ color: {TEXT_4}; }}

QLineEdit#librarySearch {{
    background: {SURFACE_1};
    color: {TEXT_1};
    border: 1px solid {HAIRLINE};
    border-radius: 8px;
    padding: 0px 9px;
    min-height: {CONTROL_HEIGHT}px;
    max-height: {CONTROL_HEIGHT}px;
    font-size: {FONT_BODY}px;
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_ON};
}}
QLineEdit#librarySearch:hover {{ border-color: {HAIRLINE_STRONG}; }}
QLineEdit#librarySearch:focus {{
    background: {SURFACE_2};
    border-color: {rgba(ACCENT, 0.4)};
}}

QPushButton#librarySort {{
    background: transparent;
    color: {TEXT_3};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 0px 22px 0px 12px;
    min-height: {CONTROL_HEIGHT}px;
    max-height: {CONTROL_HEIGHT}px;
    font-size: {FONT_BODY}px;
    text-align: left;
}}
QPushButton#librarySort:hover {{
    color: {TEXT_1};
    background: {rgba('#FFFFFF', 0.06)};
}}
QPushButton#librarySort:pressed {{ background: {rgba('#FFFFFF', 0.03)}; }}
QPushButton#librarySort:focus {{ border-color: {rgba(ACCENT, 0.45)}; color: {TEXT_1}; }}

QWidget#viewToggle {{
    background: {SURFACE_1};
    border: 1px solid {HAIRLINE};
    border-radius: 8px;
}}
QPushButton#viewToggleButton {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 0px;
    min-width: 27px;
    max-width: 27px;
    min-height: 26px;
    max-height: 26px;
}}
QPushButton#viewToggleButton:hover {{ background: {rgba('#FFFFFF', 0.07)}; }}
QPushButton#viewToggleButton:pressed {{ background: {rgba('#FFFFFF', 0.04)}; }}
QPushButton#viewToggleButton:checked {{ background: {SURFACE_3}; }}
QPushButton#viewToggleButton:focus {{ border: 1px solid {rgba(ACCENT, 0.45)}; }}

QPushButton#filterChip {{
    background: transparent;
    color: {TEXT_3};
    border: 1px solid transparent;
    border-radius: 13px;
    padding: 0px 11px;
    min-height: {CONTROL_HEIGHT_SMALL}px;
    max-height: {CONTROL_HEIGHT_SMALL}px;
    font-size: {FONT_BODY}px;
}}
QPushButton#filterChip:hover {{
    color: {TEXT_1};
    background: {rgba('#FFFFFF', 0.05)};
}}
QPushButton#filterChip:pressed {{ background: {rgba('#FFFFFF', 0.03)}; }}
QPushButton#filterChip:focus {{ border-color: {rgba(ACCENT, 0.45)}; }}
QPushButton#filterChip:checked {{
    color: {TEXT_1};
    background: {SURFACE_2};
    border-color: {HAIRLINE_STRONG};
}}
QPushButton#filterChip[tone="red"]:checked {{
    background: {rgba(COLOR_TONES['red'], 0.13)};
    border-color: {rgba(COLOR_TONES['red'], 0.42)};
}}
QPushButton#filterChip[tone="yellow"]:checked {{
    background: {rgba(COLOR_TONES['yellow'], 0.13)};
    border-color: {rgba(COLOR_TONES['yellow'], 0.42)};
}}
QPushButton#filterChip[tone="green"]:checked {{
    background: {rgba(COLOR_TONES['green'], 0.13)};
    border-color: {rgba(COLOR_TONES['green'], 0.42)};
}}
QPushButton#filterChip[tone="blue"]:checked {{
    background: {rgba(COLOR_TONES['blue'], 0.13)};
    border-color: {rgba(COLOR_TONES['blue'], 0.42)};
}}
QFrame#chipDivider {{
    background: {HAIRLINE_STRONG};
    border: none;
}}

/* ══ 卡片：照片本身是主体，卡片不带壳 ═════════════════════════ */
QFrame#photoCard {{
    background: transparent;
    border: none;
}}
QFrame#photoCard[selected="true"] QLabel#photoName {{ color: {ACCENT_STRONG}; }}

QPushButton#starButton,
QPushButton#colorButton,
QPushButton#moreButton {{
    background: {rgba(SURFACE_0, 0.58)};
    border: 1px solid {rgba('#FFFFFF', 0.10)};
    border-radius: 11px;
    padding: 0px;
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
}}
QPushButton#starButton:hover,
QPushButton#colorButton:hover,
QPushButton#moreButton:hover {{
    background: {SURFACE_3};
    border-color: {rgba('#FFFFFF', 0.18)};
}}
QPushButton#starButton:pressed,
QPushButton#colorButton:pressed,
QPushButton#moreButton:pressed {{ background: {SURFACE_2}; }}

/* ══ 列表视图 ══════════════════════════════════════════════════ */
QFrame#photoRow {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
}}
QFrame#photoRow[hover="true"] {{
    background: {SURFACE_1};
    border-color: {HAIRLINE};
}}
QFrame#photoRow[selected="true"] {{
    background: {rgba(ACCENT, 0.08)};
    border-color: {rgba(ACCENT, 0.28)};
}}
QFrame#photoRow[selected="true"] QLabel#photoName {{ color: {ACCENT_STRONG}; }}
QWidget#photoText {{ background: transparent; }}
QWidget#cardControls {{ background: transparent; }}
QFrame#photoRow QPushButton#starButton,
QFrame#photoRow QPushButton#colorButton,
QFrame#photoRow QPushButton#moreButton {{
    background: transparent;
    border-color: transparent;
}}
QFrame#photoRow QPushButton#starButton:hover,
QFrame#photoRow QPushButton#colorButton:hover,
QFrame#photoRow QPushButton#moreButton:hover {{
    background: {SURFACE_3};
    border-color: {HAIRLINE_STRONG};
}}

/* ══ 空状态：不用卡片框，靠留白与标题建立重心 ═══════════════════ */
QFrame#emptyMark {{
    background: {SURFACE_1};
    border: 1px solid {HAIRLINE_STRONG};
    border-radius: 38px;
}}
QLabel#emptyTitle {{
    color: {TEXT_1};
    font-size: 16px;
    font-weight: 500;
    letter-spacing: 0.2px;
}}
QLabel#emptyHint {{ color: {TEXT_3}; font-size: {FONT_BODY}px; }}
QLabel#emptyFormats {{
    color: {TEXT_4};
    font-size: {FONT_MICRO}px;
    letter-spacing: 1.2px;
}}
QWidget#emptyButtons {{ background: transparent; }}

QPushButton#moreAction {{
    background: transparent;
    color: {TEXT_3};
    border: 1px solid {HAIRLINE};
    border-radius: 8px;
    padding: 0px 16px;
    min-height: 32px;
    max-height: 32px;
    font-size: {FONT_BODY}px;
}}
QPushButton#moreAction:hover {{
    color: {TEXT_1};
    border-color: {HAIRLINE_STRONG};
    background: {rgba('#FFFFFF', 0.04)};
}}
"""
