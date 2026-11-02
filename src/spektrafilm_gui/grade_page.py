"""调色台占位页：第二步先打通入口、交接图与返回路径。

真正的调色引擎、LUT/预设栏与导出在第三步接入；这里只负责：
- 显示离开显影台后的标题与当前照片信息
- 展示一份已显影预览，确认交接图确实生成过
- 提供清晰的返回显影台入口
"""

from __future__ import annotations

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

from spektrafilm_gui import shell_icons
from spektrafilm_gui.library_store import LibraryItem
from spektrafilm_gui.theme_oflim import (
    ACCENT,
    HAIRLINE,
    SURFACE_0,
    SURFACE_1,
    SURFACE_2,
    TEXT_1,
    TEXT_2,
    TEXT_3,
    TEXT_4,
    rgba,
)
from spektrafilm_gui.ui_names import film_display_name, paper_display_name
from spektrafilm_gui.widget_primitives import tabular_font

Qt = QtCore.Qt
Signal = QtCore.Signal


def _qimage_from_array(image) -> QtGui.QImage | None:
    if image is None:
        return None
    try:
        array = np.asarray(image)
        if array.ndim != 3 or array.shape[2] < 3:
            return None
        if array.dtype.kind == 'f':
            array = np.clip(array, 0.0, 1.0) * 255.0
        array = np.ascontiguousarray(array[..., :3], dtype=np.uint8)
    except (TypeError, ValueError):
        return None
    height, width = array.shape[:2]
    if width <= 0 or height <= 0:
        return None
    return QtGui.QImage(
        array.data,
        width,
        height,
        width * 3,
        QtGui.QImage.Format_RGB888,
    ).copy()


class GradeTopBar(QtWidgets.QWidget):
    back_requested = Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('gradeTopBar')
        self.setFixedHeight(54)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f'QWidget#gradeTopBar {{ background: {SURFACE_0};'
            f' border-bottom: 1px solid {HAIRLINE}; }}'
        )
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        back = QtWidgets.QPushButton('显影台')
        back.setObjectName('compactBack')
        back.setIcon(shell_icons.icon('back', TEXT_2, 11))
        back.setIconSize(QtCore.QSize(11, 11))
        back.setFixedHeight(28)
        back.setCursor(Qt.PointingHandCursor)
        back.setToolTip('返回显影台')
        back.clicked.connect(self.back_requested.emit)

        self._name = QtWidgets.QLabel('')
        self._name.setObjectName('gradeTitle')
        self._name.setStyleSheet(f'color: {TEXT_1}; font-size: 14px; font-weight: 600;')
        self._meta = QtWidgets.QLabel('')
        self._meta.setObjectName('gradeMeta')
        self._meta.setStyleSheet(f'color: {TEXT_3}; font-size: 11px;')
        self._meta.setFont(tabular_font(self._meta.font()))

        title_box = QtWidgets.QWidget()
        title_layout = QtWidgets.QVBoxLayout(title_box)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(1)
        title_layout.addWidget(self._name)
        title_layout.addWidget(self._meta)

        badge = QtWidgets.QLabel('调色台')
        badge.setStyleSheet(
            f'color: {ACCENT}; font-size: 11px;'
            f' background: {rgba(ACCENT, 0.10)}; border-radius: 7px; padding: 1px 7px;'
        )

        self._export = QtWidgets.QPushButton('导出')
        self._export.setObjectName('exportButton')
        self._export.setFixedHeight(28)
        self._export.setEnabled(False)
        self._export.setToolTip('调色台导出将在第三步接入')
        self._export.setIcon(shell_icons.icon('export', TEXT_3, 12))
        self._export.setIconSize(QtCore.QSize(12, 12))

        layout.addWidget(back, 0, Qt.AlignVCenter)
        layout.addWidget(title_box, 1)
        layout.addWidget(badge, 0, Qt.AlignVCenter)
        layout.addWidget(self._export, 0, Qt.AlignVCenter)

    def set_photo(self, item: LibraryItem) -> None:
        self._name.setText(item.name)
        parts: list[str] = []
        if item.width and item.height:
            parts.append(f'{item.width}×{item.height}')
        if item.film_stock:
            parts.append(film_display_name(item.film_stock))
        if item.print_paper:
            parts.append(paper_display_name(item.print_paper))
        parts.append('16-bit ProPhoto 线性交接图')
        self._meta.setText(' · '.join(parts))


class _FitPreview(QtWidgets.QWidget):
    """等比缩放的预览面；没有图像时显示占位说明。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('gradePreview')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f'QWidget#gradePreview {{ background: {SURFACE_0}; }}')
        self._pixmap = QtGui.QPixmap()
        self._message = '正在读取交接图…'

    def set_image(self, image) -> None:
        qimage = _qimage_from_array(image)
        self._pixmap = QtGui.QPixmap.fromImage(qimage) if qimage is not None else QtGui.QPixmap()
        self._message = '交接图已生成，预览将在第三步接入' if qimage is None else ''
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
            rect = self.rect().adjusted(18, 18, -18, -18)
            if self._pixmap.isNull():
                painter.setPen(QtGui.QColor(TEXT_4))
                painter.drawText(rect, Qt.AlignCenter, self._message)
                return
            scaled = self._pixmap.scaled(
                rect.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            x = rect.left() + (rect.width() - scaled.width()) // 2
            y = rect.top() + (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        finally:
            painter.end()


class _PlaceholderPanel(QtWidgets.QWidget):
    def __init__(self, title: str, message: str, *, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('gradePlaceholderPanel')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f'QWidget#gradePlaceholderPanel {{ background: {SURFACE_1};'
            f' border-left: 1px solid {HAIRLINE}; }}'
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        heading = QtWidgets.QLabel(title)
        heading.setStyleSheet(
            f'color: {TEXT_2}; font-size: 12px; font-weight: 600; letter-spacing: 0.5px;'
        )
        note = QtWidgets.QLabel(message)
        note.setStyleSheet(f'color: {TEXT_4}; font-size: 11px;')
        note.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(note)
        layout.addStretch(1)


class GradePage(QtWidgets.QWidget):
    back_requested = Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('gradePage')
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.top_bar = GradeTopBar()
        root.addWidget(self.top_bar)

        splitter = QtWidgets.QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)

        self.preview = _FitPreview()
        left = _PlaceholderPanel('LUT / 预设', 'LUT 与预设将在第三步接入。')
        right = _PlaceholderPanel(
            '调色参数',
            '曝光、曲线、色彩混合、颜色分级与细节将在第三步接入。',
        )
        left.setFixedWidth(240)
        right.setFixedWidth(300)
        splitter.addWidget(left)
        splitter.addWidget(self.preview)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        root.addWidget(splitter, 1)

        self.top_bar.back_requested.connect(self.back_requested.emit)

    def set_photo(self, item: LibraryItem) -> None:
        self.top_bar.set_photo(item)

    def set_preview(self, image) -> None:
        self.preview.set_image(image)


__all__ = ['GradePage', 'GradeTopBar']
