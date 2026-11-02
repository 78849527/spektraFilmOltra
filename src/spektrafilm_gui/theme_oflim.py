"""OltraFlim 视觉规范在 Qt 侧的移植。

只承载**视觉与交互语言**：表面层级、黄铜强调色、发丝线、圆角、控件形态。
不含任何 oflim 的业务逻辑、调色管线或数据模型——spektrafilm 的参数绑定、
控制器、渲染管线一律保持原样。

设计规则（来自 oflim 的 surface scale）：
相邻表面只相差 1–3% 亮度，分割靠"光"而非黑色描边，字重整体降一档以补偿
光学膨胀。
"""

from __future__ import annotations

# ── 表面层级 ────────────────────────────────────────────────────
SURFACE_0 = '#121315'
SURFACE_1 = '#18191B'
SURFACE_2 = '#202124'
SURFACE_3 = '#282A2D'
SURFACE_4 = '#34363A'

# ── 文本层级（对应 white 的 100/70/54/36% 不透明度）──────────────
TEXT_1 = '#F4F4F2'
TEXT_2 = '#B4B4B0'
TEXT_3 = '#8A8A86'
TEXT_4 = '#5E5E5A'

# ── 发丝线（white 7% / 13%）──────────────────────────────────────
HAIRLINE = '#12FFFFFF'
HAIRLINE_STRONG = '#22FFFFFF'

# ── 唯一强调色：黄铜，取自胶片齿孔与安全灯 ──────────────────────
ACCENT = '#C8A97E'
ACCENT_STRONG = '#D9BD95'
ACCENT_DIM = '#8E7756'
ACCENT_ON = '#14120E'
DANGER = '#C7705D'

# ── 圆角 ────────────────────────────────────────────────────────
R_SMALL = 7
R_MEDIUM = 11
R_LARGE = 15
R_CONTROL = 6

# ── 布局节奏 ────────────────────────────────────────────────────
SIDEBAR_WIDTH = 360
TOP_BAR_HEIGHT = 48
SECTION_HEADER_HEIGHT = 36
ROW_HEIGHT = 44


def rgba(hex_color: str, alpha: float) -> str:
    """#RRGGBB + 0-1 透明度 → #AARRGGBB（Qt 顺序）。"""
    value = hex_color.lstrip('#')
    a = max(0, min(255, round(alpha * 255)))
    return f'#{a:02X}{value.upper()}'
