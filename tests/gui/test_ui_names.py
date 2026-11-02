from __future__ import annotations

from qtpy import QtWidgets

from spektrafilm_gui import i18n, ui_names
from spektrafilm_gui.widget_editors import EnumEditor, ProfileEnumEditor


def _app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_film_and_paper_names_are_chinese_brand_plus_model() -> None:
    assert ui_names.film_display_name('kodak_portra_400') == '柯达 Portra 400'
    assert ui_names.film_display_name('fujifilm_c200') == '富士 C200'
    assert ui_names.film_display_name('kodak_vision3_500t') == '柯达 Vision3 500T'
    assert ui_names.paper_display_name('kodak_supra_endura') == '柯达 Supra Endura'
    assert ui_names.paper_display_name('kodak_2393') == '柯达 2393 电影印片'
    assert ui_names.film_brand('fujifilm_pro_400h') == '富士'
    assert ui_names.paper_brand('kodak_2383') == '柯达'


def test_friendly_and_technical_labels_stay_separate() -> None:
    assert ui_names.label_for('print_exposure') == '亮度'
    assert ui_names.technical_label_for('print_exposure') == '印相曝光'
    assert ui_names.label_for('film_gamma_factor') == '对比度'
    assert ui_names.technical_label_for('developer_exhaustion') == '显影液疲劳'
    assert ui_names.tip_for('print_exposure')


def test_enum_display_is_chinese_but_raw_value_is_untouched() -> None:
    _app()
    editor = EnumEditor(['black_pro_mist', 'pro_mist', 'glimmerglass'], enum_name='DiffusionFilterFamilies')
    assert editor.display_text_for_value('black_pro_mist') == '黑柔镜'
    assert editor.display_text_for_value('pro_mist') == '白柔镜'
    assert editor.value == 'black_pro_mist'

    editor.value = 'pro_mist'
    assert editor.value == 'pro_mist'
    assert editor.currentText() == 'pro_mist'


def test_profile_editor_keeps_raw_value_and_shows_chinese() -> None:
    _app()
    editor = ProfileEnumEditor(['kodak_portra_400', 'fujifilm_c200'], kind='film_stock')
    assert editor.value == 'kodak_portra_400'
    assert editor.display_text_for_value('kodak_portra_400', 'film_stock') == '柯达 Portra 400'

    editor.value = 'fujifilm_c200'
    assert editor.value == 'fujifilm_c200'
    assert editor.currentText() == 'fujifilm_c200'


def test_translate_falls_back_between_spaces_and_underscores() -> None:
    assert i18n.translate('auto exposure') == '自动曝光'
    assert i18n.translate('auto_exposure') == '自动曝光'
    assert i18n.translate('exposure compensation ev') == '曝光补偿'
    assert i18n.translate('gamma factor') == '印相反差'
    assert i18n.translate('unsharp_mask') == '扫描锐化'
    assert i18n.translate('import rgb') == '导入图片'


def test_unknown_translation_returns_none() -> None:
    assert i18n.translate('a label nobody translated') is None
    assert i18n.tr('a label nobody translated') == 'a label nobody translated'
