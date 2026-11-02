"""导出设置弹窗：格式、画质/压缩、位深、长边、目录与文件名。"""

from __future__ import annotations

from pathlib import Path

from qtpy import QtCore, QtGui, QtWidgets

from spektrafilm_gui import shell_icons
from spektrafilm_gui.export_settings import ExportSettings
from spektrafilm_gui.theme_oflim import (
    ACCENT,
    ACCENT_ON,
    HAIRLINE,
    HAIRLINE_STRONG,
    R_LARGE,
    R_SMALL,
    SURFACE_1,
    SURFACE_2,
    SURFACE_3,
    TEXT_1,
    TEXT_2,
    TEXT_3,
    rgba,
)

Qt = QtCore.Qt

DIALOG_STYLE = f"""
QFrame#exportCard {{
    background: {SURFACE_1};
    border: 1px solid {HAIRLINE_STRONG};
    border-radius: {R_LARGE}px;
}}
QLabel#dialogTitle {{
    color: {TEXT_1}; font-size: 15px; font-weight: 500; letter-spacing: 0.3px;
}}
QLabel#dialogLabel {{
    color: {TEXT_3}; font-size: 9px; font-weight: 500; letter-spacing: 1.2px;
}}
QLabel#dialogHint {{ color: {TEXT_3}; font-size: 10px; }}
QComboBox#dialogCombo, QSpinBox#dialogSpin {{
    background: {SURFACE_2}; color: {TEXT_1};
    border: 1px solid {HAIRLINE}; border-radius: {R_SMALL}px;
    min-height: 27px; padding: 0 8px; font-size: 11px;
}}
QComboBox#dialogCombo:hover, QSpinBox#dialogSpin:hover {{ border-color: {HAIRLINE_STRONG}; }}
QComboBox#dialogCombo:focus, QSpinBox#dialogSpin:focus {{ border-color: {rgba(ACCENT, 0.55)}; }}
QComboBox#dialogCombo QAbstractItemView {{
    background: {SURFACE_2}; color: {TEXT_1}; border: 1px solid {HAIRLINE};
    selection-background-color: {SURFACE_3}; outline: none; padding: 4px;
    font-size: 11px;
}}
QLineEdit#dialogEdit {{
    background: {SURFACE_2}; color: {TEXT_1};
    border: 1px solid {HAIRLINE}; border-radius: {R_SMALL}px;
    min-height: 27px; padding: 0 8px; font-size: 11px;
}}
QLineEdit#dialogEdit:focus {{ border-color: {rgba(ACCENT, 0.55)}; }}
QPushButton#dialogBrowse {{
    background: {SURFACE_3}; color: {TEXT_2};
    border: 1px solid {HAIRLINE}; border-radius: {R_SMALL}px;
    min-height: 27px; padding: 0 10px; font-size: 10.5px;
}}
QPushButton#dialogBrowse:hover {{ color: {TEXT_1}; border-color: {HAIRLINE_STRONG}; }}
QPushButton#dialogCancel {{
    background: transparent; color: {TEXT_2};
    border: 1px solid {HAIRLINE_STRONG}; border-radius: {R_SMALL}px;
    min-height: 28px; padding: 0 16px; font-size: 11px;
}}
QPushButton#dialogCancel:hover {{ color: {TEXT_1}; background: {rgba('#FFFFFF', 0.04)}; }}
QPushButton#dialogSave {{
    background: {ACCENT}; color: {ACCENT_ON};
    border: 1px solid {ACCENT}; border-radius: {R_SMALL}px;
    min-height: 28px; padding: 0 16px; font-size: 11px; font-weight: 600;
}}
QPushButton#dialogSave:hover {{ background: {rgba(ACCENT, 0.9)}; }}
QPushButton#dialogClose {{
    background: transparent; border: none; border-radius: 6px;
}}
QPushButton#dialogClose:hover {{ background: {rgba('#FFFFFF', 0.05)}; }}
"""


class ExportSettingsDialog(QtWidgets.QDialog):
    def __init__(self, settings: ExportSettings, *, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('exportDialog')
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setStyleSheet(DIALOG_STYLE)
        self._initial = settings.normalized()
        self._result: ExportSettings | None = None
        self._format_rows: dict[str, QtWidgets.QWidget] = {}
        self._build_ui()
        self._load(self._initial)
        self._sync_format_rows()
        self.setFixedWidth(452)

    # ── 构建 ────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)

        card = QtWidgets.QFrame()
        card.setObjectName('exportCard')
        shadow = QtWidgets.QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 8)
        shadow.setColor(QtGui.QColor(0, 0, 0, 170))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(22, 16, 22, 18)
        layout.setSpacing(14)
        layout.addLayout(self._build_header())
        layout.addWidget(self._hairline())

        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.setObjectName('dialogCombo')
        for name in ('JPEG', 'PNG', 'TIFF', 'EXR'):
            self.format_combo.addItem(name, name)
        self.format_combo.currentIndexChanged.connect(self._sync_format_rows)

        self.quality_spin = QtWidgets.QSpinBox()
        self.quality_spin.setObjectName('dialogSpin')
        self.quality_spin.setRange(1, 100)

        self.png_level = QtWidgets.QSpinBox()
        self.png_level.setObjectName('dialogSpin')
        self.png_level.setRange(0, 9)

        self.tiff_compression = QtWidgets.QComboBox()
        self.tiff_compression.setObjectName('dialogCombo')
        for label, value in (('无压缩', 'none'), ('ZIP', 'zip'), ('LZW', 'lzw')):
            self.tiff_compression.addItem(label, value)

        self.exr_compression = QtWidgets.QComboBox()
        self.exr_compression.setObjectName('dialogCombo')
        for label, value in (('ZIP', 'zip'), ('PIZ', 'piz'), ('RLE', 'rle')):
            self.exr_compression.addItem(label, value)

        self.bit_depth = QtWidgets.QComboBox()
        self.bit_depth.setObjectName('dialogCombo')

        self.long_edge = QtWidgets.QSpinBox()
        self.long_edge.setObjectName('dialogSpin')
        self.long_edge.setRange(0, 20000)
        self.long_edge.setSpecialValueText('原始尺寸')
        self.long_edge.setSuffix(' px')

        self.directory_edit = QtWidgets.QLineEdit()
        self.directory_edit.setObjectName('dialogEdit')
        self.directory_edit.setPlaceholderText('原图所在目录')
        browse = QtWidgets.QPushButton('选择')
        browse.setObjectName('dialogBrowse')
        browse.setCursor(Qt.PointingHandCursor)
        browse.clicked.connect(self._choose_directory)
        directory_row = QtWidgets.QWidget()
        directory_layout = QtWidgets.QHBoxLayout(directory_row)
        directory_layout.setContentsMargins(0, 0, 0, 0)
        directory_layout.setSpacing(8)
        directory_layout.addWidget(self.directory_edit, 1)
        directory_layout.addWidget(browse, 0)

        self.filename_edit = QtWidgets.QLineEdit()
        self.filename_edit.setObjectName('dialogEdit')
        self.filename_edit.setToolTip('可用占位符：{name} 原文件名，{film} 胶片，{paper} 相纸')

        self._format_rows['JPEG'] = self._field('画质', self.quality_spin)
        self._format_rows['PNG'] = self._field('压缩级别', self.png_level)
        self._format_rows['TIFF'] = self._field('压缩', self.tiff_compression)
        self._format_rows['EXR'] = self._field('压缩', self.exr_compression)
        self._format_rows['BIT_DEPTH'] = self._field('位深', self.bit_depth)

        layout.addWidget(self._field('格式', self.format_combo))
        for key in ('JPEG', 'PNG', 'TIFF', 'EXR'):
            layout.addWidget(self._format_rows[key])
        layout.addWidget(self._format_rows['BIT_DEPTH'])
        layout.addWidget(self._field('长边', self.long_edge, tooltip='大于原图时不放大'))
        layout.addWidget(self._field('导出目录', directory_row))
        layout.addWidget(self._field('文件名', self.filename_edit))
        layout.addSpacing(4)
        layout.addLayout(self._build_footer())

    def _build_header(self) -> QtWidgets.QHBoxLayout:
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addStretch(1)
        title = QtWidgets.QLabel('导出设置')
        title.setObjectName('dialogTitle')
        header.addWidget(title, 0, Qt.AlignVCenter)
        header.addStretch(1)
        close = QtWidgets.QPushButton()
        close.setObjectName('dialogClose')
        close.setFixedSize(26, 26)
        close.setCursor(Qt.PointingHandCursor)
        close.setIcon(shell_icons.icon('close', TEXT_2, 11))
        close.setIconSize(QtCore.QSize(11, 11))
        close.clicked.connect(self.reject)
        header.addWidget(close, 0, Qt.AlignTop)
        return header

    def _build_footer(self) -> QtWidgets.QHBoxLayout:
        footer = QtWidgets.QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(8)
        footer.addStretch(1)
        cancel = QtWidgets.QPushButton('取消')
        cancel.setObjectName('dialogCancel')
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        save = QtWidgets.QPushButton('保存')
        save.setObjectName('dialogSave')
        save.setCursor(Qt.PointingHandCursor)
        save.setIcon(shell_icons.icon('check', ACCENT_ON, 12))
        save.setIconSize(QtCore.QSize(12, 12))
        save.setDefault(True)
        save.clicked.connect(self._accept)
        footer.addWidget(cancel, 0, Qt.AlignVCenter)
        footer.addWidget(save, 0, Qt.AlignVCenter)
        return footer

    @staticmethod
    def _hairline() -> QtWidgets.QFrame:
        line = QtWidgets.QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f'background: {HAIRLINE}; border: none;')
        return line

    @staticmethod
    def _field(label: str, control: QtWidgets.QWidget, *, tooltip: str = '') -> QtWidgets.QWidget:
        row = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        title = QtWidgets.QLabel(label)
        title.setObjectName('dialogLabel')
        if tooltip:
            title.setToolTip(tooltip)
            control.setToolTip(tooltip)
        layout.addWidget(title)
        layout.addWidget(control)
        return row

    # ── 读写 ────────────────────────────────────────────────────
    def _load(self, settings: ExportSettings) -> None:
        index = self.format_combo.findData(settings.format)
        if index >= 0:
            self.format_combo.setCurrentIndex(index)
        self.quality_spin.setValue(settings.jpeg_quality)
        self.png_level.setValue(settings.png_compression)
        self._select_data(self.tiff_compression, settings.tiff_compression)
        self._select_data(self.exr_compression, settings.exr_compression)
        self.long_edge.setValue(settings.long_edge)
        self.directory_edit.setText(settings.directory)
        self.filename_edit.setText(settings.filename_template)

    @staticmethod
    def _select_data(combo: QtWidgets.QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _sync_format_rows(self, *_args) -> None:
        format_name = self.format_combo.currentData() or 'JPEG'
        for key, row in self._format_rows.items():
            if key == 'BIT_DEPTH':
                row.setVisible(format_name in {'TIFF', 'EXR'})
                continue
            row.setVisible(key == format_name)
        if format_name in {'TIFF', 'EXR'}:
            current = self.bit_depth.currentData()
            if current is None:
                current = self._initial.bit_depth
            self.bit_depth.blockSignals(True)
            self.bit_depth.clear()
            depths = (8, 16, 32) if format_name == 'TIFF' else (16, 32)
            for depth in depths:
                self.bit_depth.addItem(f'{depth} 位', depth)
            if current not in depths:
                current = 16 if format_name == 'EXR' else 8
            index = self.bit_depth.findData(current)
            self.bit_depth.setCurrentIndex(max(0, index))
            self.bit_depth.blockSignals(False)

    def _choose_directory(self) -> None:
        start = self.directory_edit.text().strip()
        if not start:
            start = str(Path.home() / 'Pictures')
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, '选择导出目录', start)
        if directory:
            self.directory_edit.setText(directory)

    def settings(self) -> ExportSettings:
        format_name = self.format_combo.currentData() or 'JPEG'
        bit_depth = self.bit_depth.currentData() if format_name in {'TIFF', 'EXR'} else self._initial.bit_depth
        return ExportSettings(
            format=format_name,
            jpeg_quality=self.quality_spin.value(),
            png_compression=self.png_level.value(),
            tiff_compression=self.tiff_compression.currentData() or 'zip',
            exr_compression=self.exr_compression.currentData() or 'zip',
            bit_depth=int(bit_depth or 16),
            long_edge=self.long_edge.value(),
            directory=self.directory_edit.text().strip(),
            filename_template=self.filename_edit.text().strip(),
        ).normalized()

    def _accept(self) -> None:
        self._result = self.settings()
        self.accept()

    def result_settings(self) -> ExportSettings | None:
        return self._result

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is not None:
            frame = parent.window()
            geometry = frame.frameGeometry()
            self.move(geometry.center() - self.rect().center())


def edit_export_settings(parent: QtWidgets.QWidget | None, settings: ExportSettings) -> ExportSettings | None:
    dialog = ExportSettingsDialog(settings, parent=parent)
    if dialog.exec() == QtWidgets.QDialog.Accepted:
        return dialog.result_settings()
    return None


__all__ = ['ExportSettingsDialog', 'edit_export_settings']
