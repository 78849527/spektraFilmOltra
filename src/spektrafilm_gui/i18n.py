"""界面中文化。

只翻译**显示文本**：面板标题、字段标签、按钮、分页、页眉。
参数键名（dotted path）、枚举值、配置文件格式一律不动，
因此序列化、profile 同步、导出结果都不受影响。
"""

from __future__ import annotations

# 面板 / 分组标题
_TITLES = {
    'import rgb': '导入图片',
    'import raw': '导入 RAW',
    'raw decoding': 'RAW 解码设置',
    'input': '输入',
    'camera': '相机',
    'profiles': '胶片与相纸',
    'exposure control': '曝光控制',
    'enlarger': '放大机',
    'scanner': '扫描仪',
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
    'spectral upsampling': '光谱上采样',
    'input gamut compress': '输入色域压缩',
    'output gamut compress': '输出色域压缩',
    'tune': '微调',
    'experimental': '实验',
    'gui parameters': '界面参数',
    'display': '显示',
    'napari layers': '图层',
    'film': '胶片',
    'print': '印相',
    'develop': '显影',
    'spectral': '光谱',
}

# 字段标签
_FIELDS = {
    # 胶片 / 相纸选择
    'film profile': '胶片型号',
    'print profile': '相纸型号',
    'print illuminant': '印相光源',
    # 曝光
    'exposure': '曝光',
    'exposure_compensation_ev': '曝光补偿',
    'print exposure': '印相曝光',
    'print auto compensation': '印相自动补偿',
    'auto_exposure': '自动曝光',
    'auto exposure': '自动曝光',
    'auto_exposure_method': '自动测光方式',
    'auto exposure method': '自动测光方式',
    'white balance': '白平衡',
    'temperature': '色温',
    'tint': '色调',
    'lens correction': '镜头校正',
    'boost_ev': '提升曝光',
    'boost_range': '提升范围',
    'protect_ev': '保护曝光',
    'knee': '拐点',
    # 输入 / 输出
    'input color space': '输入色彩空间',
    'output color space': '输出色彩空间',
    'output interpolation': '输出插值',
    'apply cctf decoding': '输入亮度解码',
    'saving cctf encoding': '保存亮度编码',
    'saving color space': '保存色彩空间',
    'upscale factor': '放大倍率',
    'preview max size': '预览最大边长',
    'film format_mm': '画幅 (mm)',
    'film_format_mm': '画幅 (mm)',
    'crop': '裁剪',
    'crop center': '裁剪中心',
    'crop size': '裁剪尺寸',
    'percent': '百分比',
    # 放大机
    'print y filter shift': '印相黄滤镜偏移',
    'print m filter shift': '印相品红滤镜偏移',
    'y filter shift': '预闪黄滤镜偏移',
    'm filter shift': '预闪品红滤镜偏移',
    'film channel swap': '胶片通道互换',
    'print channel swap': '印相通道互换',
    'developer exhaustion': '显影液疲劳',
    'gamma factor': '印相反差',
    'gamma factor red': '红色反差',
    'gamma factor green': '绿色反差',
    'gamma factor blue': '蓝色反差',
    'gamma factor fast': '快层反差',
    'gamma factor slow': '慢层反差',
    'film gamma factor': '胶片反差',
    'density_min': '最小密度',
    'filter_family': '滤镜系列',
    # 扫描仪
    'white_correction': '白场校正',
    'black_correction': '黑场校正',
    'white_level': '白场',
    'black_level': '黑场',
    'uniformity': '均匀度',
    'unsharp_mask': '扫描锐化',
    'lens_blur': '镜头模糊',
    'lens_blur_um': '镜头模糊 (µm)',
    'scan film': '扫描负片',
    # 光晕 / 散射
    'active': '启用',
    'amount': '强度',
    'strength': '强度',
    'halation_amount': '光晕强度',
    'halation_strength': '光晕强度',
    'halation_spatial_scale': '光晕空间尺度',
    'halation_bounce_decay': '光晕回弹衰减',
    'halation_first_sigma_um': '光晕首次散射 σ (µm)',
    'halation_n_bounces': '光晕回弹次数',
    'halation_renormalize': '光晕能量归一',
    'scatter_amount': '散射强度',
    'scatter_spatial_scale': '散射空间尺度',
    'scatter_core_um': '散射核心 (µm)',
    'scatter_tail_um': '散射拖尾 (µm)',
    'scatter_tail_weight': '拖尾权重',
    'spatial_scale': '空间尺度',
    'halo_intensity': '光晕强度',
    'halo_size': '光晕尺寸',
    'halo_warmth': '光晕暖度',
    'core_intensity': '核心强度',
    'core_size': '核心尺寸',
    'bloom_intensity': '泛光强度',
    'bloom_size': '泛光尺寸',
    # 成色剂
    'inhibition_samelayer': '同层抑制',
    'inhibition_interlayer': '层间抑制',
    'gamma_samelayer_rgb': '同层反差（三色）',
    'gamma_interlayer_r_to_gb': '层间反差（红→绿蓝）',
    'gamma_interlayer_g_to_rb': '层间反差（绿→红蓝）',
    'gamma_interlayer_b_to_rg': '层间反差（蓝→红绿）',
    'diffusion_size_um': '扩散尺寸 (µm)',
    # 颗粒
    'particle_area_um2': '颗粒面积 (µm²)',
    'particle_scale': '颗粒尺度',
    'particle_scale_layers': '分层颗粒尺度',
    'blur_dye_clouds_um': '染料云模糊 (µm)',
    'micro_structure': '微观结构',
    'roughness': '粗糙度',
    'sublayers_active': '启用子层',
    'blur': '模糊',
    # 显示
    'use display transform': '使用显示变换',
    'gray 18% canvas': '18% 灰画布',
    'white padding': '白边留白',
    'algorithm': '算法',
    'hanatos2025 adaptation surface': '光谱适应面（2025 法）',
    'hanatos2025 adaptation window': '光谱适应窗（2025 法）',
    # 动作
    'auto preview': '自动预览',
    'spectral gaussian blur': '光谱高斯模糊',
    'spectral upsampling': '光谱上采样',
}

# 按钮 / 分页 / 页眉
_UI = {
    'preview': '预览',
    'scan': '扫描',
    'save': '保存',
    'update': '更新',
    'select file': '选择文件',
    'reprocess raw': '重新解码 RAW',
    'save current as default': '当前存为默认',
    'load from file': '从文件载入',
    'restore factory default': '恢复出厂默认',
    'expose': '曝光',
    'print': '印相',
    'output': '输出',
    'config': '配置',
    'develop': '显影',
    'spectral film simulation': '光谱胶片模拟',
}

_TABLE = {}
_TABLE.update(_TITLES)
_TABLE.update(_FIELDS)
_TABLE.update(_UI)


def translate(text: str) -> str | None:
    """返回中文译文；没有对应词条时返回 None（调用方保留原文）。"""
    if not text:
        return None
    key = text.strip().lower()
    for candidate in (key, key.replace(' ', '_'), key.replace('_', ' ')):
        translated = _TABLE.get(candidate)
        if translated is not None:
            return translated
    return None


def tr(text: str) -> str:
    """有译文用译文，没有就原样返回。"""
    return translate(text) or text


# 按钮与面板级提示语（字段级长说明保留英文原文，避免物理表述误译）
_TOOLTIPS = {
    'run the simulation on a small preview and deactivates grain, halation, blurs, unsharp mask (diffusion filters are active)':
        '在小尺寸预览上运行模拟，暂时关闭颗粒、光晕、模糊与锐化（扩散滤镜仍然生效）',
    'run the full simulation on the full-resolution input':
        '在全分辨率输入上运行完整模拟',
    'save the current output layer to an image file':
        '把当前输出图层保存为图像文件',
    'load and process a raw file using rawpy, output colorspace and cctf as defined in current input widget state':
        '用 rawpy 载入并处理 RAW 文件，输出色彩空间与 CCTF 按当前输入面板的设置',
    'film stock to simulate': '要模拟的胶片型号',
    'print paper to simulate': '要模拟的相纸型号',
    'print illuminant to simulate': '要模拟的印相光源',
    'enable halation and in-emulsion scatter.': '启用光晕与乳剂内散射。',
    'enable dir coupler inhibition.': '启用 DIR 成色剂抑制。',
    'auto adjust the print exposure for the camera exposure compensation ev':
        '按相机曝光补偿自动调整印相曝光',
    'changes the exposure time set in the virtual enlarger': '调整虚拟放大机的曝光时间',
    'white balance used when decoding the raw file': '解码 RAW 文件时使用的白平衡',
    'run the simulation on a small preview': '在小尺寸预览上运行模拟',
    'restore factory default gui state': '恢复出厂默认的界面参数',
    'save the current gui state as the startup default': '把当前界面参数保存为启动默认',
    'save the current gui state to a json file': '把当前界面参数保存为 JSON 文件',
    'load gui state from a json file': '从 JSON 文件载入界面参数',
}


def tr_tooltip(text: str) -> str:
    """提示语翻译；词条未覆盖的保留原文。"""
    if not text:
        return text
    return _TOOLTIPS.get(text.strip().lower()) or _TOOLTIPS.get(text.strip()) or text
