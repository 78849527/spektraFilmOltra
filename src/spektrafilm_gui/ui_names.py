"""界面显示名层。

这里 **只** 放给人看的字符串：参数友好名、胶片/相纸中文名、枚举中文名、
提示语。任何键（dotted path、枚举原值、JSON 字段）都不在这里改写，
运行时参数值与持久化格式保持原样。

原则：
- 有中文就用中文；商品型号（Portra 400、C200）没有通行中文名时保留原文。
- 专业参数在「专业」面板保留精确中文名，在「基础」面板用可感知的友好名。
- 同一个参数可以有多个名字：``label_for(leaf)`` 给基础面板，
  ``technical_label_for(leaf)`` 给专业面板。
"""

from __future__ import annotations

# ── 胶片 / 相纸 ──────────────────────────────────────────────────

FILM_BRANDS = {
    'kodak_ektar_100': '柯达',
    'kodak_portra_160': '柯达',
    'kodak_portra_400': '柯达',
    'kodak_portra_800': '柯达',
    'kodak_portra_800_push1': '柯达',
    'kodak_portra_800_push2': '柯达',
    'kodak_gold_200': '柯达',
    'kodak_ultramax_400': '柯达',
    'kodak_vision3_50d': '柯达',
    'kodak_vision3_250d': '柯达',
    'kodak_verita_200d': '柯达',
    'kodak_vision3_200t': '柯达',
    'kodak_vision3_500t': '柯达',
    'fujifilm_pro_400h': '富士',
    'fujifilm_c200': '富士',
    'fujifilm_xtra_400': '富士',
    'kodak_ektachrome_100': '柯达',
    'kodak_kodachrome_64': '柯达',
    'fujifilm_velvia_100': '富士',
    'fujifilm_provia_100f': '富士',
}

FILM_DISPLAY_NAMES = {
    'kodak_ektar_100': '柯达 Ektar 100',
    'kodak_portra_160': '柯达 Portra 160',
    'kodak_portra_400': '柯达 Portra 400',
    'kodak_portra_800': '柯达 Portra 800',
    'kodak_portra_800_push1': '柯达 Portra 800 推一档',
    'kodak_portra_800_push2': '柯达 Portra 800 推两档',
    'kodak_gold_200': '柯达 Gold 200',
    'kodak_ultramax_400': '柯达 UltraMax 400',
    'kodak_vision3_50d': '柯达 Vision3 50D',
    'kodak_vision3_250d': '柯达 Vision3 250D',
    'kodak_verita_200d': '柯达 Verita 200D',
    'kodak_vision3_200t': '柯达 Vision3 200T',
    'kodak_vision3_500t': '柯达 Vision3 500T',
    'fujifilm_pro_400h': '富士 Pro 400H',
    'fujifilm_c200': '富士 C200',
    'fujifilm_xtra_400': '富士 X-Tra 400',
    'kodak_ektachrome_100': '柯达 Ektachrome 100',
    'kodak_kodachrome_64': '柯达 Kodachrome 64',
    'fujifilm_velvia_100': '富士 Velvia 100',
    'fujifilm_provia_100f': '富士 Provia 100F',
}

# 负片 / 反转片 / 电影片，用于预设卡副标题与分组
FILM_GROUPS = {
    'kodak_ektar_100': '彩色负片',
    'kodak_portra_160': '彩色负片',
    'kodak_portra_400': '彩色负片',
    'kodak_portra_800': '彩色负片',
    'kodak_portra_800_push1': '彩色负片',
    'kodak_portra_800_push2': '彩色负片',
    'kodak_gold_200': '彩色负片',
    'kodak_ultramax_400': '彩色负片',
    'kodak_vision3_50d': '电影负片',
    'kodak_vision3_250d': '电影负片',
    'kodak_verita_200d': '彩色负片',
    'kodak_vision3_200t': '电影负片',
    'kodak_vision3_500t': '电影负片',
    'fujifilm_pro_400h': '彩色负片',
    'fujifilm_c200': '彩色负片',
    'fujifilm_xtra_400': '彩色负片',
    'kodak_ektachrome_100': '彩色反转片',
    'kodak_kodachrome_64': '彩色反转片',
    'fujifilm_velvia_100': '彩色反转片',
    'fujifilm_provia_100f': '彩色反转片',
}

FILM_ISO = {
    'kodak_ektar_100': '100',
    'kodak_portra_160': '160',
    'kodak_portra_400': '400',
    'kodak_portra_800': '800',
    'kodak_portra_800_push1': '800 · 推一档',
    'kodak_portra_800_push2': '800 · 推两档',
    'kodak_gold_200': '200',
    'kodak_ultramax_400': '400',
    'kodak_vision3_50d': '50 · 日光型',
    'kodak_vision3_250d': '250 · 日光型',
    'kodak_verita_200d': '200 · 日光型',
    'kodak_vision3_200t': '200 · 灯光型',
    'kodak_vision3_500t': '500 · 灯光型',
    'fujifilm_pro_400h': '400',
    'fujifilm_c200': '200',
    'fujifilm_xtra_400': '400',
    'kodak_ektachrome_100': '100',
    'kodak_kodachrome_64': '64',
    'fujifilm_velvia_100': '100',
    'fujifilm_provia_100f': '100',
}

PAPER_BRANDS = {
    'kodak_ultra_endura': '柯达',
    'kodak_endura_premier': '柯达',
    'kodak_ektacolor_edge': '柯达',
    'kodak_supra_endura': '柯达',
    'kodak_portra_endura': '柯达',
    'fujifilm_crystal_archive_typeii': '富士',
    'kodak_2383': '柯达',
    'kodak_2393': '柯达',
}

PAPER_DISPLAY_NAMES = {
    'kodak_ultra_endura': '柯达 Ultra Endura',
    'kodak_endura_premier': '柯达 Endura Premier',
    'kodak_ektacolor_edge': '柯达 Ektacolor Edge',
    'kodak_supra_endura': '柯达 Supra Endura',
    'kodak_portra_endura': '柯达 Portra Endura',
    'fujifilm_crystal_archive_typeii': '富士 Crystal Archive Type II',
    'kodak_2383': '柯达 2383 电影印片',
    'kodak_2393': '柯达 2393 电影印片',
}

PAPER_NOTES = {
    'kodak_ultra_endura': '彩色相纸 · 通用',
    'kodak_endura_premier': '彩色相纸 · 专业',
    'kodak_ektacolor_edge': '彩色相纸 · 高反差',
    'kodak_supra_endura': '彩色相纸 · 人像',
    'kodak_portra_endura': '彩色相纸 · 人像',
    'fujifilm_crystal_archive_typeii': '彩色相纸 · 存档',
    'kodak_2383': '电影印片 · 标准',
    'kodak_2393': '电影印片 · 高光',
}


def film_display_name(value: str) -> str:
    return FILM_DISPLAY_NAMES.get(value, value.replace('_', ' ').strip() or value)


def paper_display_name(value: str) -> str:
    return PAPER_DISPLAY_NAMES.get(value, value.replace('_', ' ').strip() or value)


def profile_display_name(value: str, kind: str | None = None) -> str:
    if kind == 'print_paper':
        return paper_display_name(value)
    if kind == 'film_stock':
        return film_display_name(value)
    # 未声明时按已知表推断，未知值原样回退
    if value in FILM_DISPLAY_NAMES:
        return film_display_name(value)
    if value in PAPER_DISPLAY_NAMES:
        return paper_display_name(value)
    return value.replace('_', ' ').strip() or value


def film_brand(value: str) -> str:
    if value in FILM_BRANDS:
        return FILM_BRANDS[value]
    head = value.split('_', 1)[0].strip().lower()
    return {'kodak': '柯达', 'fujifilm': '富士', 'fuji': '富士'}.get(head, head)


def paper_brand(value: str) -> str:
    if value in PAPER_BRANDS:
        return PAPER_BRANDS[value]
    return film_brand(value)


# ── 参数友好名（基础面板）────────────────────────────────────────

PARAM_LABELS = {
    # 光线
    'print_exposure': '亮度',
    'film_gamma_factor': '对比度',
    'exposure_compensation_ev': '曝光补偿',
    'print_exposure_compensation': '自动亮度补偿',
    'auto_exposure': '自动测光',
    'auto_exposure_method': '测光方式',
    'developer_exhaustion': '高光柔化',
    # 色彩
    'print_y_filter_shift': '色温',
    'print_m_filter_shift': '色调',
    'inhibition_interlayer': '色彩浓度',
    'inhibition_samelayer': '层次反差',
    'gamma_factor': '印相对比度',
    'gamma_factor_red': '红色反差',
    'gamma_factor_green': '绿色反差',
    'gamma_factor_blue': '蓝色反差',
    'gamma_factor_fast': '快层反差',
    'gamma_factor_slow': '慢层反差',
    # 质感
    'active': '启用',
    'halation_amount': '光晕强度',
    'halation_spatial_scale': '光晕范围',
    'scatter_amount': '乳剂柔化',
    'scatter_spatial_scale': '柔化范围',
    'boost_ev': '高光提升',
    'protect_ev': '高光保护',
    'boost_range': '提升过渡',
    'particle_area_um2': '颗粒大小',
    'particle_scale': '三层颗粒比例',
    'particle_scale_layers': '子层颗粒比例',
    'density_min': '颗粒底密度',
    'uniformity': '颗粒均匀度',
    'blur': '柔化',
    'blur_dye_clouds_um': '染料云柔化',
    'micro_structure': '微观颗粒结构',
    'sublayers_active': '分层颗粒',
    'strength': '柔光强度',
    'filter_family': '柔光类型',
    'spatial_scale': '柔光范围',
    'halo_warmth': '光晕暖度',
    'core_intensity': '核心亮度',
    'core_size': '核心大小',
    'halo_intensity': '光晕亮度',
    'halo_size': '光晕大小',
    'bloom_intensity': '泛光亮度',
    'bloom_size': '泛光大小',
    'percent': '眩光强度',
    'roughness': '眩光粗糙度',
    # 印相 / 扫描
    'white_correction': '白场校正',
    'black_correction': '黑场校正',
    'white_level': '白场',
    'black_level': '黑场',
    'unsharp_mask': '锐化',
    'lens_blur': '镜头柔化',
    'scan_film': '查看底片',
    'preflash_exposure': '预闪曝光',
    'y_filter_shift': '预闪色温',
    'm_filter_shift': '预闪色调',
    'print_illuminant': '印相光源',
    'film_stock': '胶片',
    'print_paper': '相纸',
    # 输入 / 输出
    'input_color_space': '输入色彩空间',
    'output_color_space': '输出色彩空间',
    'saving_color_space': '保存色彩空间',
    'saving_cctf_encoding': '保存亮度编码',
    'input_cctf_decoding': '输入伽马解码',
    'upscale_factor': '放大倍率',
    'crop': '裁剪',
    'crop_center': '裁剪中心',
    'crop_size': '裁剪范围',
    'film_format_mm': '画幅',
    'spectral_gaussian_blur': '光谱平滑',
    'rgb_to_raw_method': '光谱重建方式',
    'apply_hanatos2025_adaptation_window': '光谱适应窗',
    'apply_hanatos2025_adaptation_surface': '光谱适应面',
    'input_gamut_compress': '输入色域压缩',
    'output_gamut_compress': '输出色域压缩',
    'algorithm': '方式',
    'knee': '压缩拐点',
    # 显示
    'use_display_transform': '使用系统色彩显示',
    'gray_18_canvas': '18% 灰背景',
    'white_padding': '白边留白',
    'preview_max_size': '预览尺寸',
    'output_interpolation': '预览插值',
    'film_channel_swap': '胶片通道互换',
    'print_channel_swap': '印相通道互换',
    'auto_preview': '自动预览',
    'amount': '强度',
}

# 专业面板精确名（覆盖基础友好名；没有条目则回退到 i18n/原始标签）
TECHNICAL_LABELS = {
    'print_exposure': '印相曝光',
    'film_gamma_factor': '胶片伽马系数',
    'print_y_filter_shift': '印相 Y 滤镜偏移（黄）',
    'print_m_filter_shift': '印相 M 滤镜偏移（品红）',
    'inhibition_interlayer': '层间抑制',
    'inhibition_samelayer': '同层抑制',
    'gamma_factor': '印相伽马系数',
    'particle_area_um2': '颗粒面积（平方微米）',
    'halation_amount': '光晕强度系数',
    'strength': '强度档位',
    'developer_exhaustion': '显影液疲劳',
    'white_level': '白场目标',
    'black_level': '黑场目标',
    'unsharp_mask': '扫描锐化（USM）',
    'lens_blur': '镜头/扫描柔化',
    'film_format_mm': '画幅长边（毫米）',
    'white_padding': '白边宽度',
    'upscale_factor': '放大倍率',
    'crop_center': '裁切中心',
    'crop_size': '裁切范围',
    'diffusion_size_um': '染色扩散（微米）',
    'preflash_y_filter_shift': '预闪 Y 滤镜偏移',
    'preflash_m_filter_shift': '预闪 M 滤镜偏移',
    'lens_blur_um': '拍摄镜头柔化（微米）',
    'white_balance': '白平衡',
    'temperature': '色温',
    'tint': '色调',
    'lens_correction': '镜头校正',
    'scatter_core_um': '散射核心（微米）',
    'scatter_tail_um': '散射尾部（微米）',
    'scatter_tail_weight': '散射尾部权重',
    'halation_strength': '光晕反射强度',
    'halation_first_sigma_um': '光晕首跳扩散（微米）',
    'halation_n_bounces': '光晕反射次数',
    'halation_bounce_decay': '光晕反射衰减',
    'halation_renormalize': '光晕亮度归一',
    'gamma_samelayer_rgb': '同层伽马（RGB）',
    'gamma_interlayer_r_to_gb': 'R→G/B 层间伽马',
    'gamma_interlayer_g_to_rb': 'G→R/B 层间伽马',
    'gamma_interlayer_b_to_rg': 'B→R/G 层间伽马',
}

# 基础面板提示语：解释“动了会怎样”，不堆物理术语
PARAM_TIPS = {
    'print_exposure': '向右提亮、向左压暗，按档调节（±2 档）；0 档是当前胶片相纸的标准曝光。',
    'film_gamma_factor': '胶片反差。数值越大，明暗对比越强；越小越柔和。',
    'exposure_compensation_ev': '提亮或压暗拍摄曝光。「自动亮度补偿」开启时只改变亮暗部层次；关闭后才会改变整体亮度。',
    'print_exposure_compensation': '相机曝光变化时，自动跟着调整印相亮度。',
    'auto_exposure': '让模拟相机自动决定曝光。',
    'auto_exposure_method': '自动测光时重点参考画面的哪个区域。',
    'developer_exhaustion': '数值越高，亮部越柔、越不容易死白。',
    'print_y_filter_shift': '往左偏冷（蓝），往右偏暖（黄）。',
    'print_m_filter_shift': '往左偏绿，往右偏品红。',
    'inhibition_interlayer': '色彩浓度。数值越高，颜色越浓、越鲜艳。',
    'inhibition_samelayer': '每一层的反差强弱，影响整体层次。',
    'gamma_factor': '印相阶段的整体反差。',
    'halation_amount': '高光周围的红橙色光晕，数值越大越明显。',
    'halation_spatial_scale': '光晕扩散的范围。',
    'scatter_amount': '乳剂内部的柔光，让画面不那么锐利。',
    'boost_ev': '额外提亮高光的幅度。',
    'particle_area_um2': '颗粒粗细。数值越大，颗粒越明显。自动预览不渲染颗粒，点「生成全尺寸」查看。',
    'blur': '颗粒的柔化程度。自动预览不渲染颗粒，点「生成全尺寸」查看。',
    'strength': '柔光镜的档位，数值越大高光越柔。',
    'filter_family': '选择柔光镜的性格：白柔、黑柔、微光或电影柔光。',
    'halo_warmth': '光晕偏暖还是偏冷。',
    'white_level': '扫描时认定的白场亮度。需开启「白场校正」后生效。',
    'black_level': '扫描时认定的黑场亮度。需开启「黑场校正」后生效。',
    'white_correction': '按白场目标校正扫描结果。',
    'black_correction': '按黑场目标校正扫描结果。',
    'scan_film': '查看未印相的底片，而不是最终照片。',
    'unsharp_mask': '扫描后的锐化强度。',
    'lens_blur': '镜头或扫描仪的柔化程度。自动预览不渲染，点「生成全尺寸」查看。',
    'preflash_exposure': '印相前给相纸一次微弱预曝光，保住高光。',
    'film_format_mm': '模拟的画幅长边，例如 35mm、60mm。主要影响颗粒、柔化与光晕的物理尺度。',
    'input_cctf_decoding': '输入文件带伽马编码时，先解码成线性光。',
    'saving_cctf_encoding': '保存文件时写入伽马编码，方便普通软件查看。',
    'output_interpolation': '预览放大时使用的插值方式。',
    'auto_preview': '每次改参数后自动重新计算小图预览。',
    'use_display_transform': '用系统色彩管理把结果映射到当前屏幕。',
    'gray_18_canvas': '用 18% 灰作为画布背景，方便判断曝光。',
    'white_padding': '在照片外围留一圈白边。',
    'preview_max_size': '预览图最长边的像素数。',
    'crop': '只计算画面的一部分，用来快速看细节。',
    'crop_center': '裁剪区域在画面中的中心位置。',
    'crop_size': '裁剪区域占画面的比例。',
    'upscale_factor': '把输入放大后再模拟。预览图受预览尺寸限制，生成全尺寸后更明显。',
    'percent': '眩光雾的强度，越大黑位越浮、画面越不透。',
    'roughness': '眩光噪点的粗粝感。把「眩光」强度调大才看得明显。',
    'film_channel_swap': '交换胶片的三色通道，通常保持 0、1、2。',
    'print_channel_swap': '交换印相的三色通道，通常保持 0、1、2。',
    # 专业面板补充（按叶子名，避免英文提示）
    'active': '打开或关闭这一项效果。',
    'algorithm': '选择这一项使用的处理方式。',
    'amount': '整体强度倍率，1.0 保持默认。',
    'apply_hanatos2025_adaptation_surface': '光谱重建时启用表面适应修正。',
    'apply_hanatos2025_adaptation_window': '光谱重建时启用带通适应窗。',
    'bloom_intensity': '柔光泛光的亮度。',
    'bloom_size': '柔光泛光的范围。',
    'blur_dye_clouds_um': '染料云的柔化半径，越大越柔。自动预览不渲染，点「生成全尺寸」查看。',
    'boost_range': '高光提升从开始到完全的过渡范围。',
    'core_intensity': '柔光核心的亮度。',
    'core_size': '柔光核心的大小。',
    'density_min': '颗粒的最小密度，越大底子越脏。',
    'diffusion_size_um': '成色剂扩散半径，影响锐度与饱和。自动预览不渲染，点「生成全尺寸」查看。',
    'film_stock': '选择要模拟的胶片型号。',
    'gamma_factor_red': '红色通道的印相反差。',
    'gamma_factor_green': '绿色通道的印相反差。',
    'gamma_factor_blue': '蓝色通道的印相反差。',
    'gamma_factor_fast': '快层的印相反差。',
    'gamma_factor_slow': '慢层的印相反差。',
    'gamma_interlayer_r_to_gb': '红层对绿、蓝层的抑制强度。',
    'gamma_interlayer_g_to_rb': '绿层对红、蓝层的抑制强度。',
    'gamma_interlayer_b_to_rg': '蓝层对红、绿层的抑制强度。',
    'gamma_samelayer_rgb': '三层各自的同层抑制强度。',
    'halation_bounce_decay': '光晕多次反射之间的衰减比例。',
    'halation_first_sigma_um': '光晕第一次反射的扩散半径。',
    'halation_n_bounces': '光晕反射的次数。',
    'halation_renormalize': '光晕后归一化，保持中灰亮度不变。',
    'halation_strength': '各颜色通道的光晕强度。',
    'halo_intensity': '柔光光晕的亮度。',
    'halo_size': '柔光光晕的大小。',
    'input_color_space': '输入文件使用的色彩空间。',
    'knee': '压缩曲线开始弯曲的位置。',
    'lens_blur_um': '镜头或扫描仪的柔化半径。自动预览不渲染，点「生成全尺寸」查看。',
    'micro_structure': '微观颗粒结构，只在极高倍率下可见。',
    'output_color_space': '输出文件使用的色彩空间。',
    'particle_scale': '三层颗粒大小的倍率。',
    'particle_scale_layers': '每个子层颗粒大小的倍率。',
    'percent': '眩光强度。',
    'preflash_m_filter_shift': '预闪时品红滤镜的偏移。',
    'preflash_y_filter_shift': '预闪时黄滤镜的偏移。',
    'print_illuminant': '模拟放大机使用的光源。',
    'print_paper': '选择要模拟的相纸型号。',
    'protect_ev': '高光保护从哪个亮度开始生效。',
    'rgb_to_raw_method': '把 RGB 还原成光谱所用的算法。',
    'roughness': '眩光的粗糙程度。',
    'saving_color_space': '保存文件时使用的色彩空间。',
    'scatter_core_um': '乳剂散射核心的半径。',
    'scatter_tail_um': '乳剂散射拖尾的长度。',
    'scatter_tail_weight': '散射拖尾所占的比重。',
    'spatial_scale': '这一项效果的空间尺度。',
    'spectral_gaussian_blur': '光谱曲线的平滑半径。',
    'sublayers_active': '启用分层颗粒结构。',
    'uniformity': '颗粒分布的均匀程度。',
    'white_balance': '解码 RAW 时使用的白平衡。',
    'temperature': '自定义白平衡的色温，单位开尔文。',
    'tint': '自定义白平衡的色调偏移。',
    'lens_correction': '解码 RAW 时应用镜头校正。',
    'scan_for_print': '扫描时启用白场/黑场校正并关闭眩光。',
    'scatter_spatial_scale': '乳剂散射的空间范围。',
}

_SECTION_LABELS = {
    'import rgb': '导入图片',
    'import raw': '导入 RAW',
    'input': '输入',
    'camera': '相机',
    'profiles': '胶片与相纸',
    'exposure control': '曝光',
    'enlarger': '放大机',
    'scanner': '扫描',
    'preview and crop': '预览与裁剪',
    'crop and upscale': '裁剪与放大',
    'output': '输出',
    'grain': '颗粒',
    'halation': '光晕',
    'couplers': '色彩层次',
    'chemistry': '印相化学',
    'glare': '眩光',
    'preflash': '预闪',
    'diffusion': '柔光',
    'spectral upsampling': '光谱重建',
    'input gamut compress': '输入色域压缩',
    'output gamut compress': '输出色域压缩',
    'tune': '微调',
    'experimental': '实验参数',
    'gui parameters': '界面参数',
    'display': '显示',
    'napari layers': '图层',
    'film': '胶片',
    'print': '印相',
    'develop': '显影',
    'spectral': '光谱',
}


def section_label(text: str) -> str:
    return _SECTION_LABELS.get(text.strip().lower(), text)


def label_for(leaf: str, fallback: str | None = None) -> str:
    return PARAM_LABELS.get(leaf) or fallback or leaf.replace('_', ' ')


def technical_label_for(leaf: str, fallback: str | None = None) -> str:
    return TECHNICAL_LABELS.get(leaf) or PARAM_LABELS.get(leaf) or fallback or leaf.replace('_', ' ')


def tip_for(leaf: str, fallback: str = '') -> str:
    return PARAM_TIPS.get(leaf) or fallback


# ── 枚举中文名（只影响显示，currentText 仍是原值）────────────────

ENUM_LABELS = {
    'AutoExposureMethods': {
        'center_weighted': '中央重点测光',
        'matrix': '矩阵测光',
        'multi_zone': '多区测光',
        'partial': '局部测光',
        'highlight_weighted': '高光重点测光',
        'median': '中值测光',
        'average': '平均测光',
    },
    'DiffusionFilterFamilies': {
        'glimmerglass': '微光镜',
        'black_pro_mist': '黑柔镜',
        'pro_mist': '白柔镜',
        'cinebloom': '电影柔光镜',
    },
    'RawWhiteBalance': {
        'as_shot': '拍摄时白平衡',
        'daylight': '日光',
        'tungsten': '钨丝灯',
        'custom': '自定义',
    },
    'InputGamutCompressAlgorithms': {
        'xy': '色度坐标压缩',
        'oklch': '感知色度压缩',
    },
    'OutputGamutCompressAlgorithms': {
        'off': '关闭',
        'oklch': '感知色度压缩',
        'aces_rgc': '电影工业标准压缩',
        'oklrab': '感知色度压缩（进阶）',
        'jzazbz': '高动态色度压缩',
        'cam16ucs': '均匀色度压缩',
    },
    'NapariInterpolationModes': {
        'nearest': '最近邻',
        'linear': '双线性',
        'cubic': '双三次',
        'spline16': '样条 16',
        'spline36': '样条 36',
        'lanczos': '兰索斯',
        'blackman': '布莱克曼',
    },
    'RGBtoRAWMethod': {
        'hanatos2025': '全可见光重建',
        'mallett2019': 'sRGB 范围重建',
    },
    'Illuminants': {
        'TH-KG3': 'TH-KG3 标准印相光源',
    },
}


def enum_display(enum_name: str | None, value: str) -> str:
    if not enum_name:
        return value
    return ENUM_LABELS.get(enum_name, {}).get(value, value)


# 品牌筛选胶囊
def brand_sort_key(brand: str) -> tuple[int, str]:
    order = {'柯达': 0, '富士': 1}
    return (order.get(brand, 9), brand)
