"""oflim 形态的「胶片 / 相纸」卡片。

只做版式：把原本折叠在 Profiles 面板里的两个下拉提升为常驻大卡，
显示当前胶片名与厂商，下方是两条完整宽度的选择器。
参数绑定完全沿用传入的编辑器实例，不新增任何数据通路。
"""

from __future__ import annotations

from qtpy import QtCore, QtGui, QtWidgets

from spektrafilm_gui.theme_oflim import (
    ACCENT,
    ACCENT_DIM,
    HAIRLINE,
    HAIRLINE_STRONG,
    R_MEDIUM,
    R_SMALL,
    SURFACE_2,
    SURFACE_3,
    TEXT_1,
    TEXT_2,
    TEXT_3,
    TEXT_4,
)
from spektrafilm_gui.ui_names import film_brand, film_display_name, paper_brand, paper_display_name


def _brand_of(profile_name: str, *, is_paper: bool = False) -> str:
    name = profile_name.strip()
    if not name:
        return ''
    return paper_brand(name) if is_paper else film_brand(name)


class _StockSwatch(QtWidgets.QWidget):
    """64×64 的胶片色块：黄铜到深色的斜向渐变，作为识别锚点。"""

    def __init__(self):
        super().__init__()
        self.setFixedSize(64, 64)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            rect = QtCore.QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
            path = QtGui.QPainterPath()
            path.addRoundedRect(rect, R_SMALL, R_SMALL)
            painter.setClipPath(path)

            gradient = QtGui.QLinearGradient(0, 0, self.width(), self.height())
            gradient.setColorAt(0.0, QtGui.QColor(ACCENT))
            gradient.setColorAt(0.55, QtGui.QColor(ACCENT_DIM))
            gradient.setColorAt(1.0, QtGui.QColor(SURFACE_2))
            painter.fillRect(rect, gradient)

            painter.setClipping(False)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 20), 1))
            painter.drawPath(path)
        finally:
            painter.end()


class FilmLookCard(QtWidgets.QWidget):
    """oflim 的 LookCard 在 spektrafilm 里的对应物。"""

    def __init__(self, film_editor: QtWidgets.QWidget, print_editor: QtWidgets.QWidget):
        super().__init__()
        self._film_editor = film_editor
        self._print_editor = print_editor

        self.setObjectName('filmLookCard')

        self._swatch = _StockSwatch()

        self._name = QtWidgets.QLabel('')
        name_font = self._name.font()
        name_font.setPointSizeF(max(name_font.pointSizeF() + 1.5, 11.0))
        name_font.setWeight(QtGui.QFont.DemiBold)
        self._name.setFont(name_font)
        self._name.setStyleSheet(f'color: {TEXT_1}; background: transparent;')
        self._name.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)

        self._meta = QtWidgets.QLabel('')
        meta_font = self._meta.font()
        meta_font.setPointSizeF(max(meta_font.pointSizeF() - 1.0, 7.5))
        self._meta.setFont(meta_font)
        self._meta.setStyleSheet(f'color: {TEXT_3}; background: transparent;')

        self._brand = QtWidgets.QLabel('')
        brand_font = self._brand.font()
        brand_font.setPointSizeF(max(brand_font.pointSizeF() - 1.5, 7.0))
        brand_font.setWeight(QtGui.QFont.DemiBold)
        brand_font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, 0.9)
        self._brand.setFont(brand_font)
        self._brand.setStyleSheet(f'color: {ACCENT}; background: transparent;')

        identity = QtWidgets.QVBoxLayout()
        identity.setContentsMargins(0, 0, 0, 0)
        identity.setSpacing(2)
        identity.addWidget(self._name)
        identity.addWidget(self._meta)
        identity.addSpacing(2)
        identity.addWidget(self._brand)
        identity.addStretch(1)

        top_row = QtWidgets.QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(11)
        top_row.addWidget(self._swatch, 0, QtCore.Qt.AlignTop)
        top_row.addLayout(identity, 1)

        film_label = self._caption('胶片型号')
        print_label = self._caption('相纸型号')

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(11, 11, 11, 11)
        layout.setSpacing(7)
        layout.addLayout(top_row)
        layout.addWidget(self._rule())
        layout.addWidget(film_label)
        layout.addWidget(film_editor)
        layout.addSpacing(2)
        layout.addWidget(print_label)
        layout.addWidget(print_editor)

        self.setStyleSheet(
            f'QWidget#filmLookCard {{ background: {SURFACE_3}; '
            f'border: 1px solid {HAIRLINE_STRONG}; border-radius: {R_MEDIUM}px; }}'
        )

        # 下拉变化时同步卡片抬头（只读展示，不参与参数写回）
        for editor in (film_editor, print_editor):
            signal = getattr(editor, 'currentTextChanged', None)
            if signal is not None:
                signal.connect(self._refresh)
        self._refresh()

    @staticmethod
    def _caption(text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        font = label.font()
        font.setPointSizeF(max(font.pointSizeF() - 1.5, 7.0))
        font.setWeight(QtGui.QFont.DemiBold)
        font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, 1.0)
        label.setFont(font)
        label.setStyleSheet(f'color: {TEXT_4}; background: transparent;')
        return label

    @staticmethod
    def _rule() -> QtWidgets.QFrame:
        rule = QtWidgets.QFrame()
        rule.setFixedHeight(1)
        rule.setStyleSheet(f'background: {HAIRLINE}; border: none;')
        return rule

    def _current_text(self, editor: QtWidgets.QWidget) -> str:
        text = getattr(editor, 'currentText', None)
        if callable(text):
            return str(text())
        value = getattr(editor, 'value', '')
        return str(value)

    def _refresh(self) -> None:
        film = self._current_text(self._film_editor)
        paper = self._current_text(self._print_editor)
        self._name.setText(film_display_name(film) if film else '—')
        self._meta.setText(f'相纸 · {paper_display_name(paper)}' if paper else '胶片模拟')
        self._brand.setText(_brand_of(film))
