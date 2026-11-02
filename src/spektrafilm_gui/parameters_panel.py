"""参数分页面板：把原有全部参数组织成 5 个页签。

从 napari_layout 拆出来，供「专业参数」侧栏与兼容层共用；
不改变任何参数绑定，只负责摆放。
"""

from __future__ import annotations

from importlib import import_module

from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtCore import Qt

from spektrafilm_gui.theme_oflim import ACCENT, ACCENT_ON, SURFACE_1, SURFACE_2, SURFACE_3, TEXT_2
from spektrafilm_gui.theme_palette import SIZE_PANEL_MARGIN, SIZE_TAB_CONTENT_TOP_MARGIN
from spektrafilm_gui.widget_primitives import CollapsibleSection

QFrame = QtWidgets.QFrame
QScrollArea = QtWidgets.QScrollArea
QTabWidget = QtWidgets.QTabWidget
QVBoxLayout = QtWidgets.QVBoxLayout
QWidget = QtWidgets.QWidget


def _wrap_scrollable(widget: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setSizeAdjustPolicy(QScrollArea.AdjustIgnored)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setFrameShape(QFrame.NoFrame)
    widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
    scroll.setWidget(widget)
    return scroll


def _sections_in(widget: QWidget) -> list[QWidget]:
    sections = list(widget.findChildren(CollapsibleSection))
    if isinstance(widget, CollapsibleSection):
        sections.insert(0, widget)
    return sections


def _build_controls_tab(*widgets: QWidget) -> QWidget:
    tab = QWidget()
    outer = QVBoxLayout(tab)
    outer.setContentsMargins(0, SIZE_TAB_CONTENT_TOP_MARGIN, 0, 0)
    outer.setSpacing(0)
    outer.setAlignment(Qt.AlignTop)

    card = QFrame()
    card.setObjectName('tabCard')
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(4, 10, 4, 10)
    card_layout.setSpacing(2)
    card_layout.setAlignment(Qt.AlignTop)

    for widget in widgets:
        for section in _sections_in(widget):
            section.set_flat(True)
        card_layout.addWidget(widget)

    outer.addWidget(card)
    return tab


def _get_current_stylesheet() -> str:
    try:
        return str(import_module('napari.qt').get_current_stylesheet())
    except (ImportError, AttributeError):
        return ''


def _borrow_layer_list_widget(viewer) -> QWidget | None:
    qt_viewer = getattr(viewer.window, '_qt_viewer', None)
    layer_list = getattr(qt_viewer, 'dockLayerList', None) if qt_viewer is not None else None
    if layer_list is None or not hasattr(layer_list, 'widget'):
        return None
    widget = layer_list.widget()
    if isinstance(widget, QWidget):
        palette = widget.palette()
        palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(ACCENT))
        palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(ACCENT_ON))
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor(SURFACE_2))
        palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(SURFACE_3))
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor(SURFACE_1))
        palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(TEXT_2))
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor(TEXT_2))
        palette.setColor(QtGui.QPalette.Button, QtGui.QColor(SURFACE_2))
        palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(TEXT_2))
        widget.setPalette(palette)
        for child in widget.findChildren(QWidget):
            child.setPalette(palette)
        widget.setStyleSheet(_get_current_stylesheet())
    return widget


def _toggle_row(label: str, editor: QWidget, tooltip: str = '') -> QWidget:
    row = QWidget()
    layout = QtWidgets.QHBoxLayout(row)
    layout.setContentsMargins(0, 2, 0, 2)
    layout.setSpacing(8)
    text = QtWidgets.QLabel(label)
    text.setObjectName('paramLabel')
    if tooltip:
        text.setToolTip(tooltip)
        editor.setToolTip(tooltip)
    layout.addWidget(text, 1, Qt.AlignVCenter)
    layout.addWidget(editor, 0, Qt.AlignRight | Qt.AlignVCenter)
    return row


def _build_run_tab(widgets) -> QWidget:
    simulation = widgets.simulation
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(8)
    layout.addWidget(QtWidgets.QLabel('运行与预览'))
    layout.addWidget(_toggle_row('自动预览', simulation._editors['auto_preview'], '改参数后自动重算小图'))
    layout.addWidget(_toggle_row('按印相扫描', simulation.bottom_scan_for_print, '扫描时启用白场/黑场校正并关闭眩光'))
    layout.addWidget(_toggle_row('查看底片', simulation._editors['scan_film'], '查看未印相的负片'))
    hint = QtWidgets.QLabel('预览、生成全尺寸与保存都在右上角“导出”菜单里。')
    hint.setObjectName('paramLabel')
    hint.setWordWrap(True)
    layout.addSpacing(6)
    layout.addWidget(hint)
    layout.addStretch(1)
    return content


def build_parameter_tabs(viewer, widgets) -> QTabWidget:
    load_raw = getattr(widgets, 'load_raw', None)
    if load_raw is not None:
        for attribute in ('file_path', 'browse_button'):
            widget = getattr(load_raw, attribute, None)
            if widget is not None:
                widget.hide()

    panel = QTabWidget()
    panel.setObjectName('controlsTabWidget')
    panel.setDocumentMode(True)
    panel.setUsesScrollButtons(False)
    panel.tabBar().setDrawBase(False)

    panel.addTab(
        _wrap_scrollable(
            _build_controls_tab(
                widgets.load_raw,
                widgets.preview_crop,
                widgets.input_image,
                widgets.camera,
                widgets.exposure_control,
            ),
        ),
        '曝光',
    )
    panel.addTab(
        _wrap_scrollable(_build_controls_tab(widgets.halation, widgets.couplers, widgets.grain, widgets.camera_diffusion)),
        '胶片',
    )
    panel.addTab(
        _wrap_scrollable(
            _build_controls_tab(
                widgets.enlarger,
                widgets.chemistry,
                widgets.glare,
                widgets.preflashing,
                widgets.enlarger_diffusion,
                widgets.scanner,
            ),
        ),
        '印相',
    )
    panel.addTab(
        _wrap_scrollable(
            _build_controls_tab(
                widgets.output,
                widgets.spectral_upsampling,
                widgets.input_gamut_compress,
                widgets.output_gamut_compress,
                widgets.tune,
                widgets.special,
            ),
        ),
        '输出',
    )

    panel.addTab(_wrap_scrollable(_build_run_tab(widgets)), '运行')

    layers_content = QWidget()
    layers_layout = QVBoxLayout(layers_content)
    layers_layout.setContentsMargins(0, 0, 0, 0)
    layers_layout.setSpacing(6)
    layer_list_widget = _borrow_layer_list_widget(viewer)
    if layer_list_widget is not None:
        layers_layout.addWidget(layer_list_widget)

    panel.addTab(
        _wrap_scrollable(
            _build_controls_tab(
                widgets.gui_config,
                widgets.display,
                CollapsibleSection('napari layers', layers_content, expanded=False),
            ),
        ),
        '配置',
    )
    return panel


def build_professional_panel(viewer, widgets) -> QWidget:
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(SIZE_PANEL_MARGIN, 8, SIZE_PANEL_MARGIN, 8)
    layout.setSpacing(0)
    layout.addWidget(build_parameter_tabs(viewer, widgets), 1)
    return container
