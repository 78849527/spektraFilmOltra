"""左侧预设台：胶片 / 相纸。

Spektra 的运行时没有「套用外部 LUT」的入口，所以这里不做 LUT 预设，
只做它原生支持的胶片与相纸组合。点击卡片仍然走
「设置下拉值 + apply_profile_defaults」这条原有链路。
"""

from __future__ import annotations

import hashlib

from qtpy import QtCore, QtGui, QtWidgets

from spektrafilm.model.stocks import FilmStocks, PrintPapers
from spektrafilm_gui import shell_icons
from spektrafilm_gui.library_page import ElidedLabel
from spektrafilm_gui.theme_oflim import TEXT_3
from spektrafilm_gui.ui_names import (
    FILM_GROUPS,
    FILM_ISO,
    PAPER_NOTES,
    film_brand,
    film_display_name,
    paper_brand,
    paper_display_name,
)
from spektrafilm_gui.widget_primitives import DampedScrollArea

QFrame = QtWidgets.QFrame
QHBoxLayout = QtWidgets.QHBoxLayout
QLabel = QtWidgets.QLabel
QLineEdit = QtWidgets.QLineEdit
QPainter = QtGui.QPainter
QPainterPath = QtGui.QPainterPath
QPushButton = QtWidgets.QPushButton
QScrollArea = QtWidgets.QScrollArea
QVBoxLayout = QtWidgets.QVBoxLayout
QWidget = QtWidgets.QWidget
QRectF = QtCore.QRectF
Qt = QtCore.Qt
Signal = QtCore.Signal


def _film_entries() -> list[dict[str, str]]:
    entries = []
    for stock in FilmStocks:
        raw = stock.value
        entries.append({
            'raw': raw,
            'name': film_display_name(raw),
            'brand': film_brand(raw),
            'meta': f'{FILM_GROUPS.get(raw, "彩色负片")} · {FILM_ISO.get(raw, "")}'.strip(' ·'),
        })
    return entries


def _paper_entries() -> list[dict[str, str]]:
    entries = []
    for paper in PrintPapers:
        raw = paper.value
        entries.append({
            'raw': raw,
            'name': paper_display_name(raw),
            'brand': paper_brand(raw),
            'meta': PAPER_NOTES.get(raw, '彩色相纸'),
        })
    return entries


class _StockSwatch(QWidget):
    def __init__(self, raw: str, *, is_paper: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(42, 42)
        seed = int(hashlib.sha1(raw.encode('utf-8')).hexdigest()[:6], 16)
        self._is_paper = is_paper
        if is_paper:
            self._base = QtGui.QColor(226, 216, 196)
            self._accent = QtGui.QColor(180, 158, 120)
        elif 'fujifilm' in raw:
            self._base = QtGui.QColor(52, 92, 82)
            self._accent = QtGui.QColor(120, 178, 146)
        else:
            self._base = QtGui.QColor(92, 62, 40)
            self._accent = QtGui.QColor(212, 168, 108)
        self._hue_shift = (seed % 40) - 20
        self._reversal = 'ektachrome' in raw or 'kodachrome' in raw or 'velvia' in raw or 'provia' in raw
        self._cine = 'vision3' in raw

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
            path = QPainterPath()
            path.addRoundedRect(rect, 6, 6)
            painter.setClipPath(path)

            base = QtGui.QColor(self._base)
            accent = QtGui.QColor(self._accent)
            base.setHsv((base.hue() + self._hue_shift) % 360, base.saturation(), base.value())
            accent.setHsv((accent.hue() + self._hue_shift) % 360, accent.saturation(), accent.value())
            gradient = QtGui.QLinearGradient(0, 0, self.width(), self.height())
            gradient.setColorAt(0.0, accent if self._reversal else base)
            gradient.setColorAt(0.55, base)
            gradient.setColorAt(1.0, QtGui.QColor(24, 24, 22))
            painter.fillRect(rect, gradient)

            if not self._is_paper:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QtGui.QColor(0, 0, 0, 90))
                for index in range(4):
                    y = 4 + index * 9
                    painter.drawRoundedRect(QRectF(2, y, 2.4, 5), 0.8, 0.8)
                if self._cine:
                    painter.setBrush(QtGui.QColor(accent.red(), accent.green(), accent.blue(), 90))
                    painter.drawRect(QRectF(32, 0, self.width() - 32, self.height()))
            else:
                painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 40), 0.8))
                for index in range(3):
                    y = 12 + index * 8
                    painter.drawLine(QtCore.QPointF(8, y), QtCore.QPointF(self.width() - 8, y))

            painter.setClipping(False)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 20), 1))
            painter.drawPath(path)
        finally:
            painter.end()


class PresetCard(QFrame):
    selected = Signal(str)

    def __init__(self, entry: dict[str, str], *, is_paper: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('presetCard')
        self.entry = entry
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(54)
        self._selected = False

        swatch = _StockSwatch(entry['raw'], is_paper=is_paper)
        swatch.setFixedSize(38, 38)
        name = ElidedLabel(entry['name'])
        name.setObjectName('presetName')
        meta = ElidedLabel(entry['meta'])
        meta.setObjectName('presetMeta')
        name.setToolTip(entry['name'])
        meta.setToolTip(entry['meta'])

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(2)
        text_box.addWidget(name)
        text_box.addWidget(meta)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 12, 8)
        layout.setSpacing(10)
        layout.addWidget(swatch)
        layout.addLayout(text_box, 1)

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self.setProperty('selected', 'true' if selected else 'false')
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.LeftButton:
            self.selected.emit(self.entry['raw'])
            event.accept()
            return
        super().mousePressEvent(event)


class PresetRail(QWidget):
    film_selected = Signal(str)
    paper_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('presetRail')
        self.setFixedWidth(300)
        self._films = _film_entries()
        self._papers = _paper_entries()
        self._tab = 'film'
        self._brand = '全部'
        self._search = ''
        self._current_film = ''
        self._current_paper = ''
        self._cards: dict[str, PresetCard] = {}
        self._build_ui()
        self._rebuild()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 0, 14, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 14, 0, 0)
        header.setSpacing(6)
        self._tab_group = QtWidgets.QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._film_tab = QPushButton('胶片')
        self._paper_tab = QPushButton('相纸')
        for index, button in enumerate((self._film_tab, self._paper_tab)):
            button.setObjectName('modeTab')
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(26)
            button.clicked.connect(lambda _checked=False, target=index: self._set_tab('film' if target == 0 else 'paper'))
            self._tab_group.addButton(button)
            header.addWidget(button)
        self._film_tab.setChecked(True)
        self._film_tab.setText(f'胶片 {len(self._films)}')
        self._paper_tab.setText(f'相纸 {len(self._papers)}')
        header.addStretch(1)
        root.addLayout(header)

        self._search_box = QLineEdit()
        self._search_box.setObjectName('presetSearch')
        self._search_box.setPlaceholderText('搜索胶片或相纸')
        self._search_box.setClearButtonEnabled(True)
        self._search_box.setFixedHeight(32)
        self._search_box.addAction(shell_icons.icon('search', TEXT_3, 12), QLineEdit.LeadingPosition)
        self._search_box.textChanged.connect(self._on_search)
        root.addWidget(self._search_box)

        self._brand_row = QHBoxLayout()
        self._brand_row.setContentsMargins(0, 0, 0, 0)
        self._brand_row.setSpacing(6)
        self._brand_group = QtWidgets.QButtonGroup(self)
        self._brand_group.setExclusive(True)
        self._brand_buttons: dict[str, QPushButton] = {}
        for brand in ('全部', '柯达', '富士'):
            button = QPushButton(brand)
            button.setObjectName('brandChip')
            button.setCheckable(True)
            button.setFixedHeight(26)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, value=brand: self._set_brand(value))
            self._brand_group.addButton(button)
            self._brand_buttons[brand] = button
            self._brand_row.addWidget(button)
        self._brand_buttons['全部'].setChecked(True)
        self._brand_row.addStretch(1)
        root.addLayout(self._brand_row)

        self._scroll = DampedScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._list = QWidget()
        self._list_layout = QVBoxLayout(self._list)
        self._list_layout.setContentsMargins(0, 2, 0, 2)
        self._list_layout.setSpacing(4)
        self._list_layout.setAlignment(Qt.AlignTop)
        self._scroll.setWidget(self._list)
        root.addWidget(self._scroll, 1)

    def _set_tab(self, tab: str) -> None:
        self._tab = tab
        self._film_tab.setChecked(tab == 'film')
        self._paper_tab.setChecked(tab == 'paper')
        self._brand = '全部'
        self._brand_buttons['全部'].setChecked(True)
        self._search = ''
        self._search_box.clear()
        self._rebuild()

    def _set_brand(self, brand: str) -> None:
        self._brand = brand
        self._brand_buttons[brand].setChecked(True)
        self._rebuild()

    def _on_search(self, text: str) -> None:
        self._search = text.strip().lower()
        self._rebuild()

    def _entries(self) -> list[dict[str, str]]:
        entries = self._films if self._tab == 'film' else self._papers
        if self._brand != '全部':
            entries = [entry for entry in entries if entry['brand'] == self._brand]
        if self._search:
            needle = self._search
            entries = [
                entry for entry in entries
                if needle in entry['name'].lower()
                or needle in entry['raw'].lower()
                or needle in entry['meta'].lower()
                or needle in entry['brand'].lower()
            ]
        return entries

    def _rebuild(self) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
        self._cards.clear()

        entries = self._entries()
        for entry in entries:
            card = PresetCard(entry, is_paper=self._tab == 'paper')
            current = self._current_film if self._tab == 'film' else self._current_paper
            card.set_selected(entry['raw'] == current)
            card.selected.connect(self._on_card_selected)
            self._cards[entry['raw']] = card
            self._list_layout.addWidget(card)
        self._list_layout.addStretch(1)

    def _on_card_selected(self, raw: str) -> None:
        if self._tab == 'film':
            self._current_film = raw
            self._refresh_selection()
            self.film_selected.emit(raw)
        else:
            self._current_paper = raw
            self._refresh_selection()
            self.paper_selected.emit(raw)

    def _refresh_selection(self) -> None:
        current = self._current_film if self._tab == 'film' else self._current_paper
        for raw, card in self._cards.items():
            card.set_selected(raw == current)

    def set_current(self, film_raw: str, paper_raw: str) -> None:
        self._current_film = film_raw
        self._current_paper = paper_raw
        self._refresh_selection()
        current = film_raw if self._tab == 'film' else paper_raw
        card = self._cards.get(current)
        if card is not None:
            self._scroll.ensureWidgetVisible(card, 0, 40)
