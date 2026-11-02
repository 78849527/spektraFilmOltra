from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from qtpy import QtWidgets

from spektrafilm_gui import controller as controller_module
from spektrafilm_gui.controller import GuiController
from spektrafilm_gui.export_dialog import ExportSettingsDialog
from spektrafilm_gui.export_settings import (
    DirectExportSettings,
    ExportSettings,
    load_export_settings,
    save_export_settings,
)


@pytest.fixture()
def qt_app():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    return app


def test_export_settings_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr('spektrafilm_gui.export_settings.app_paths.app_config_dir', lambda: tmp_path)
    settings = ExportSettings(
        format='TIFF',
        jpeg_quality=88,
        png_compression=3,
        tiff_compression='lzw',
        exr_compression='piz',
        bit_depth=32,
        long_edge=2400,
        directory=str(tmp_path / 'out'),
        filename_template='{name}_{film}',
    )
    save_export_settings(settings)
    loaded = load_export_settings()
    assert loaded == settings.normalized()


def test_export_settings_rejects_bad_values() -> None:
    settings = ExportSettings(format='GIF', jpeg_quality=500, png_compression=-3, bit_depth=12).normalized()
    assert settings.format == 'JPEG'
    assert settings.jpeg_quality == 100
    assert settings.png_compression == 0
    assert settings.bit_depth == 16


def test_direct_export_settings_are_png_at_ninety_percent() -> None:
    settings = DirectExportSettings().to_export_settings(4000)
    assert settings.format == 'PNG'
    assert settings.long_edge == 3600
    assert settings.png_compression == 9
    assert settings.directory == ''
    assert settings.filename_template == '{name}_spektrafilm'


@pytest.mark.usefixtures('qt_app')
def test_export_direct_writes_png_at_ninety_percent(monkeypatch, tmp_path) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        controller,
        '_export_payload_or_warn',
        lambda: (np.zeros((100, 200, 3), dtype=np.float32), 'ProPhoto RGB', False, None),
    )
    monkeypatch.setattr(controller, '_export_target_path', lambda settings: tmp_path / 'direct.png')

    def fake_save(filepath, image_data, settings, *, color_space, cctf_encoding):
        captured.update(
            filepath=filepath,
            shape=image_data.shape,
            settings=settings,
            color_space=color_space,
            cctf_encoding=cctf_encoding,
        )

    monkeypatch.setattr(controller, '_save_with_settings', fake_save)
    monkeypatch.setattr(controller, '_write_export_metadata', lambda *args, **kwargs: None)
    monkeypatch.setattr(controller_module, 'set_status', lambda *args, **kwargs: None)

    controller.export_direct()

    assert captured['filepath'] == tmp_path / 'direct.png'
    assert max(captured['shape'][:2]) == 180
    assert captured['settings'].format == 'PNG'
    assert captured['settings'].png_compression == 9
    assert captured['color_space'] == 'ProPhoto RGB'
    assert captured['cctf_encoding'] is False


@pytest.mark.usefixtures('qt_app')
def test_export_dialog_maps_format_controls(qt_app) -> None:
    dialog = ExportSettingsDialog(ExportSettings(format='TIFF', tiff_compression='lzw', bit_depth=32))
    dialog.format_combo.setCurrentIndex(dialog.format_combo.findData('TIFF'))
    dialog.tiff_compression.setCurrentIndex(dialog.tiff_compression.findData('lzw'))
    dialog.bit_depth.setCurrentIndex(dialog.bit_depth.findData(32))
    settings = dialog.settings()
    assert settings.format == 'TIFF'
    assert settings.tiff_compression == 'lzw'
    assert settings.bit_depth == 32
    dialog.deleteLater()


@pytest.mark.parametrize(
    ('format_name', 'suffix', 'expected_quality', 'expected_compression'),
    [
        ('JPEG', '.jpg', 85, None),
        ('PNG', '.png', None, 4),
        ('TIFF', '.tif', None, 'lzw'),
        ('EXR', '.exr', None, 'piz'),
    ],
)
def test_export_now_uses_settings(
    monkeypatch,
    tmp_path,
    format_name: str,
    suffix: str,
    expected_quality,
    expected_compression,
) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    settings = ExportSettings(
        format=format_name,
        jpeg_quality=85,
        png_compression=4,
        tiff_compression='lzw',
        exr_compression='piz',
        bit_depth=32,
        directory=str(tmp_path),
        filename_template='{name}_export',
    )
    controller._export_settings = settings
    controller._current_input_path = str(tmp_path / 'source.dng')
    captured: dict[str, object] = {}

    monkeypatch.setattr(controller, '_output_layer', lambda: object())
    monkeypatch.setattr(
        controller,
        '_export_image_payload',
        lambda: (np.zeros((2, 2, 3), dtype=np.float32), 'sRGB', True, None),
    )
    monkeypatch.setattr(
        'spektrafilm_gui.controller.collect_gui_state',
        lambda *, widgets: SimpleNamespace(
            simulation=SimpleNamespace(
                selection=SimpleNamespace(film_stock='kodak_gold_200', print_paper='kodak_supra_endura'),
            ),
        ),
    )
    monkeypatch.setattr(controller_module, 'save_image_oiio', lambda path, data, **kwargs: captured.update(path=path, kwargs=kwargs))
    monkeypatch.setattr(controller_module, 'write_image_metadata', lambda *args, **kwargs: None)
    monkeypatch.setattr(controller_module, 'set_status', lambda *args, **kwargs: None)

    controller.export_now()

    assert str(captured['path']).endswith(f'source_export{suffix}')
    assert captured['kwargs']['quality'] == expected_quality
    assert captured['kwargs']['compression'] == expected_compression
    if format_name in {'TIFF', 'EXR'}:
        assert captured['kwargs']['bit_depth'] == 32
