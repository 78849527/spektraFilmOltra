from __future__ import annotations

from qtpy import QtCore, QtGui, QtWidgets

QPointF = getattr(QtCore, 'QPointF')
QSize = getattr(QtCore, 'QSize')

from spektrafilm_gui.i18n import translate
from spektrafilm_gui import motion
from spektrafilm_gui.theme_oflim import ACCENT, R_MEDIUM, SECTION_HEADER_HEIGHT, TEXT_2, TEXT_3
from spektrafilm_gui.theme_palette import (
    HEADER_DIVIDER_LINE,
    SIZE_FORM_SPACING,
    SIZE_SECTION_FRAME_MARGIN,
    SIZE_SECTION_STACK_SPACING,
)
from spektrafilm_gui.icons import HEADER_ICON_SIZE, section_header_icon
from spektrafilm_gui.theme import resolve_theme_qcolor


def normalize_ui_text(text: str) -> str:
    """界面文案统一出口：优先出中文，没有词条则退回小写原文。"""
    translated = translate(text)
    if translated is not None:
        return translated
    return text.lower()


def platform_default_font() -> QtGui.QFont:
    return QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.GeneralFont)


def tabular_font(base: QtGui.QFont | None = None) -> QtGui.QFont:
    """等宽数字（tabular-nums）：计数、尺寸串不随数字宽度跳动。"""
    font = QtGui.QFont(base) if base is not None else platform_default_font()
    set_feature = getattr(font, 'setFeature', None)
    if callable(set_feature):
        try:
            set_feature('tnum', 1)
        except (TypeError, ValueError):
            pass
    return font


class WheelSafeSlider(QtWidgets.QSlider):
    """滚轮不改变数值；忽略事件，让它冒泡到外层滚动区域。"""

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API name
        event.ignore()


class DampedScrollArea(QtWidgets.QScrollArea):
    """滚轮阻尼滚动：目标位置指数跟随收敛，接近边界自然缓停。

    只接管滚轮；拖动滚动条仍走原生路径（目标即时同步）。
    """

    NOTCH_PIXELS = 62  # 一格滚轮对应的像素行程

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._target = 0.0
        self._animating = False
        self._follow = motion.FollowValue(self, rate=13.0)
        self._follow.valueChanged.connect(self._on_follow)
        self.viewport().installEventFilter(self)
        bar = self.verticalScrollBar()
        if bar is not None:
            bar.valueChanged.connect(self._on_bar_moved)

    # ── 交互 ────────────────────────────────────────────────────
    def eventFilter(self, obj, event):  # noqa: N802 - Qt API name
        if obj is self.viewport() and event.type() == QtCore.QEvent.Wheel:
            delta = self._wheel_delta(event)
            if delta != 0:
                self._nudge(delta)
                return True
        return super().eventFilter(obj, event)

    @staticmethod
    def _wheel_delta(event) -> int:
        pixel = event.pixelDelta()
        if pixel is not None and pixel.y() != 0:
            return -int(pixel.y())
        angle = event.angleDelta()
        if angle.y() == 0:
            return 0
        return int(round(-angle.y() * (DampedScrollArea.NOTCH_PIXELS / 120.0)))

    def _nudge(self, delta: int) -> None:
        bar = self.verticalScrollBar()
        if bar is None:
            return
        minimum, maximum = bar.minimum(), bar.maximum()
        if maximum <= minimum:
            return
        self._target = float(min(max(self._target + delta, minimum), maximum))
        self._animating = True
        self._follow.move_to(self._target)

    # ── 状态同步 ────────────────────────────────────────────────
    def _on_follow(self, value: float) -> None:
        bar = self.verticalScrollBar()
        if bar is None:
            return
        bar.setValue(int(round(value)))
        if abs(value - self._target) < 0.6:
            self._animating = False

    def _on_bar_moved(self, value: int) -> None:
        if self._animating:
            # 偏离动画轨迹说明用户在拖滚动条：让位给用户
            if abs(value - self._follow.value) > 1.5:
                self._animating = False
                self._target = float(value)
                self._follow.snap_to(value)
            return
        # 拖滚动条 / 布局变化 / 程序滚动：目标即时同步
        self._target = float(value)
        self._follow.snap_to(value)


class Chevron(QtWidgets.QWidget):
    """细折线箭头，展开时指向下，收起时指向右（对齐 oflim 的 8pt chevron）。"""

    def __init__(self, expanded: bool = True):
        super().__init__()
        self._expanded = expanded
        self._hover = False
        self.setFixedSize(10, 10)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

    def set_expanded(self, expanded: bool) -> None:
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self.update()

    def set_hovered(self, hovered: bool) -> None:
        if self._hover == hovered:
            return
        self._hover = hovered
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            color = resolve_theme_qcolor(ACCENT if (self._expanded or self._hover) else TEXT_3)
            pen = QtGui.QPen(color, 1.3, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
            painter.setPen(pen)

            cx = self.width() / 2
            cy = self.height() / 2
            if self._expanded:
                painter.drawLine(QPointF(cx - 2.6, cy - 1.3), QPointF(cx, cy + 1.4))
                painter.drawLine(QPointF(cx, cy + 1.4), QPointF(cx + 2.6, cy - 1.3))
            else:
                painter.drawLine(QPointF(cx - 1.3, cy - 2.6), QPointF(cx + 1.4, cy))
                painter.drawLine(QPointF(cx + 1.4, cy), QPointF(cx - 1.3, cy + 2.6))
        finally:
            painter.end()


class CollapsibleSection(QtWidgets.QWidget):
    """oflim 形态的折叠卡片：圆角卡片 + 发丝描边 + 34px 标题行。"""

    def __init__(self, title: str, content: QtWidgets.QWidget, *, expanded: bool = True):
        super().__init__()
        self._content = content
        self._expanded = expanded

        # 卡片内层容器跟随卡片表面，否则会露出全局 BASE_BG 的黑底
        if content.objectName() == '':
            content.setObjectName('sectionContent')

        self._chevron = Chevron(expanded)

        self._title_label = QtWidgets.QLabel(normalize_ui_text(title))
        self._title_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        title_font = self._title_label.font()
        title_font.setPointSizeF(max(title_font.pointSizeF() - 1.5, 8.0))
        title_font.setWeight(QtGui.QFont.DemiBold)
        title_font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, 0.9)
        self._title_label.setFont(title_font)
        self._title_label.setStyleSheet(f'color: {TEXT_2}; background: transparent;')

        self._icon_label = QtWidgets.QLabel()
        self._icon_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self._icon_label.setAlignment(QtCore.Qt.AlignCenter)
        self._icon_label.setFixedSize(HEADER_ICON_SIZE, HEADER_ICON_SIZE)
        self._apply_header_icon(title)

        header = QtWidgets.QWidget()
        header.setObjectName('sectionHeader')
        header.setFixedHeight(SECTION_HEADER_HEIGHT)
        header.setCursor(QtCore.Qt.PointingHandCursor)
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        header_layout.setSpacing(7)
        header_layout.setAlignment(QtCore.Qt.AlignVCenter)
        header_layout.addWidget(self._chevron, 0, QtCore.Qt.AlignVCenter)
        if not self._icon_label.isHidden():
            header_layout.addWidget(self._icon_label, 0, QtCore.Qt.AlignVCenter)
        header_layout.addWidget(self._title_label, 0, QtCore.Qt.AlignVCenter)
        header_layout.addStretch(1)

        header.installEventFilter(self)
        self._header = header

        body = QtWidgets.QWidget()
        body.setObjectName('sectionCardBody')
        body_layout = QtWidgets.QVBoxLayout(body)
        body_layout.setContentsMargins(12, 0, 12, 10)
        body_layout.setSpacing(0)
        body_layout.setAlignment(QtCore.Qt.AlignTop)
        body_layout.addWidget(self._content)

        self._body = body

        card = QtWidgets.QFrame()
        card.setObjectName('sectionCard')
        self._card = card
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        card_layout.addWidget(header)
        card_layout.addWidget(body)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(int(SIZE_SECTION_STACK_SPACING.removesuffix('px')))
        layout.setAlignment(QtCore.Qt.AlignTop)
        layout.addWidget(card)

        self._set_expanded(expanded)

    # ── 交互 ────────────────────────────────────────────────────
    def eventFilter(self, obj, event):  # noqa: N802 - Qt API name
        header = getattr(self, '_header', None)
        if header is not None and obj is header:
            if event.type() == QtCore.QEvent.MouseButtonRelease and event.button() == QtCore.Qt.LeftButton:
                self.toggle()
                return True
            if event.type() == QtCore.QEvent.Enter:
                self._chevron.set_hovered(True)
            elif event.type() == QtCore.QEvent.Leave:
                self._chevron.set_hovered(False)
        return super().eventFilter(obj, event)

    def toggle(self) -> None:
        self._set_expanded(not self._expanded)

    def is_expanded(self) -> bool:
        return self._expanded

    def _set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._chevron.set_expanded(expanded)
        self._body.setVisible(expanded)

    def set_flat(self, flat: bool = True) -> None:
        """扁平模式：放进 tab 大卡时不重复画卡片背景与描边。"""
        self._card.setObjectName('sectionFlat' if flat else 'sectionCard')
        self._card.style().unpolish(self._card)
        self._card.style().polish(self._card)

    # ── 兼容旧接口 ──────────────────────────────────────────────
    def _apply_header_icon(self, title: str) -> None:
        icon = section_header_icon(title)
        if icon.isNull():
            self._icon_label.hide()
            return

        pixmap = icon.pixmap(HEADER_ICON_SIZE, HEADER_ICON_SIZE)
        if pixmap.isNull():
            self._icon_label.hide()
            return

        self._icon_label.setPixmap(pixmap)
        self._icon_label.show()

    def has_header_icon(self) -> bool:
        pixmap = self._icon_label.pixmap()
        return not self._icon_label.isHidden() and pixmap is not None and not pixmap.isNull()


class HeaderDivider(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

    def sizeHint(self):  # noqa: N802 - Qt API name
        return QSize(48, max(12, self.fontMetrics().height()))

    def minimumSizeHint(self):  # noqa: N802 - Qt API name
        return QSize(12, max(12, self.fontMetrics().height()))

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
            pen = QtGui.QPen(resolve_theme_qcolor(HEADER_DIVIDER_LINE))
            pen.setCosmetic(True)
            painter.setPen(pen)
            y = (self.height() / 2) + 1
            painter.drawLine(QPointF(0, y), QPointF(self.width(), y))
        finally:
            painter.end()
