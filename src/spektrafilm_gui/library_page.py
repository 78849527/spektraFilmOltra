"""照片库主页：Finder 式的照片管理页。

只做展示与收藏/筛选/导入入口；打开照片、载入显影由上层协调器负责。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from qtpy import QtCore, QtGui, QtWidgets

from spektrafilm_gui import shell_icons
from spektrafilm_gui.library_store import (
    COLOR_LABEL_NAMES,
    COLOR_LABELS,
    LibraryItem,
    LibraryStore,
    is_supported_image,
)
from spektrafilm_gui.library_thumbs import ThumbnailService, format_file_size
from spektrafilm_gui.persistence import load_dialog_dir, save_dialog_dir
from spektrafilm_gui.theme_oflim import ACCENT, TEXT_2, TEXT_3
from spektrafilm_gui.ui_names import film_display_name, paper_display_name
from spektrafilm_gui.widget_primitives import tabular_font

QAction = QtGui.QAction
QColor = QtGui.QColor
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
QPixmap = QtGui.QPixmap
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

COLOR_HEX = {
    'red': '#C7705D',
    'yellow': '#C8A97E',
    'green': '#7D9B76',
    'blue': '#6B8CAE',
}

CARD_WIDTH = 208
CARD_HEIGHT = 198
GRID_SPACING = 16

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

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._update_elided()

    def _update_elided(self) -> None:
        width = max(self.width(), 10)
        elided = QFontMetrics(self.font()).elidedText(self._full_text, Qt.ElideMiddle, width)
        super().setText(elided)


class ThumbnailView(QWidget):
    """圆角缩略图；没有缩略图时画占位，源文件丢失时明确提示。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._image: QtGui.QImage | None = None
        self._missing = False
        self._raw = False
        self._error = False

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

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
            path = QPainterPath()
            path.addRoundedRect(rect, 7, 7)
            painter.setClipPath(path)

            if self._image is not None and not self._image.isNull():
                scaled = self._image.scaled(
                    self.size(),
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
                x = (scaled.width() - self.width()) // 2
                y = (scaled.height() - self.height()) // 2
                painter.drawImage(self.rect(), scaled, QtCore.QRect(x, y, self.width(), self.height()))
            else:
                gradient = QtGui.QLinearGradient(0, 0, 0, self.height())
                gradient.setColorAt(0.0, QColor('#1E1E1C'))
                gradient.setColorAt(1.0, QColor('#141414'))
                painter.fillRect(rect, gradient)
                painter.setPen(QtGui.QPen(QColor('#3A3A36'), 1.2))
                cx, cy = self.width() / 2, self.height() / 2
                frame = QRectF(cx - 22, cy - 16, 44, 32)
                painter.drawRoundedRect(frame, 4, 4)
                painter.drawLine(QtCore.QPointF(cx - 14, cy + 7), QtCore.QPointF(cx - 4, cy - 3))
                painter.drawLine(QtCore.QPointF(cx - 4, cy - 3), QtCore.QPointF(cx + 4, cy + 5))
                painter.drawLine(QtCore.QPointF(cx + 1, cy + 2), QtCore.QPointF(cx + 9, cy - 6))
                painter.drawLine(QtCore.QPointF(cx + 9, cy - 6), QtCore.QPointF(cx + 16, cy + 2))
                if self._raw:
                    painter.setPen(QColor('#8A8A82'))
                    font = painter.font()
                    font.setPointSizeF(max(font.pointSizeF() - 1.0, 7.0))
                    font.setWeight(QtGui.QFont.DemiBold)
                    painter.setFont(font)
                    painter.drawText(
                        QRectF(0, self.height() - 24, self.width(), 18),
                        Qt.AlignHCenter | Qt.AlignVCenter,
                        'RAW',
                    )

            painter.setClipping(False)
            painter.setPen(QtGui.QPen(QColor(255, 255, 255, 14), 1))
            painter.drawPath(path)

            if self._missing or self._error:
                painter.fillRect(self.rect(), QColor(11, 11, 11, 190))
                painter.setPen(QColor('#9E9E9E'))
                font = painter.font()
                font.setPointSizeF(max(font.pointSizeF() - 0.5, 8.0))
                painter.setFont(font)
                painter.drawText(
                    self.rect(),
                    Qt.AlignCenter,
                    '文件已移动' if self._missing else '无法预览',
                )
        finally:
            painter.end()


class StarButton(QPushButton):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('starButton')
        self.setCheckable(True)
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip('收藏')
        self.toggled.connect(self._refresh_icon)
        self._refresh_icon(False)

    def _refresh_icon(self, checked: bool) -> None:
        self.setIcon(shell_icons.icon('star_filled' if checked else 'star', ACCENT if checked else '#CFCFC8', 13))
        self.setIconSize(QSize(13, 13))


class ColorDotButton(QPushButton):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('colorButton')
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip('颜色标签')
        self._color = ''
        self.clicked.connect(self._show_menu)

    def set_color(self, color: str) -> None:
        self._color = color if color in COLOR_LABELS else ''
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

    color_selected = Signal(str)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().paintEvent(event)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            if self._color:
                rect = QRectF(6, 6, 10, 10)
                painter.setBrush(QColor(COLOR_HEX[self._color]))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(rect)
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor('#CFCFC8'))
                for x in (6.5, 11.0, 15.5):
                    painter.drawEllipse(QRectF(x - 1.1, 10.0, 2.2, 2.2))
        finally:
            painter.end()


class _BasePhotoCard(QFrame):
    opened = Signal(str)
    favorite_requested = Signal(str, bool)
    color_requested = Signal(str, str)
    remove_requested = Signal(str)

    def __init__(self, item: LibraryItem, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('photoCard')
        self.item = item
        self._selected = False
        self._thumb = ThumbnailView()
        self._thumb.set_raw(item.is_raw)
        self._thumb.set_missing(not item.exists)
        self.star = StarButton()
        self.star.setChecked(item.favorite)
        self.star.blockSignals(True)
        self.star.setChecked(item.favorite)
        self.star.blockSignals(False)
        self.color_button = ColorDotButton()
        self.color_button.set_color(item.color)
        self.star.toggled.connect(lambda checked: self.favorite_requested.emit(self.item.id, bool(checked)))
        self.color_button.color_selected.connect(lambda color: self.color_requested.emit(self.item.id, color))

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self.setProperty('selected', 'true' if selected else 'false')
        self.style().unpolish(self)
        self.style().polish(self)

    def update_item(self, item: LibraryItem) -> None:
        self.item = item
        self._thumb.set_missing(not item.exists)
        self._thumb.set_raw(item.is_raw)
        self.star.blockSignals(True)
        self.star.setChecked(item.favorite)
        self.star.blockSignals(False)
        self.star._refresh_icon(item.favorite)
        self.color_button.set_color(item.color)
        self._name.setText(item.name)
        self._meta.setText(self._meta_text())

    def _meta_text(self) -> str:
        parts: list[str] = []
        if self.item.film_stock:
            parts.append(film_display_name(self.item.film_stock))
        elif self.item.adjusted:
            parts.append('已调整')
        dimensions = ''
        if self.item.width and self.item.height:
            dimensions = f'{self.item.width}×{self.item.height}'
        if dimensions:
            parts.append(dimensions)
        elif self.item.file_size:
            parts.append(format_file_size(self.item.file_size))
        if self.item.is_raw and 'RAW' not in parts:
            parts.insert(0, 'RAW')
        return ' · '.join(parts) or ('RAW' if self.item.is_raw else self.item.suffix.lstrip('.').upper())

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
    def __init__(self, item: LibraryItem, parent: QWidget | None = None):
        super().__init__(item, parent)
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self._thumb.setFixedSize(CARD_WIDTH - 16, 132)

        self._name = ElidedLabel(item.name)
        self._name.setObjectName('photoName')
        self._name.setFixedWidth(CARD_WIDTH - 16)
        self._meta = ElidedLabel(self._meta_text())
        self._meta.setObjectName('photoMeta')
        self._meta.setFont(tabular_font(self._meta.font()))
        self._meta.setFixedWidth(CARD_WIDTH - 16)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)
        layout.addWidget(self._thumb)
        layout.addWidget(self._name)
        layout.addWidget(self._meta)

        self.star.setParent(self)
        self.color_button.setParent(self)
        self.star.move(CARD_WIDTH - 30, 8)
        self.color_button.move(CARD_WIDTH - 56, 8)
        self.star.show()
        self.color_button.show()
        self.star.raise_()
        self.color_button.raise_()

    def set_thumbnail(self, image: QtGui.QImage) -> None:
        self._thumb.set_image(image)
        self._thumb.set_missing(False)

    def set_thumbnail_error(self) -> None:
        self._thumb.set_error(True)


class PhotoRow(_BasePhotoCard):
    def __init__(self, item: LibraryItem, parent: QWidget | None = None):
        super().__init__(item, parent)
        self.setFixedHeight(66)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self._thumb.setFixedSize(76, 50)

        self._name = ElidedLabel(item.name)
        self._name.setObjectName('photoName')
        self._meta = ElidedLabel(self._meta_text())
        self._meta.setObjectName('photoMeta')
        self._meta.setFont(tabular_font(self._meta.font()))

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(2)
        text_box.addWidget(self._name)
        text_box.addWidget(self._meta)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 10, 8)
        layout.setSpacing(10)
        layout.addWidget(self._thumb)
        layout.addLayout(text_box, 1)
        layout.addWidget(self.color_button, 0, Qt.AlignVCenter)
        layout.addWidget(self.star, 0, Qt.AlignVCenter)

    def set_thumbnail(self, image: QtGui.QImage) -> None:
        self._thumb.set_image(image)
        self._thumb.set_missing(False)

    def set_thumbnail_error(self) -> None:
        self._thumb.set_error(True)


class FolderCard(QFrame):
    clicked = Signal(str)

    def __init__(self, folder_id: str, name: str, count: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.folder_id = folder_id
        self.setObjectName('folderCard')
        self.setFixedSize(188, 86)
        self.setCursor(Qt.PointingHandCursor)
        self._selected = False

        icon = QLabel()
        icon.setPixmap(shell_icons.icon('folder', TEXT_3, 26).pixmap(26, 26))
        icon.setFixedSize(28, 28)

        name_label = ElidedLabel(name)
        name_label.setObjectName('folderName')
        name_label.setFixedWidth(132)
        count_label = QLabel(f'{count} 张照片')
        count_label.setObjectName('folderCount')
        count_label.setFont(tabular_font(count_label.font()))

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(2)
        text_box.addWidget(name_label)
        text_box.addWidget(count_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(icon, 0, Qt.AlignTop)
        layout.addLayout(text_box, 1)
        layout.addStretch(1)

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self.setProperty('selected', 'true' if selected else 'false')
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.folder_id)
            event.accept()
            return
        super().mousePressEvent(event)


class ResponsiveGrid(QWidget):
    """固定宽度卡片的响应式网格，列数随可用宽度变化。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('photoGrid')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._cards: list[QWidget] = []
        self._columns = 0
        self._layout = QtWidgets.QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(GRID_SPACING)
        self._layout.setVerticalSpacing(GRID_SPACING)
        self._layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_cards(self, cards: list[QWidget]) -> None:
        for card in self._cards:
            card.setParent(None)
        self._cards = list(cards)
        for card in self._cards:
            card.setParent(self)
        self._columns = 0
        self._relayout(force=True)

    def _available_width(self) -> int:
        width = self.width()
        if width <= 1:
            width = self.parentWidget().width() if self.parentWidget() is not None else CARD_WIDTH
        return max(width, CARD_WIDTH)

    def _column_count(self) -> int:
        usable = max(self._available_width(), CARD_WIDTH)
        return max(1, int((usable + GRID_SPACING) // (CARD_WIDTH + GRID_SPACING)))

    def _relayout(self, *, force: bool = False) -> None:
        columns = self._column_count()
        if not force and columns == self._columns:
            return
        self._columns = columns
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.setParent(self)
        for index, card in enumerate(self._cards):
            row, column = divmod(index, columns)
            self._layout.addWidget(card, row, column, Qt.AlignLeft | Qt.AlignTop)
        for column in range(self._layout.columnCount()):
            self._layout.setColumnStretch(column, 0)
        self._layout.setColumnStretch(columns, 1)
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._relayout()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        columns = max(1, self._column_count())
        rows = max(1, (len(self._cards) + columns - 1) // columns)
        return QSize(
            columns * CARD_WIDTH + max(0, columns - 1) * GRID_SPACING,
            rows * CARD_HEIGHT + max(0, rows - 1) * GRID_SPACING,
        )


class LibraryPage(QWidget):
    import_photos_requested = Signal()
    open_item_requested = Signal(str)
    photos_imported = Signal(list)
    status_message = Signal(str)

    def __init__(self, store: LibraryStore, *, thumbnails: ThumbnailService | None = None, parent: QWidget | None = None):
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
        scroll.setObjectName('libraryScroll')
        scroll.viewport().setAutoFillBackground(False)
        body = QWidget()
        body.setObjectName('libraryBody')
        body.setAutoFillBackground(False)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(28, 22, 28, 32)
        body_layout.setSpacing(16)
        body_layout.addLayout(self._build_toolbar())
        body_layout.addLayout(self._build_chips())
        body_layout.addWidget(self._build_folders())
        self._content_stack = QStackedWidget()
        self._content_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._grid = ResponsiveGrid()
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(8)
        self._list_layout.setAlignment(Qt.AlignTop)
        self._empty = self._build_empty_state()
        self._content_stack.addWidget(self._grid)
        self._content_stack.addWidget(self._list_container)
        self._content_stack.addWidget(self._empty)
        body_layout.addWidget(self._content_stack, 1)
        self._more_button = QPushButton('')
        self._more_button.setObjectName('secondaryAction')
        self._more_button.setCursor(Qt.PointingHandCursor)
        self._more_button.setFixedHeight(32)
        self._more_button.setMaximumWidth(220)
        self._more_button.hide()
        self._more_button.clicked.connect(self._show_more)
        body_layout.addWidget(self._more_button, 0, Qt.AlignHCenter)
        body_layout.addStretch(0)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName('libraryHeader')
        header.setAttribute(Qt.WA_StyledBackground, True)
        header.setFixedHeight(88)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 16, 28, 16)
        layout.setSpacing(12)

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(3)
        self._title = QLabel('照片库')
        self._title.setObjectName('libraryTitle')
        self._subtitle = QLabel('')
        self._subtitle.setObjectName('librarySubtitle')
        self._subtitle.setFont(tabular_font(self._subtitle.font()))
        text_box.addWidget(self._title)
        text_box.addWidget(self._subtitle)

        self._import_photos_button = QPushButton('导入照片')
        self._import_photos_button.setObjectName('primaryAction')
        self._import_photos_button.setCursor(Qt.PointingHandCursor)
        self._import_photos_button.setIcon(shell_icons.icon('import', ACCENT, 14))
        self._import_photos_button.setIconSize(QtCore.QSize(14, 14))
        self._import_photos_button.clicked.connect(self.import_photos_requested.emit)

        self._import_folder_button = QPushButton('导入文件夹')
        self._import_folder_button.setObjectName('secondaryAction')
        self._import_folder_button.setCursor(Qt.PointingHandCursor)
        self._import_folder_button.setIcon(shell_icons.icon('folder', TEXT_2, 14))
        self._import_folder_button.clicked.connect(self._choose_folder)

        layout.addLayout(text_box, 1)
        layout.addWidget(self._import_folder_button, 0, Qt.AlignVCenter)
        layout.addWidget(self._import_photos_button, 0, Qt.AlignVCenter)
        return header

    def _build_toolbar(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)
        self._section_title = QLabel('全部照片')
        self._section_title.setObjectName('librarySectionTitle')
        self._section_count = QLabel('')
        self._section_count.setObjectName('librarySectionCount')
        self._section_count.setFont(tabular_font(self._section_count.font()))
        title_box.addWidget(self._section_title)
        title_box.addWidget(self._section_count)

        self._search = QLineEdit()
        self._search.setObjectName('librarySearch')
        self._search.setPlaceholderText('搜索照片、胶片或相纸')
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(226)
        self._search.addAction(shell_icons.icon('search', TEXT_3, 14), QLineEdit.LeadingPosition)
        self._search.textChanged.connect(self._on_search_changed)

        self._sort = QtWidgets.QComboBox()
        self._sort.setObjectName('librarySort')
        self._sort.addItem('最近导入', 'recent')
        self._sort.addItem('文件名', 'name')
        self._sort.addItem('收藏优先', 'favorite')
        self._sort.setFixedWidth(104)
        self._sort.currentIndexChanged.connect(self._on_sort_changed)

        self._grid_button = QPushButton()
        self._grid_button.setObjectName('iconButton')
        self._grid_button.setCheckable(True)
        self._grid_button.setChecked(True)
        self._grid_button.setIcon(shell_icons.icon('grid', TEXT_2, 15))
        self._grid_button.setFixedSize(28, 28)
        self._grid_button.setToolTip('网格视图')
        self._grid_button.clicked.connect(lambda: self._set_view_mode('grid'))

        self._list_button = QPushButton()
        self._list_button.setObjectName('iconButton')
        self._list_button.setCheckable(True)
        self._list_button.setIcon(shell_icons.icon('list', TEXT_2, 15))
        self._list_button.setFixedSize(28, 28)
        self._list_button.setToolTip('列表视图')
        self._list_button.clicked.connect(lambda: self._set_view_mode('list'))

        toolbar.addLayout(title_box)
        toolbar.addStretch(1)
        toolbar.addWidget(self._search)
        toolbar.addWidget(self._sort)
        toolbar.addWidget(self._grid_button)
        toolbar.addWidget(self._list_button)
        return toolbar

    def _build_chips(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
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
            chip = QPushButton(text)
            chip.setObjectName('filterChip')
            chip.setCheckable(True)
            chip.setCursor(Qt.PointingHandCursor)
            if color:
                chip.setIcon(shell_icons.dot(color, 9))
            chip.clicked.connect(lambda _checked=False, mode=key: self._set_filter(mode))
            self._chip_group.addButton(chip)
            self._chips[key] = chip
            row.addWidget(chip)
        self._chips['all'].setChecked(True)
        row.addStretch(1)
        return row

    def _build_folders(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setObjectName('folderSection')
        self._folder_section = wrapper
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        label = QLabel('文件夹')
        label.setObjectName('librarySectionCount')
        layout.addWidget(label)
        self._folder_scroll = QScrollArea()
        self._folder_scroll.setWidgetResizable(True)
        self._folder_scroll.setFrameShape(QFrame.NoFrame)
        self._folder_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._folder_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._folder_scroll.setFixedHeight(100)
        self._folder_container = QWidget()
        self._folder_layout = QHBoxLayout(self._folder_container)
        self._folder_layout.setContentsMargins(0, 0, 0, 0)
        self._folder_layout.setSpacing(12)
        self._folder_layout.setAlignment(Qt.AlignLeft)
        self._folder_scroll.setWidget(self._folder_container)
        layout.addWidget(self._folder_scroll)
        return wrapper

    def _build_empty_state(self) -> QWidget:
        empty = QWidget()
        empty.setObjectName('emptyState')
        outer = QVBoxLayout(empty)
        outer.setContentsMargins(0, 24, 0, 24)
        outer.addStretch(1)

        card = QFrame()
        card.setObjectName('emptyCard')
        card.setFixedSize(500, 276)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(32, 30, 32, 28)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)

        icon = QLabel()
        icon.setPixmap(shell_icons.icon('film_frame', TEXT_2, 48).pixmap(48, 48))
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(48, 48)
        self._empty_title = QLabel('照片库还是空的')
        self._empty_title.setObjectName('emptyTitle')
        self._empty_title.setAlignment(Qt.AlignCenter)
        self._empty_hint = QLabel('把照片拖到这里，或从右上角导入。')
        self._empty_hint.setObjectName('emptyHint')
        self._empty_hint.setAlignment(Qt.AlignCenter)
        self._empty_hint.setWordWrap(False)
        self._empty_formats = QLabel('RAW · TIFF · PNG · JPEG')
        self._empty_formats.setObjectName('emptyFormats')
        self._empty_formats.setAlignment(Qt.AlignCenter)
        self._empty_buttons = QWidget()
        self._empty_buttons.setObjectName('emptyButtons')
        buttons = QHBoxLayout(self._empty_buttons)
        buttons.setContentsMargins(0, 10, 0, 0)
        buttons.setSpacing(8)
        buttons.setAlignment(Qt.AlignCenter)
        import_photos = QPushButton('导入照片')
        import_photos.setObjectName('primaryAction')
        import_photos.clicked.connect(self.import_photos_requested.emit)
        import_folder = QPushButton('导入文件夹')
        import_folder.setObjectName('secondaryAction')
        import_folder.clicked.connect(self._choose_folder)
        buttons.addWidget(import_photos)
        buttons.addWidget(import_folder)

        layout.addStretch(1)
        layout.addWidget(icon)
        layout.addWidget(self._empty_title)
        layout.addWidget(self._empty_hint)
        layout.addWidget(self._empty_formats)
        layout.addWidget(self._empty_buttons)
        layout.addStretch(1)
        outer.addWidget(card, 0, Qt.AlignHCenter)
        outer.addStretch(1)
        return empty

    # ── 外部入口 ────────────────────────────────────────────────
    def import_photos(self, parent: QWidget | None = None) -> None:
        start_dir = load_dialog_dir('library_photos')
        dialog_parent = self if parent is None else parent
        paths, _ = QFileDialog.getOpenFileNames(dialog_parent, '导入照片', start_dir, _IMAGE_FILTER)
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
        has_items = self.store.item_count() > 0
        if hasattr(self, '_folder_section'):
            self._folder_section.setVisible(has_items)
        self._subtitle.setText(f'{self.store.folder_count()} 个文件夹 · {self.store.item_count()} 张照片')
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
        suffix = ' 张照片' if len(visible_items) == self.store.item_count() else f' / {self.store.item_count()} 张照片'
        self._section_count.setText(f'{len(visible_items)}{suffix}')

        while self._folder_layout.count():
            item = self._folder_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
        self._folder_cards.clear()

        total_card = FolderCard('', '全部照片', self.store.item_count())
        total_card.set_selected(not self._folder_filter)
        total_card.clicked.connect(self._set_folder_filter)
        self._folder_layout.addWidget(total_card)
        self._folder_cards[''] = total_card

        for folder in self.store.all_folders():
            if folder.id == 'inbox':
                continue
            count = len(self.store.items_in_folder(folder.id))
            card = FolderCard(folder.id, folder.name, count)
            card.set_selected(self._folder_filter == folder.id)
            card.clicked.connect(self._set_folder_filter)
            self._folder_layout.addWidget(card)
            self._folder_cards[folder.id] = card
        self._folder_layout.addStretch(1)

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
            self._empty_hint.setText('把照片拖到这里，或从右上角导入。')
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
