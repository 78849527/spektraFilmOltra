"""照片库主页：Finder 式的照片管理页。

只做展示与收藏/筛选/导入入口；打开照片、载入显影由上层协调器负责。
视觉规范集中在 theme_library，本文件只负责组件结构与状态。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from qtpy import QtCore, QtGui, QtWidgets

from spektrafilm_gui import motion, shell_icons
from spektrafilm_gui.handoff import has_grade_recipe
from spektrafilm_gui.library_store import (
    COLOR_LABEL_NAMES,
    COLOR_LABELS,
    LibraryItem,
    LibraryStore,
    is_supported_image,
)
from spektrafilm_gui.library_thumbs import ThumbnailService, format_file_size
from spektrafilm_gui.persistence import load_dialog_dir, save_dialog_dir
from spektrafilm_gui.theme_library import (
    CARD_GAP_X,
    CARD_GAP_Y,
    CARD_MAX_WIDTH,
    CARD_MIN_WIDTH,
    CARD_RADIUS,
    CARD_TEXT_GAP,
    CARD_TEXT_STACK,
    COLOR_TONES,
    LIST_ROW_HEIGHT,
    LIST_THUMB_HEIGHT,
    LIST_THUMB_WIDTH,
    META_HEIGHT,
    NAME_HEIGHT,
    PAGE_MARGIN_BOTTOM,
    PAGE_MARGIN_X,
    PAGE_MARGIN_TOP,
    THUMB_ASPECT,
)
from spektrafilm_gui.theme_oflim import (
    ACCENT,
    ACCENT_ON,
    CONTROL_HEIGHT,
    CONTROL_HEIGHT_SMALL,
    SURFACE_1,
    SURFACE_2,
    SURFACE_3,
    TEXT_1,
    TEXT_2,
    TEXT_3,
    rgba,
)
from spektrafilm_gui.ui_names import film_display_name, paper_display_name
from spektrafilm_gui.widget_primitives import tabular_font

QAction = QtGui.QAction
QColor = QtGui.QColor
QCursor = QtGui.QCursor
QDesktopServices = QtGui.QDesktopServices
QFileDialog = QtWidgets.QFileDialog
QFontMetrics = QtGui.QFontMetrics
QFrame = QtWidgets.QFrame
QHBoxLayout = QtWidgets.QHBoxLayout
QLabel = QtWidgets.QLabel
QLineEdit = QtWidgets.QLineEdit
QMenu = QtWidgets.QMenu
QMessageBox = QtWidgets.QMessageBox
QPainter = QtGui.QPainter
QPainterPath = QtGui.QPainterPath
QPushButton = QtWidgets.QPushButton
QRectF = QtCore.QRectF
QScrollArea = QtWidgets.QScrollArea
QSize = QtCore.QSize
QSizePolicy = QtWidgets.QSizePolicy
QStackedWidget = QtWidgets.QStackedWidget
QTimer = QtCore.QTimer
QUrl = QtCore.QUrl
QVBoxLayout = QtWidgets.QVBoxLayout
QWidget = QtWidgets.QWidget
Qt = QtCore.Qt
Signal = QtCore.Signal

COLOR_HEX = COLOR_TONES

_IMAGE_FILTER = (
    '图片文件 ('
    '*.cr2 *.cr3 *.nef *.arw *.dng *.raf *.orf *.rw2 *.pef *.srw *.3fr *.iiq '
    '*.x3f *.erf *.mef *.mos *.mrw *.nrw *.rwl *.srf *.sr2 '
    '*.tif *.tiff *.png *.jpg *.jpeg *.bmp *.webp *.exr *.hdr'
    ')'
)


class ElidedLabel(QLabel):
    def __init__(self, text: str = '', parent: QWidget | None = None):
        super().__init__(parent)
        self._full_text = ''
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API name
        self._full_text = text
        self.setToolTip(text)
        self._update_elided()

    def full_text(self) -> str:
        return self._full_text

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        hint = super().minimumSizeHint()
        return QSize(0, hint.height())

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        hint = super().sizeHint()
        return QSize(min(hint.width(), 520), hint.height())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._update_elided()

    def _update_elided(self) -> None:
        width = max(self.width(), 10)
        elided = QFontMetrics(self.font()).elidedText(self._full_text, Qt.ElideMiddle, width)
        super().setText(elided)


class ThumbnailView(QWidget):
    """4:3 缩略面：横构图居中裁切，竖构图模糊延展，带悬浮/选中状态。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        radius: float = CARD_RADIUS,
        hover_mode: str = 'none',
        folder: bool = False,
    ):
        super().__init__(parent)
        self._image: QtGui.QImage | None = None
        self._missing = False
        self._raw = False
        self._error = False
        self._radius = float(radius)
        self._hover_mode = hover_mode
        self._hovered = False
        self._selected = False
        self._folder = folder

    # ── 状态 ────────────────────────────────────────────────────
    def set_image(self, image: QtGui.QImage | None) -> None:
        self._image = image
        self._error = False
        self.update()

    def set_missing(self, missing: bool) -> None:
        self._missing = missing
        self.update()

    def set_raw(self, raw: bool) -> None:
        self._raw = raw
        self.update()

    def set_error(self, error: bool) -> None:
        self._error = error
        self.update()

    def set_hovered(self, hovered: bool) -> None:
        if self._hovered == hovered:
            return
        self._hovered = hovered
        self.update()

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._hover_mode == 'self':
            self.set_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._hover_mode == 'self':
            self.set_hovered(False)
        super().leaveEvent(event)

    # ── 绘制 ────────────────────────────────────────────────────
    def _rounded_path(self) -> QPainterPath:
        width = max(1, self.width())
        height = max(1, self.height())
        radius = max(2.0, min(self._radius, min(width, height) / 3.0))
        rect = QRectF(0.5, 0.5, max(1.0, width - 1.0), max(1.0, height - 1.0))
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            path = self._rounded_path()
            painter.setClipPath(path)

            if self._folder:
                self._paint_folder(painter)
            elif self._image is not None and not self._image.isNull():
                self._paint_image(painter)
            else:
                self._paint_placeholder(painter, path)

            if self._hovered and not self._selected:
                painter.fillRect(self.rect(), QColor(255, 255, 255, 5))

            painter.setClipping(False)
            if self._selected:
                pen = QtGui.QPen(QColor(ACCENT), 1.6)
            elif self._hovered:
                pen = QtGui.QPen(QColor(255, 255, 255, 42), 1.0)
            else:
                pen = QtGui.QPen(QColor(255, 255, 255, 16), 1.0)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

            if self._missing or self._error:
                painter.fillPath(path, QColor(0, 0, 0, 155))
                font = QtGui.QFont(self.font())
                font.setPixelSize(11)
                painter.setFont(font)
                painter.setPen(QColor(TEXT_2))
                painter.drawText(
                    self.rect(),
                    Qt.AlignCenter,
                    '文件已移动' if self._missing else '无法预览',
                )
        finally:
            painter.end()

    def _paint_image(self, painter: QPainter) -> None:
        image = self._image
        assert image is not None
        width = max(1, self.width())
        height = max(1, self.height())
        target_ratio = width / max(1.0, float(height))
        image_ratio = image.width() / max(1.0, float(image.height()))

        if image_ratio >= target_ratio:
            # 横构图：按目标比例从源图直接裁切绘制，避免二次重采样
            crop_width = image.height() * target_ratio
            crop_x = (image.width() - crop_width) / 2.0
            painter.drawImage(
                QRectF(0.0, 0.0, width, height),
                image,
                QRectF(crop_x, 0.0, crop_width, float(image.height())),
            )
            return

        # 竖构图：低分辨率铺底放大成模糊延展，主体完整居中显示
        cover = image.scaled(24, 24, Qt.KeepAspectRatioByExpanding, Qt.FastTransformation)
        painter.drawImage(self.rect(), cover)

        scale = min(width / image.width(), height / image.height())
        fit_width = image.width() * scale
        fit_height = image.height() * scale
        painter.drawImage(
            QRectF((width - fit_width) / 2.0, (height - fit_height) / 2.0, fit_width, fit_height),
            image,
            QRectF(image.rect()),
        )

    def _paint_folder(self, painter: QPainter) -> None:
        painter.fillRect(self.rect(), QColor(SURFACE_3 if self._hovered else SURFACE_2))
        icon_size = max(30, min(56, round(min(self.width(), self.height()) * 0.30)))
        icon_color = ACCENT if self._selected else (TEXT_2 if self._hovered else TEXT_3)
        pixmap = shell_icons.icon('folder', icon_color, icon_size).pixmap(icon_size, icon_size)
        painter.drawPixmap(
            QtCore.QPointF(
                (self.width() - icon_size) / 2.0,
                (self.height() - icon_size) / 2.0,
            ),
            pixmap,
        )

    def _paint_placeholder(self, painter: QPainter, path: QPainterPath) -> None:
        painter.fillPath(path, QColor(SURFACE_1))
        painter.setPen(QtGui.QPen(QColor(255, 255, 255, 26), 1.2))
        cx, cy = self.width() / 2.0, self.height() / 2.0
        frame = QRectF(cx - 22, cy - 17, 44, 34)
        painter.drawRoundedRect(frame, 5, 5)
        painter.drawLine(QtCore.QPointF(cx - 13, cy + 8), QtCore.QPointF(cx - 4, cy - 2))
        painter.drawLine(QtCore.QPointF(cx - 4, cy - 2), QtCore.QPointF(cx + 3, cy + 5))
        painter.drawLine(QtCore.QPointF(cx + 1, cy + 3), QtCore.QPointF(cx + 8, cy - 5))
        painter.drawLine(QtCore.QPointF(cx + 8, cy - 5), QtCore.QPointF(cx + 14, cy + 1))

        if self._raw:
            font = QtGui.QFont(self.font())
            font.setPixelSize(10)
            font.setWeight(QtGui.QFont.DemiBold)
            painter.setFont(font)
            painter.setPen(QColor(TEXT_3))
            painter.drawText(
                QRectF(0, self.height() - 22, self.width(), 16),
                Qt.AlignHCenter | Qt.AlignVCenter,
                'RAW',
            )


class StarButton(QPushButton):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('starButton')
        self.setCheckable(True)
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip('收藏')
        self.setIconSize(QSize(13, 13))
        self.toggled.connect(self._refresh_icon)
        self._refresh_icon(False)

    def _refresh_icon(self, checked: bool) -> None:
        self.setIcon(
            shell_icons.icon('star_filled' if checked else 'star', ACCENT if checked else TEXT_2, 13)
        )


class MoreButton(QPushButton):
    """更多操作：与收藏、颜色标签同一尺寸的悬浮按钮。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('moreButton')
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip('更多操作')
        self.setIcon(shell_icons.icon('dots', TEXT_2, 14))
        self.setIconSize(QSize(14, 14))


class ColorDotButton(QPushButton):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('colorButton')
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip('颜色标签')
        self._color = ''
        self.clicked.connect(self._show_menu)

    color_selected = Signal(str)

    def set_color(self, color: str) -> None:
        color = color if color in COLOR_LABELS else ''
        if color == self._color:
            return
        self._color = color
        self.update()

    def _show_menu(self) -> None:
        menu = QMenu(self)
        clear = menu.addAction('无标签')
        clear.setCheckable(True)
        clear.setChecked(not self._color)
        actions = {'': clear}
        for color in COLOR_LABELS:
            action = menu.addAction(COLOR_LABEL_NAMES[color])
            action.setCheckable(True)
            action.setChecked(self._color == color)
            action.setIcon(shell_icons.dot(COLOR_HEX[color], 10))
            actions[color] = action
        chosen = menu.exec(self.mapToGlobal(self.rect().bottomLeft()))
        if chosen is None:
            return
        for color, action in actions.items():
            if action is chosen:
                self.color_selected.emit(color)
                return

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().paintEvent(event)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(Qt.NoPen)
            if self._color:
                painter.setBrush(QColor(COLOR_HEX[self._color]))
                painter.drawEllipse(QRectF(6, 6, 10, 10))
            else:
                pen = QtGui.QPen(QColor(TEXT_2), 1.2)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QRectF(6.5, 6.5, 9, 9))
        finally:
            painter.end()


class _BasePhotoCard(QFrame):
    """照片卡公共部分：缩略面 + 悬浮操作 + 选中状态。"""

    opened = Signal(str)
    favorite_requested = Signal(str, bool)
    color_requested = Signal(str, str)
    remove_requested = Signal(str)

    _controls_always_visible = False

    def __init__(self, item: LibraryItem, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('photoCard')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty('hover', 'false')
        self.item = item
        self._selected = False
        self._hovered = False
        self._controls_target = False
        self._controls_anim = None

        self._thumb = ThumbnailView(hover_mode='external')
        self._thumb.set_raw(item.is_raw)
        self._thumb.set_missing(not item.exists)
        self._grade_badge = QLabel('已调色', self._thumb)
        self._grade_badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._grade_badge.setStyleSheet(
            f'QLabel {{ color: {ACCENT}; background: {rgba("#000000", 0.62)};'
            f' border: 1px solid {rgba(ACCENT, 0.45)}; border-radius: 5px;'
            f' padding: 1px 6px; font-size: 10px; font-weight: 600; }}'
        )
        self._grade_badge.adjustSize()
        self._grade_badge.move(10, 10)
        self._refresh_grade_badge()

        self.star = StarButton()
        self.star.blockSignals(True)
        self.star.setChecked(item.favorite)
        self.star.blockSignals(False)

        self.color_button = ColorDotButton()
        self.color_button.set_color(item.color)
        self.more_button = MoreButton()

        self._controls = QWidget(self)
        self._controls.setAttribute(Qt.WA_TranslucentBackground, True)
        controls_layout = QHBoxLayout(self._controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(4)
        controls_layout.addWidget(self.color_button)
        controls_layout.addWidget(self.star)
        controls_layout.addWidget(self.more_button)
        self._controls.setFixedSize(74, 22)
        self._controls.hide()

        if not self._controls_always_visible:
            effect = QtWidgets.QGraphicsOpacityEffect(self._controls)
            effect.setOpacity(0.0)
            self._controls.setGraphicsEffect(effect)

        self._hover_check = QTimer(self)
        self._hover_check.setSingleShot(True)
        self._hover_check.setInterval(0)
        self._hover_check.timeout.connect(self._sync_hover)

        self.star.toggled.connect(
            lambda checked: self.favorite_requested.emit(self.item.id, bool(checked))
        )
        self.color_button.color_selected.connect(
            lambda color: self.color_requested.emit(self.item.id, color)
        )
        self.more_button.clicked.connect(self._show_context_menu)

    def _show_context_menu(self) -> None:
        self._context_menu(
            self.more_button.mapToGlobal(QtCore.QPoint(0, self.more_button.height() + 4))
        )

    # ── 状态 ────────────────────────────────────────────────────
    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self.setProperty('selected', 'true' if selected else 'false')
        self._thumb.set_selected(selected)
        self._refresh_controls(animate=False)
        self._repolish()

    def update_item(self, item: LibraryItem) -> None:
        self.item = item
        self._thumb.set_missing(not item.exists)
        self._thumb.set_raw(item.is_raw)
        self._refresh_grade_badge()
        self.star.blockSignals(True)
        self.star.setChecked(item.favorite)
        self.star.blockSignals(False)
        self.star._refresh_icon(item.favorite)
        self.color_button.set_color(item.color)
        self._name.setText(item.name)
        self._meta.setText(self._meta_text())
        self._refresh_controls(animate=False)

    def _refresh_grade_badge(self) -> None:
        self._grade_badge.setVisible(has_grade_recipe(self.item.state))

    def _meta_text(self) -> str:
        parts: list[str] = []
        if self.item.film_stock:
            parts.append(film_display_name(self.item.film_stock))
        elif self.item.adjusted:
            parts.append('已调整')
        if self.item.width and self.item.height:
            parts.append(f'{self.item.width}×{self.item.height}')
        elif self.item.file_size:
            parts.append(format_file_size(self.item.file_size))
        if self.item.is_raw and 'RAW' not in parts:
            parts.insert(0, 'RAW')
        return ' · '.join(parts) or (
            'RAW' if self.item.is_raw else self.item.suffix.lstrip('.').upper()
        )

    # ── 悬浮 ────────────────────────────────────────────────────
    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().enterEvent(event)
        self._set_hovered(True)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().leaveEvent(event)
        self._hover_check.start()

    def _sync_hover(self) -> None:
        try:
            inside = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
        except (RuntimeError, TypeError):
            return
        self._set_hovered(inside)

    def _set_hovered(self, hovered: bool) -> None:
        if self._hovered == hovered:
            return
        self._hovered = hovered
        self.setProperty('hover', 'true' if hovered else 'false')
        self._thumb.set_hovered(hovered)
        self._refresh_controls(animate=True)
        self._repolish()

    def _refresh_controls(self, *, animate: bool) -> None:
        should_show = (
            self._controls_always_visible
            or self._hovered
            or self._selected
            or self.item.favorite
            or bool(self.item.color)
        )
        if self._controls_target == should_show and self._controls.isHidden() != should_show:
            return
        self._controls_target = should_show

        if self._controls_always_visible:
            self._controls.setVisible(should_show)
            return

        effect = self._controls.graphicsEffect()
        if not isinstance(effect, QtWidgets.QGraphicsOpacityEffect):
            effect = QtWidgets.QGraphicsOpacityEffect(self._controls)
            self._controls.setGraphicsEffect(effect)
        if self._controls_anim is not None:
            self._controls_anim.stop()
            self._controls_anim = None

        start = effect.opacity()
        target = 1.0 if should_show else 0.0
        if should_show:
            self._controls.show()
        if not animate or abs(start - target) < 0.01:
            effect.setOpacity(target)
            if not should_show:
                self._controls.hide()
            return

        def _frame(progress: float) -> None:
            effect.setOpacity(start + (target - start) * progress)

        def _done() -> None:
            if not should_show:
                self._controls.hide()

        self._controls_anim = motion.animate_progress(
            self._controls,
            _frame,
            duration=140 if should_show else 110,
            curve=QtCore.QEasingCurve.Type.OutCubic,
            on_finished=_done,
        )

    def _repolish(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    # ── 交互 ────────────────────────────────────────────────────
    def _context_menu(self, position) -> None:
        menu = QMenu(self)
        open_action = menu.addAction('打开')
        menu.addSeparator()
        favorite_action = menu.addAction('取消收藏' if self.item.favorite else '收藏')
        color_menu = menu.addMenu('颜色标签')
        color_actions = {}
        clear_action = color_menu.addAction('无标签')
        clear_action.setCheckable(True)
        clear_action.setChecked(not self.item.color)
        color_actions[''] = clear_action
        for color in COLOR_LABELS:
            action = color_menu.addAction(COLOR_LABEL_NAMES[color])
            action.setCheckable(True)
            action.setChecked(self.item.color == color)
            action.setIcon(shell_icons.dot(COLOR_HEX[color], 10))
            color_actions[color] = action
        menu.addSeparator()
        reveal_action = menu.addAction('在访达中显示')
        reveal_action.setEnabled(self.item.exists)
        menu.addSeparator()
        remove_action = menu.addAction('从库中移出')

        chosen = menu.exec(position)
        if chosen is None:
            return
        if chosen is open_action:
            self.opened.emit(self.item.id)
        elif chosen is favorite_action:
            self.favorite_requested.emit(self.item.id, not self.item.favorite)
        elif chosen is reveal_action:
            _reveal_in_file_manager(self.item.path)
        elif chosen is remove_action:
            self.remove_requested.emit(self.item.id)
        else:
            for color, action in color_actions.items():
                if action is chosen:
                    self.color_requested.emit(self.item.id, color)
                    return

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.LeftButton:
            self.opened.emit(self.item.id)
            event.accept()
            return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._context_menu(event.globalPos())
        event.accept()


class PhotoCard(_BasePhotoCard):
    """网格卡：4:3 缩略面是主体，文件名与参数在下，操作悬浮出现。"""

    def __init__(self, item: LibraryItem, parent: QWidget | None = None):
        super().__init__(item, parent)
        self.setCursor(Qt.PointingHandCursor)
        self._card_size = (0, 0)

        self._name = ElidedLabel(item.name)
        self._name.setObjectName('photoName')
        self._name.setFixedHeight(NAME_HEIGHT)
        self._meta = ElidedLabel(self._meta_text())
        self._meta.setObjectName('photoMeta')
        self._meta.setFont(tabular_font(self._meta.font()))
        self._meta.setFixedHeight(META_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._thumb)
        layout.addSpacing(CARD_TEXT_GAP)
        layout.addWidget(self._name)
        layout.addSpacing(3)
        layout.addWidget(self._meta)

        self.set_card_width(CARD_MIN_WIDTH)
        self._controls.raise_()
        self._refresh_controls(animate=False)

    def set_card_width(self, width: int) -> None:
        width = max(CARD_MIN_WIDTH, int(width))
        thumb_height = max(1, round(width * THUMB_ASPECT))
        if (width, thumb_height) == self._card_size:
            return
        self._card_size = (width, thumb_height)
        self._thumb.setFixedSize(width, thumb_height)
        self._name.setFixedWidth(width)
        self._meta.setFixedWidth(width)
        self.setFixedSize(width, thumb_height + CARD_TEXT_STACK)
        self._controls.move(width - self._controls.width() - 7, 7)

    def set_thumbnail(self, image: QtGui.QImage) -> None:
        self._thumb.set_image(image)
        self._thumb.set_missing(False)

    def set_thumbnail_error(self) -> None:
        self._thumb.set_error(True)


class PhotoRow(_BasePhotoCard):
    """列表行：缩略图 + 文件信息 + 常驻操作，悬停整行提亮。"""

    _controls_always_visible = True

    def __init__(self, item: LibraryItem, parent: QWidget | None = None):
        super().__init__(item, parent)
        self.setObjectName('photoRow')
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(LIST_ROW_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._thumb.setFixedSize(LIST_THUMB_WIDTH, LIST_THUMB_HEIGHT)

        self._name = ElidedLabel(item.name)
        self._name.setObjectName('photoName')
        self._meta = ElidedLabel(self._meta_text())
        self._meta.setObjectName('photoMeta')
        self._meta.setFont(tabular_font(self._meta.font()))

        text_widget = QWidget()
        text_widget.setObjectName('photoText')
        text_box = QVBoxLayout(text_widget)
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(2)
        text_box.addWidget(self._name)
        text_box.addWidget(self._meta)
        text_box.addStretch(1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 10, 2)
        layout.setSpacing(12)
        layout.addWidget(self._thumb, 0, Qt.AlignVCenter)
        layout.addWidget(text_widget, 1, Qt.AlignVCenter)
        layout.addWidget(self._controls, 0, Qt.AlignVCenter)
        self._controls.show()
        self._refresh_controls(animate=False)

    def set_thumbnail(self, image: QtGui.QImage) -> None:
        self._thumb.set_image(image)
        self._thumb.set_missing(False)

    def set_thumbnail_error(self) -> None:
        self._thumb.set_error(True)


class FolderCard(QFrame):
    """文件夹卡：与照片卡同一套 4:3 卡片语言，混排在同一个网格里。"""

    clicked = Signal(str)

    def __init__(self, folder_id: str, name: str, count: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.folder_id = folder_id
        self.setObjectName('photoCard')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self._selected = False
        self._card_size = (0, 0)

        self._thumb = ThumbnailView(hover_mode='self', folder=True)

        self._name = ElidedLabel(name)
        self._name.setObjectName('photoName')
        self._name.setFixedHeight(NAME_HEIGHT)
        self._meta = ElidedLabel(f'{count} 张照片')
        self._meta.setObjectName('photoMeta')
        self._meta.setFont(tabular_font(self._meta.font()))
        self._meta.setFixedHeight(META_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._thumb)
        layout.addSpacing(CARD_TEXT_GAP)
        layout.addWidget(self._name)
        layout.addSpacing(3)
        layout.addWidget(self._meta)

        self.set_card_width(CARD_MIN_WIDTH)

    def set_card_width(self, width: int) -> None:
        width = max(CARD_MIN_WIDTH, int(width))
        thumb_height = max(1, round(width * THUMB_ASPECT))
        if (width, thumb_height) == self._card_size:
            return
        self._card_size = (width, thumb_height)
        self._thumb.setFixedSize(width, thumb_height)
        self._name.setFixedWidth(width)
        self._meta.setFixedWidth(width)
        self.setFixedSize(width, thumb_height + CARD_TEXT_STACK)

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self.setProperty('selected', 'true' if selected else 'false')
        self._thumb.set_selected(selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.folder_id)
            event.accept()
            return
        super().mousePressEvent(event)


class ResponsiveGrid(QWidget):
    """自适应网格：列数与卡片宽度都由可用宽度算出，卡片永远填满一行。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('photoGrid')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._cards: list[QWidget] = []
        self._columns = 0
        self._card_width = 0
        self._layout = QtWidgets.QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(CARD_GAP_X)
        self._layout.setVerticalSpacing(CARD_GAP_Y)
        self._layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._relayout_timer = QTimer(self)
        self._relayout_timer.setSingleShot(True)
        self._relayout_timer.setInterval(40)
        self._relayout_timer.timeout.connect(self._relayout)

    def set_cards(self, cards: list[QWidget]) -> None:
        for card in self._cards:
            card.setParent(None)
        self._cards = list(cards)
        for card in self._cards:
            card.setParent(self)
        self._columns = 0
        self._card_width = 0
        self._relayout(force=True)

    def _available_width(self) -> int:
        width = self.width()
        if width < CARD_MIN_WIDTH and self.parentWidget() is not None:
            width = max(self.parentWidget().width() - PAGE_MARGIN_X * 2, CARD_MIN_WIDTH)
        return max(width, CARD_MIN_WIDTH)

    def metrics(self) -> tuple[int, int]:
        width = self._available_width()
        columns = max(1, int((width + CARD_GAP_X) // (CARD_MIN_WIDTH + CARD_GAP_X)))
        card_width = int((width - (columns - 1) * CARD_GAP_X) / columns)
        card_width = max(CARD_MIN_WIDTH, min(CARD_MAX_WIDTH, card_width))
        return columns, card_width

    def _relayout(self, *, force: bool = False) -> None:
        columns, card_width = self.metrics()
        if not force and (columns, card_width) == (self._columns, self._card_width):
            return
        self._columns = columns
        self._card_width = card_width

        while self._layout.count():
            layout_item = self._layout.takeAt(0)
            if layout_item is not None:
                widget = layout_item.widget()
                if widget is not None:
                    widget.setParent(self)

        for card in self._cards:
            resize_card = getattr(card, 'set_card_width', None)
            if callable(resize_card):
                resize_card(card_width)
        for index, card in enumerate(self._cards):
            row, column = divmod(index, columns)
            self._layout.addWidget(card, row, column, Qt.AlignLeft | Qt.AlignTop)
        for column in range(self._layout.columnCount()):
            self._layout.setColumnStretch(column, 0)
        self._layout.setColumnStretch(columns, 1)
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._relayout_timer.start()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        columns = max(1, self._columns or self.metrics()[0])
        rows = max(1, (len(self._cards) + columns - 1) // columns)
        card_width = self._card_width or CARD_MIN_WIDTH
        card_height = round(card_width * THUMB_ASPECT) + CARD_TEXT_STACK
        return QSize(
            columns * card_width + max(0, columns - 1) * CARD_GAP_X,
            rows * card_height + max(0, rows - 1) * CARD_GAP_Y,
        )

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        # 宽度可以缩到一列，但高度必须容得下当前所有行，否则行会被压扁重叠
        return QSize(CARD_MIN_WIDTH, self.sizeHint().height())


class SortControl(QPushButton):
    """排序控件：与搜索、视图切换同一套 30px 控件语言，自带右侧雪佛龙。"""

    currentIndexChanged = Signal(int)
    ENTRIES = (
        ('最近导入', 'recent'),
        ('文件名', 'name'),
        ('收藏优先', 'favorite'),
    )

    def __init__(self, parent: QWidget | None = None):
        super().__init__(self.ENTRIES[0][0], parent)
        self.setObjectName('librarySort')
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(112, CONTROL_HEIGHT)
        self._index = 0
        self._menu = QMenu(self)
        self._actions: list[QAction] = []
        for index, (label, _data) in enumerate(self.ENTRIES):
            action = self._menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(index == 0)
            action.triggered.connect(lambda _checked=False, i=index: self.set_current_index(i))
            self._actions.append(action)
        self.clicked.connect(self._popup_menu)

    def currentIndex(self) -> int:  # noqa: N802 - Qt API name
        return self._index

    def currentData(self):  # noqa: N802 - Qt API name
        return self.ENTRIES[self._index][1]

    def set_current_index(self, index: int) -> None:
        if index == self._index:
            return
        self._index = index
        self.setText(self.ENTRIES[index][0])
        for action_index, action in enumerate(self._actions):
            action.setChecked(action_index == index)
        self.currentIndexChanged.emit(index)

    def _popup_menu(self) -> None:
        self._menu.setMinimumWidth(self.width())
        self._menu.exec(self.mapToGlobal(QtCore.QPoint(0, self.height() + 4)))

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().paintEvent(event)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            pen = QtGui.QPen(QColor(TEXT_3), 1.3)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            cx = self.width() - 13.0
            cy = self.height() / 2.0 - 1.0
            painter.drawLine(QtCore.QPointF(cx - 3.5, cy - 1.5), QtCore.QPointF(cx, cy + 2.0))
            painter.drawLine(QtCore.QPointF(cx, cy + 2.0), QtCore.QPointF(cx + 3.5, cy - 1.5))
        finally:
            painter.end()


class LibraryPage(QWidget):
    import_photos_requested = Signal()
    open_item_requested = Signal(str)
    photos_imported = Signal(list)
    status_message = Signal(str)

    def __init__(
        self,
        store: LibraryStore,
        *,
        thumbnails: ThumbnailService | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName('libraryPage')
        self.store = store
        self.thumbnails = thumbnails or ThumbnailService(store, parent=self)
        self._filter_mode = 'all'
        self._folder_filter = ''
        self._search_text = ''
        self._sort_mode = 'recent'
        self._view_mode = 'grid'
        self._selected_id = ''
        self._cards: dict[str, _BasePhotoCard] = {}
        self._folder_cards: dict[str, FolderCard] = {}
        self._visible_limit = 240
        self._visible_total = 0
        self._thumb_refresh_timer = QTimer(self)
        self._thumb_refresh_timer.setSingleShot(True)
        self._thumb_refresh_timer.setInterval(150)
        self._thumb_refresh_timer.timeout.connect(self.refresh)
        self._meta_save_timer = QTimer(self)
        self._meta_save_timer.setSingleShot(True)
        self._meta_save_timer.setInterval(1200)
        self._meta_save_timer.timeout.connect(self.store.save)
        self._build_ui()
        self._connect_thumbnails()
        self.import_photos_requested.connect(self.import_photos)
        self.setAcceptDrops(True)
        self.refresh()

    # ── 构建 ────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setObjectName('libraryScroll')
        scroll.viewport().setAutoFillBackground(False)
        body = QWidget()
        body.setObjectName('libraryBody')
        body.setAutoFillBackground(False)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(
            PAGE_MARGIN_X,
            PAGE_MARGIN_TOP,
            PAGE_MARGIN_X,
            PAGE_MARGIN_BOTTOM,
        )
        body_layout.setSpacing(10)
        body_layout.addLayout(self._build_section_head())
        self._content_stack = QStackedWidget()
        self._content_stack.setObjectName('libraryContent')
        self._content_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._grid = ResponsiveGrid()
        self._list_container = QWidget()
        self._list_container.setObjectName('listBody')
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.setAlignment(Qt.AlignTop)
        self._empty = self._build_empty_state()
        self._content_stack.addWidget(self._grid)
        self._content_stack.addWidget(self._list_container)
        self._content_stack.addWidget(self._empty)
        body_layout.addWidget(self._content_stack, 1)
        self._more_button = QPushButton('')
        self._more_button.setObjectName('moreAction')
        self._more_button.setCursor(Qt.PointingHandCursor)
        self._more_button.setFixedHeight(32)
        self._more_button.setMaximumWidth(240)
        self._more_button.hide()
        self._more_button.clicked.connect(self._show_more)
        body_layout.addWidget(self._more_button, 0, Qt.AlignHCenter)
        body_layout.addStretch(0)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def _build_header(self) -> QWidget:
        """管理面板：标题行 + 筛选/搜索/视图行，下面就是文件显示区。"""
        header = QWidget()
        header.setObjectName('libraryHeader')
        header.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(header)
        layout.setContentsMargins(PAGE_MARGIN_X, 16, PAGE_MARGIN_X, 13)
        layout.setSpacing(11)

        self._title = QLabel('照片库')
        self._title.setObjectName('libraryTitle')
        self._subtitle = QLabel('')
        self._subtitle.setObjectName('librarySubtitle')
        self._subtitle.setFont(tabular_font(self._subtitle.font()))

        self._import_photos_button = QPushButton('导入照片')
        self._import_photos_button.setObjectName('primaryAction')
        self._import_photos_button.setCursor(Qt.PointingHandCursor)
        self._import_photos_button.setFixedHeight(CONTROL_HEIGHT)
        self._import_photos_button.setIcon(shell_icons.icon('import', ACCENT_ON, 14))
        self._import_photos_button.setIconSize(QSize(14, 14))
        self._import_photos_button.clicked.connect(self.import_photos_requested.emit)

        self._import_folder_button = QPushButton('导入文件夹')
        self._import_folder_button.setObjectName('secondaryAction')
        self._import_folder_button.setCursor(Qt.PointingHandCursor)
        self._import_folder_button.setFixedHeight(CONTROL_HEIGHT)
        self._import_folder_button.setIcon(shell_icons.icon('folder', TEXT_3, 14))
        self._import_folder_button.setIconSize(QSize(14, 14))
        self._import_folder_button.clicked.connect(self._choose_folder)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        title_row.addWidget(self._title, 0, Qt.AlignVCenter)
        title_row.addWidget(self._subtitle, 0, Qt.AlignBaseline)
        title_row.addStretch(1)
        title_row.addWidget(self._import_folder_button, 0, Qt.AlignVCenter)
        title_row.addWidget(self._import_photos_button, 0, Qt.AlignVCenter)
        layout.addLayout(title_row)

        control_row = QHBoxLayout()
        control_row.setContentsMargins(0, 0, 0, 0)
        control_row.setSpacing(10)
        control_row.addLayout(self._build_chips())
        control_row.addStretch(1)
        control_row.addWidget(self._build_search(), 0, Qt.AlignVCenter)
        control_row.addWidget(self._build_sort(), 0, Qt.AlignVCenter)
        control_row.addWidget(self._build_view_toggle(), 0, Qt.AlignVCenter)
        layout.addLayout(control_row)
        return header

    def _build_section_head(self) -> QHBoxLayout:
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        self._section_title = QLabel('全部照片')
        self._section_title.setObjectName('librarySectionTitle')
        self._section_count = QLabel('')
        self._section_count.setObjectName('librarySectionCount')
        self._section_count.setFont(tabular_font(self._section_count.font()))
        head.addWidget(self._section_title)
        head.addWidget(self._section_count, 0, Qt.AlignBaseline)
        head.addStretch(1)
        return head

    def _build_search(self) -> QLineEdit:
        self._search = QLineEdit()
        self._search.setObjectName('librarySearch')
        self._search.setPlaceholderText('搜索照片、胶片或相纸')
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(240)
        self._search.setFixedHeight(CONTROL_HEIGHT)
        self._search.addAction(shell_icons.icon('search', TEXT_3, 14), QLineEdit.LeadingPosition)
        self._search.textChanged.connect(self._on_search_changed)
        return self._search

    def _build_sort(self) -> SortControl:
        self._sort = SortControl()
        self._sort.currentIndexChanged.connect(self._on_sort_changed)
        return self._sort

    def _build_view_toggle(self) -> QWidget:
        box = QWidget()
        box.setObjectName('viewToggle')
        box.setFixedSize(58, CONTROL_HEIGHT)
        row = QHBoxLayout(box)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(0)
        self._grid_button = QPushButton()
        self._grid_button.setObjectName('viewToggleButton')
        self._grid_button.setCheckable(True)
        self._grid_button.setChecked(True)
        self._grid_button.setIcon(shell_icons.icon('grid', TEXT_1, 14))
        self._grid_button.setIconSize(QSize(14, 14))
        self._grid_button.setFixedSize(27, 26)
        self._grid_button.setCursor(Qt.PointingHandCursor)
        self._grid_button.setToolTip('网格视图')
        self._grid_button.clicked.connect(lambda: self._set_view_mode('grid'))

        self._list_button = QPushButton()
        self._list_button.setObjectName('viewToggleButton')
        self._list_button.setCheckable(True)
        self._list_button.setIcon(shell_icons.icon('list', TEXT_3, 14))
        self._list_button.setIconSize(QSize(14, 14))
        self._list_button.setFixedSize(27, 26)
        self._list_button.setCursor(Qt.PointingHandCursor)
        self._list_button.setToolTip('列表视图')
        self._list_button.clicked.connect(lambda: self._set_view_mode('list'))
        row.addWidget(self._grid_button)
        row.addWidget(self._list_button)
        return box

    def _build_chips(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(6)
        self._chip_group = QtWidgets.QButtonGroup(self)
        self._chip_group.setExclusive(True)
        self._chips: dict[str, QPushButton] = {}
        entries = [
            ('all', '全部', None),
            ('favorite', '收藏', None),
            ('adjusted', '已调整', None),
            ('red', '红', COLOR_HEX['red']),
            ('yellow', '黄', COLOR_HEX['yellow']),
            ('green', '绿', COLOR_HEX['green']),
            ('blue', '蓝', COLOR_HEX['blue']),
        ]
        for key, text, color in entries:
            if key == 'red':
                divider = QFrame()
                divider.setObjectName('chipDivider')
                divider.setFixedSize(1, 18)
                row.addSpacing(2)
                row.addWidget(divider)
                row.addSpacing(2)
            chip = QPushButton(text)
            chip.setObjectName('filterChip')
            chip.setCheckable(True)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setFixedHeight(CONTROL_HEIGHT_SMALL)
            chip.setProperty('tone', key if color else '')
            if color:
                chip.setIcon(shell_icons.dot(color, 9))
                chip.setIconSize(QSize(9, 9))
            chip.clicked.connect(lambda _checked=False, mode=key: self._set_filter(mode))
            self._chip_group.addButton(chip)
            self._chips[key] = chip
            row.addWidget(chip)
        self._chips['all'].setChecked(True)
        return row

    def _build_empty_state(self) -> QWidget:
        empty = QWidget()
        empty.setObjectName('emptyState')
        outer = QVBoxLayout(empty)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addStretch(1)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.setAlignment(Qt.AlignHCenter)

        mark = QFrame()
        mark.setObjectName('emptyMark')
        mark.setFixedSize(76, 76)
        mark_layout = QVBoxLayout(mark)
        mark_layout.setContentsMargins(0, 0, 0, 0)
        icon = QLabel()
        icon.setPixmap(shell_icons.icon('film_frame', TEXT_2, 34).pixmap(34, 34))
        icon.setAlignment(Qt.AlignCenter)
        mark_layout.addWidget(icon)
        column.addWidget(mark, 0, Qt.AlignHCenter)
        column.addSpacing(18)

        self._empty_title = QLabel('照片库还是空的')
        self._empty_title.setObjectName('emptyTitle')
        self._empty_title.setAlignment(Qt.AlignCenter)
        column.addWidget(self._empty_title, 0, Qt.AlignHCenter)
        column.addSpacing(7)

        self._empty_hint = QLabel('把照片拖到这里，或点右上角导入。')
        self._empty_hint.setObjectName('emptyHint')
        self._empty_hint.setAlignment(Qt.AlignCenter)
        self._empty_hint.setWordWrap(False)
        column.addWidget(self._empty_hint, 0, Qt.AlignHCenter)
        column.addSpacing(12)

        self._empty_formats = QLabel('RAW · TIFF · PNG · JPEG')
        self._empty_formats.setObjectName('emptyFormats')
        self._empty_formats.setAlignment(Qt.AlignCenter)
        column.addWidget(self._empty_formats, 0, Qt.AlignHCenter)

        self._empty_buttons = QWidget()
        self._empty_buttons.setObjectName('emptyButtons')
        buttons = QHBoxLayout(self._empty_buttons)
        buttons.setContentsMargins(0, 20, 0, 0)
        buttons.setSpacing(8)
        buttons.setAlignment(Qt.AlignCenter)
        import_photos = QPushButton('导入照片')
        import_photos.setObjectName('primaryAction')
        import_photos.setCursor(Qt.PointingHandCursor)
        import_photos.setFixedHeight(CONTROL_HEIGHT)
        import_photos.clicked.connect(self.import_photos_requested.emit)
        import_folder = QPushButton('导入文件夹')
        import_folder.setObjectName('secondaryAction')
        import_folder.setCursor(Qt.PointingHandCursor)
        import_folder.setFixedHeight(CONTROL_HEIGHT)
        import_folder.clicked.connect(self._choose_folder)
        buttons.addWidget(import_photos)
        buttons.addWidget(import_folder)
        column.addWidget(self._empty_buttons, 0, Qt.AlignHCenter)

        outer.addLayout(column, 0)
        outer.addStretch(1)
        return empty

    # ── 外部入口 ────────────────────────────────────────────────
    def import_photos(self, parent: QWidget | None = None) -> None:
        start_dir = load_dialog_dir('library_photos')
        dialog_parent = self if parent is None else parent
        paths, _ = QFileDialog.getOpenFileNames(
            dialog_parent, '导入照片', start_dir, _IMAGE_FILTER
        )
        if not paths:
            return
        save_dialog_dir('library_photos', str(Path(paths[0]).parent))
        self.import_paths(paths)

    def _choose_folder(self) -> None:
        start_dir = load_dialog_dir('library_folder')
        directory = QFileDialog.getExistingDirectory(self, '导入文件夹', start_dir)
        if not directory:
            return
        save_dialog_dir('library_folder', directory)
        self.import_paths([directory])

    def import_paths(self, paths: list[str]) -> list[str]:
        imported_ids: list[str] = []
        directories = [path for path in paths if Path(path).is_dir()]
        files = [path for path in paths if Path(path).is_file() and is_supported_image(path)]
        QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for directory in directories:
                try:
                    _folder, items = self.store.add_folder(directory)
                except (OSError, ValueError) as exc:
                    QMessageBox.warning(self, '导入文件夹', f'这个文件夹没能导入。\n\n{exc}')
                    continue
                imported_ids.extend(item.id for item in items)
            if files:
                imported_ids.extend(item.id for item in self.store.add_photos(files))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        if not imported_ids:
            self.status_message.emit('没有找到可导入的图片')
            return []
        # 导入后回到“全部照片”，保证新照片立刻可见
        self._filter_mode = 'all'
        self._folder_filter = ''
        self._search_text = ''
        self._visible_limit = 240
        self._chips['all'].setChecked(True)
        if self._search.text():
            self._search.blockSignals(True)
            self._search.clear()
            self._search.blockSignals(False)
        self.refresh()
        self.status_message.emit(f'已导入 {len(imported_ids)} 张照片')
        self.photos_imported.emit(imported_ids)
        return imported_ids

    def set_current_item(self, item_id: str) -> None:
        self._selected_id = item_id
        for card_id, card in self._cards.items():
            card.set_selected(card_id == item_id)

    def refresh(self) -> None:
        items = self._filtered_items()
        self._update_header_and_folders(items)
        self._rebuild_cards(items)
        self._update_empty_state(items)

    def refresh_item(self, item_id: str) -> None:
        card = self._cards.get(item_id)
        item = self.store.item(item_id)
        if card is None or item is None:
            return
        card.update_item(item)
        card.set_selected(item_id == self._selected_id)

    # ── 筛选 / 排序 ─────────────────────────────────────────────
    def _on_search_changed(self, text: str) -> None:
        self._search_text = text.strip().lower()
        self._visible_limit = 240
        self._thumb_refresh_timer.start()

    def _on_sort_changed(self, _index: int) -> None:
        self._sort_mode = str(self._sort.currentData() or 'recent')
        self._visible_limit = 240
        self.refresh()

    def _set_filter(self, mode: str) -> None:
        self._filter_mode = mode
        self._visible_limit = 240
        self._chips[mode].setChecked(True)
        self.refresh()

    def _set_folder_filter(self, folder_id: str) -> None:
        self._folder_filter = folder_id
        self._visible_limit = 240
        for card_id, card in self._folder_cards.items():
            card.set_selected(card_id == folder_id)
        self.refresh()

    def _show_more(self) -> None:
        self._visible_limit += 240
        self.refresh()

    def _set_view_mode(self, mode: str) -> None:
        self._view_mode = mode
        self._grid_button.setChecked(mode == 'grid')
        self._list_button.setChecked(mode == 'list')
        self._grid_button.setIcon(shell_icons.icon('grid', TEXT_1 if mode == 'grid' else TEXT_3, 14))
        self._list_button.setIcon(shell_icons.icon('list', TEXT_1 if mode == 'list' else TEXT_3, 14))
        self.refresh()

    def _filtered_items(self) -> list[LibraryItem]:
        if self._folder_filter:
            items = self.store.items_in_folder(self._folder_filter)
        else:
            items = self.store.all_items()

        if self._filter_mode == 'favorite':
            items = [item for item in items if item.favorite]
        elif self._filter_mode == 'adjusted':
            items = [item for item in items if item.adjusted]
        elif self._filter_mode in COLOR_LABELS:
            items = [item for item in items if item.color == self._filter_mode]

        if self._search_text:
            needle = self._search_text
            items = [
                item for item in items
                if needle in item.name.lower()
                or needle in film_display_name(item.film_stock).lower()
                or needle in paper_display_name(item.print_paper).lower()
                or needle in item.path.lower()
            ]

        if self._sort_mode == 'name':
            items.sort(key=lambda item: (item.name.lower(), item.id))
        elif self._sort_mode == 'favorite':
            items.sort(key=lambda item: (not item.favorite, -item.added_at, item.name.lower()))
        else:
            items.sort(key=lambda item: (-item.added_at, item.name.lower()))
        return items

    def _update_header_and_folders(self, visible_items: list[LibraryItem]) -> None:
        self._subtitle.setText(
            f'{self.store.folder_count()} 个文件夹 · {self.store.item_count()} 张照片'
        )
        if self._folder_filter:
            folder = self.store.folder(self._folder_filter)
            self._section_title.setText(folder.name if folder is not None else '文件夹')
        elif self._filter_mode == 'favorite':
            self._section_title.setText('收藏')
        elif self._filter_mode == 'adjusted':
            self._section_title.setText('已调整')
        elif self._filter_mode in COLOR_LABELS:
            self._section_title.setText(f'{COLOR_LABEL_NAMES[self._filter_mode]}标签')
        else:
            self._section_title.setText('全部照片')
        suffix = (
            ' 张照片'
            if len(visible_items) == self.store.item_count()
            else f' / {self.store.item_count()} 张照片'
        )
        self._section_count.setText(f'{len(visible_items)}{suffix}')

    def _rebuild_cards(self, items: list[LibraryItem]) -> None:
        self._visible_total = len(items)
        if len(items) > self._visible_limit:
            items = items[: self._visible_limit]
            self._more_button.setText(f'显示更多（还有 {self._visible_total - self._visible_limit} 张）')
            self._more_button.show()
        else:
            self._more_button.hide()

        for card in self._cards.values():
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

        while self._list_layout.count():
            layout_item = self._list_layout.takeAt(0)
            if layout_item is not None:
                widget = layout_item.widget()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()

        grid_cards: list[QWidget] = []

        # 文件夹与照片混排在同一网格；文件夹卡在前。
        # 进入某个文件夹时，第一张卡是「全部照片」用于返回。
        self._folder_cards.clear()
        if self._view_mode == 'grid':
            if self._folder_filter:
                back = FolderCard('', '全部照片', self.store.item_count())
                back.clicked.connect(self._set_folder_filter)
                self._folder_cards[''] = back
                grid_cards.append(back)
            else:
                for folder in self.store.all_folders():
                    if folder.id == 'inbox':
                        continue
                    count = len(self.store.items_in_folder(folder.id))
                    card = FolderCard(folder.id, folder.name, count)
                    card.set_selected(self._folder_filter == folder.id)
                    card.clicked.connect(self._set_folder_filter)
                    self._folder_cards[folder.id] = card
                    grid_cards.append(card)

        for item in items:
            card_cls = PhotoCard if self._view_mode == 'grid' else PhotoRow
            card = card_cls(item)
            card.opened.connect(self._on_card_opened)
            card.favorite_requested.connect(self._on_favorite_requested)
            card.color_requested.connect(self._on_color_requested)
            card.remove_requested.connect(self._on_remove_requested)
            card.set_selected(item.id == self._selected_id)
            self._cards[item.id] = card
            image = self.thumbnails.request(item)
            if image is not None and not image.isNull():
                card.set_thumbnail(image)
            if self._view_mode == 'grid':
                grid_cards.append(card)
            else:
                self._list_layout.addWidget(card)

        self._grid.set_cards(grid_cards)
        self._list_layout.addStretch(1)
        index = 0 if self._view_mode == 'grid' else 1
        self._content_stack.setCurrentIndex(index)

    def _update_empty_state(self, items: list[LibraryItem]) -> None:
        if items:
            if self._content_stack.currentIndex() == 2:
                self._content_stack.setCurrentIndex(0 if self._view_mode == 'grid' else 1)
            return
        if self.store.item_count() == 0:
            self._empty_title.setText('照片库还是空的')
            self._empty_hint.setText('把照片拖到这里，或点右上角导入。')
            self._empty_formats.show()
            self._empty_buttons.show()
        else:
            self._empty_title.setText('没有匹配的照片')
            self._empty_hint.setText('换个关键词，或点“全部”清除筛选。')
            self._empty_formats.hide()
            self._empty_buttons.hide()
        self._content_stack.setCurrentIndex(2)

    # ── 卡片动作 ────────────────────────────────────────────────
    def _on_card_opened(self, item_id: str) -> None:
        self._selected_id = item_id
        for card_id, card in self._cards.items():
            card.set_selected(card_id == item_id)
        self.open_item_requested.emit(item_id)

    def _on_favorite_requested(self, item_id: str, favorite: bool) -> None:
        updated = self.store.set_favorite(item_id, favorite)
        if updated is None:
            return
        if self._filter_mode == 'favorite' and not favorite:
            self.refresh()
        else:
            card = self._cards.get(item_id)
            if card is not None:
                card.update_item(updated)
        self.status_message.emit('已收藏' if favorite else '已取消收藏')

    def _on_color_requested(self, item_id: str, color: str) -> None:
        updated = self.store.set_color(item_id, color)
        if updated is None:
            return
        if self._filter_mode in COLOR_LABELS and color != self._filter_mode:
            self.refresh()
        else:
            card = self._cards.get(item_id)
            if card is not None:
                card.update_item(updated)
        self.status_message.emit('已更新颜色标签' if color else '已清除颜色标签')

    def _on_remove_requested(self, item_id: str) -> None:
        item = self.store.item(item_id)
        if item is None:
            return
        self.store.remove_item(item_id)
        if self._selected_id == item_id:
            self._selected_id = ''
        self.refresh()
        self.status_message.emit(f'已从库中移出「{item.name}」（磁盘文件未删除）')

    # ── 缩略图 ──────────────────────────────────────────────────
    def _connect_thumbnails(self) -> None:
        self.thumbnails.thumbnail_ready.connect(self._on_thumbnail_ready)
        self.thumbnails.metadata_ready.connect(self._on_metadata_ready)
        self.thumbnails.thumbnail_failed.connect(self._on_thumbnail_failed)

    def _on_thumbnail_ready(self, item_id: str, image: QtGui.QImage) -> None:
        card = self._cards.get(item_id)
        if card is not None:
            card.set_thumbnail(image)

    def _on_metadata_ready(self, item_id: str, width: int, height: int) -> None:
        item = self.store.item(item_id)
        if item is None or (item.width == width and item.height == height):
            return
        self.store.update_item(item_id, width=int(width), height=int(height), save=False)
        self._meta_save_timer.start()
        card = self._cards.get(item_id)
        if card is not None:
            meta = card._meta
            meta.setText(card._meta_text())

    def _on_thumbnail_failed(self, item_id: str, _message: str) -> None:
        card = self._cards.get(item_id)
        if card is not None:
            card.set_thumbnail_error()

    # ── 拖放 ────────────────────────────────────────────────────
    @staticmethod
    def _dropped_paths(event) -> list[str]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._dropped_paths(event):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt API name
        paths = self._dropped_paths(event)
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self.import_paths(paths)


def _reveal_in_file_manager(path: str) -> None:
    target = Path(path)
    if not target.exists():
        return
    if sys.platform == 'darwin':
        subprocess.Popen(['open', '-R', str(target)])
        return
    if sys.platform == 'win32':
        subprocess.Popen(['explorer', '/select,', str(target)])
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.parent)))
