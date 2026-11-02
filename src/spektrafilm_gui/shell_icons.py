"""壳层图标：全部用 QPainter 画，避免额外图标资源与英文文本。"""

from __future__ import annotations

import math
from functools import lru_cache

from qtpy import QtCore, QtGui

from spektrafilm_gui.theme_oflim import ACCENT, TEXT_2, TEXT_3

Color = QtGui.QColor
Painter = QtGui.QPainter
Pen = QtGui.QPen
Pixmap = QtGui.QPixmap
QIcon = QtGui.QIcon
QPainterPath = QtGui.QPainterPath
Qt = QtCore.Qt
QPointF = QtCore.QPointF
QRectF = QtCore.QRectF


def _pen(color: str | QColor, width: float = 1.6) -> Pen:
    pen = Pen(Color(color), width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


@lru_cache(maxsize=None)
def icon(name: str, color: str = TEXT_2, size: int = 16) -> QIcon:
    ratio = 2
    pixmap = Pixmap(size * ratio, size * ratio)
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)

    painter = Painter(pixmap)
    try:
        painter.setRenderHint(Painter.Antialiasing, True)
        painter.setPen(_pen(color))
        painter.setBrush(Qt.NoBrush)
        _draw(painter, name, float(size))
    finally:
        painter.end()

    return QIcon(pixmap)


@lru_cache(maxsize=None)
def dot(color: str, size: int = 10) -> QIcon:
    ratio = 2
    pixmap = Pixmap(size * ratio, size * ratio)
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)
    painter = Painter(pixmap)
    try:
        painter.setRenderHint(Painter.Antialiasing, True)
        painter.setPen(Pen(Color(color), 1))
        painter.setBrush(Color(color))
        painter.drawEllipse(QRectF(1, 1, size - 2, size - 2))
    finally:
        painter.end()
    return QIcon(pixmap)


def _draw(painter: Painter, name: str, size: float) -> None:
    s = size
    if name == 'back':
        painter.drawLine(QPointF(s * 0.62, s * 0.2), QPointF(s * 0.32, s * 0.5))
        painter.drawLine(QPointF(s * 0.32, s * 0.5), QPointF(s * 0.62, s * 0.8))
    elif name == 'import':
        painter.drawLine(QPointF(s * 0.5, s * 0.12), QPointF(s * 0.5, s * 0.58))
        painter.drawLine(QPointF(s * 0.32, s * 0.4), QPointF(s * 0.5, s * 0.58))
        painter.drawLine(QPointF(s * 0.68, s * 0.4), QPointF(s * 0.5, s * 0.58))
        painter.drawLine(QPointF(s * 0.18, s * 0.72), QPointF(s * 0.18, s * 0.84))
        painter.drawLine(QPointF(s * 0.18, s * 0.84), QPointF(s * 0.82, s * 0.84))
        painter.drawLine(QPointF(s * 0.82, s * 0.84), QPointF(s * 0.82, s * 0.72))
    elif name == 'export':
        painter.drawLine(QPointF(s * 0.5, s * 0.62), QPointF(s * 0.5, s * 0.16))
        painter.drawLine(QPointF(s * 0.32, s * 0.34), QPointF(s * 0.5, s * 0.16))
        painter.drawLine(QPointF(s * 0.68, s * 0.34), QPointF(s * 0.5, s * 0.16))
        painter.drawLine(QPointF(s * 0.18, s * 0.72), QPointF(s * 0.18, s * 0.84))
        painter.drawLine(QPointF(s * 0.18, s * 0.84), QPointF(s * 0.82, s * 0.84))
        painter.drawLine(QPointF(s * 0.82, s * 0.84), QPointF(s * 0.82, s * 0.72))
    elif name == 'folder':
        path = QPainterPath()
        path.moveTo(s * 0.14, s * 0.3)
        path.lineTo(s * 0.14, s * 0.78)
        path.lineTo(s * 0.86, s * 0.78)
        path.lineTo(s * 0.86, s * 0.36)
        path.lineTo(s * 0.48, s * 0.36)
        path.lineTo(s * 0.4, s * 0.26)
        path.lineTo(s * 0.14, s * 0.26)
        path.closeSubpath()
        painter.drawPath(path)
    elif name == 'grid':
        for x in (0.16, 0.54):
            for y in (0.16, 0.54):
                painter.drawRoundedRect(QRectF(s * x, s * y, s * 0.3, s * 0.3), 1.4, 1.4)
    elif name == 'list':
        for y in (0.24, 0.5, 0.76):
            painter.drawEllipse(QPointF(s * 0.22, s * y), 1.1, 1.1)
            painter.drawLine(QPointF(s * 0.36, s * y), QPointF(s * 0.82, s * y))
    elif name in {'star', 'star_filled'}:
        path = QPainterPath()
        center = QPointF(s * 0.5, s * 0.52)
        outer = s * 0.36
        inner = outer * 0.45
        for index in range(10):
            angle = -90.0 + index * 36.0
            radius = outer if index % 2 == 0 else inner
            point = QPointF(
                center.x() + radius * math.cos(math.radians(angle)),
                center.y() + radius * math.sin(math.radians(angle)),
            )
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        path.closeSubpath()
        if name == 'star_filled':
            painter.setBrush(painter.pen().color())
        painter.drawPath(path)
    elif name == 'search':
        painter.drawEllipse(QPointF(s * 0.44, s * 0.44), s * 0.26, s * 0.26)
        painter.drawLine(QPointF(s * 0.64, s * 0.64), QPointF(s * 0.84, s * 0.84))
    elif name == 'plus':
        painter.drawLine(QPointF(s * 0.5, s * 0.24), QPointF(s * 0.5, s * 0.76))
        painter.drawLine(QPointF(s * 0.24, s * 0.5), QPointF(s * 0.76, s * 0.5))
    elif name == 'check':
        painter.drawLine(QPointF(s * 0.24, s * 0.52), QPointF(s * 0.43, s * 0.7))
        painter.drawLine(QPointF(s * 0.43, s * 0.7), QPointF(s * 0.77, s * 0.3))
    elif name == 'chevron_down':
        painter.drawLine(QPointF(s * 0.3, s * 0.42), QPointF(s * 0.5, s * 0.62))
        painter.drawLine(QPointF(s * 0.5, s * 0.62), QPointF(s * 0.7, s * 0.42))
    elif name == 'close':
        painter.drawLine(QPointF(s * 0.28, s * 0.28), QPointF(s * 0.72, s * 0.72))
        painter.drawLine(QPointF(s * 0.72, s * 0.28), QPointF(s * 0.28, s * 0.72))
    elif name == 'rotate_ccw':
        painter.drawArc(QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56), 40 * 16, 280 * 16)
        painter.drawLine(QPointF(s * 0.22, s * 0.2), QPointF(s * 0.24, s * 0.46))
        painter.drawLine(QPointF(s * 0.22, s * 0.2), QPointF(s * 0.46, s * 0.24))
    elif name == 'rotate_cw':
        painter.drawArc(QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56), 220 * 16, 280 * 16)
        painter.drawLine(QPointF(s * 0.78, s * 0.2), QPointF(s * 0.76, s * 0.46))
        painter.drawLine(QPointF(s * 0.78, s * 0.2), QPointF(s * 0.54, s * 0.24))
    elif name == 'fit':
        painter.drawLine(QPointF(s * 0.2, s * 0.4), QPointF(s * 0.2, s * 0.2))
        painter.drawLine(QPointF(s * 0.2, s * 0.2), QPointF(s * 0.4, s * 0.2))
        painter.drawLine(QPointF(s * 0.6, s * 0.2), QPointF(s * 0.8, s * 0.2))
        painter.drawLine(QPointF(s * 0.8, s * 0.2), QPointF(s * 0.8, s * 0.4))
        painter.drawLine(QPointF(s * 0.2, s * 0.6), QPointF(s * 0.2, s * 0.8))
        painter.drawLine(QPointF(s * 0.2, s * 0.8), QPointF(s * 0.4, s * 0.8))
        painter.drawLine(QPointF(s * 0.6, s * 0.8), QPointF(s * 0.8, s * 0.8))
        painter.drawLine(QPointF(s * 0.8, s * 0.8), QPointF(s * 0.8, s * 0.6))
    elif name == 'compare':
        # 原片对比：圆分两半，左半填充表示「原片」
        painter.drawEllipse(QRectF(s * 0.14, s * 0.14, s * 0.72, s * 0.72))
        path = QPainterPath()
        path.moveTo(s * 0.5, s * 0.14)
        path.arcTo(QRectF(s * 0.14, s * 0.14, s * 0.72, s * 0.72), 90, 180)
        path.closeSubpath()
        painter.setBrush(Color(painter.pen().color()))
        painter.drawPath(path)
    elif name == 'dots':
        for x in (0.26, 0.5, 0.74):
            painter.setBrush(Color(color))
            painter.drawEllipse(QPointF(s * x, s * 0.5), 1.3, 1.3)
    elif name == 'film_frame':
        # 空态胶片框：外框 + 两侧齿孔 + 黄铜光圈（唯一的双色图标）
        frame = QRectF(s * 0.16, s * 0.05, s * 0.68, s * 0.9)
        painter.drawRoundedRect(frame, s * 0.06, s * 0.06)
        painter.setBrush(Color(painter.pen().color()))
        hole_w = s * 0.055
        hole_h = s * 0.08
        for index in range(4):
            y = frame.top() + s * 0.13 + index * s * 0.185
            painter.drawRoundedRect(
                QRectF(frame.left() + s * 0.045, y, hole_w, hole_h), hole_w * 0.4, hole_h * 0.4,
            )
            painter.drawRoundedRect(
                QRectF(frame.right() - s * 0.045 - hole_w, y, hole_w, hole_h), hole_w * 0.4, hole_h * 0.4,
            )
        painter.setBrush(Qt.NoBrush)
        painter.setPen(_pen(ACCENT, 1.6))
        cx, cy = frame.center().x(), frame.center().y()
        radius = s * 0.135
        painter.drawEllipse(QPointF(cx, cy), radius, radius)
        painter.setBrush(Color(ACCENT))
        painter.drawEllipse(QPointF(cx, cy), radius * 0.42, radius * 0.42)
    else:
        painter.setPen(_pen(TEXT_3))
        painter.drawEllipse(QRectF(s * 0.2, s * 0.2, s * 0.6, s * 0.6))
