# Spektrafilm 第三步 · 调色台 Spec

## 1. 目标

在 `OltraFilm` 分支上把第二步的调色台占位页替换为可用的 Lightroom 式调色台：

- 输入：第二步已生成的 16-bit TIFF / ProPhoto RGB / 线性交接图
- 左栏：LUT + 预设
- 中间：调色预览
- 右栏：直方图 + 「光影 / 色彩」Tab + 下方「通透 / 画质 / 光学」折叠区
- 配方持久化到 `LibraryItem.state['grade']['recipe']`
- 导出当前配方结果，默认文件名 `{name}_graded`

算法蓝本：

- 通透：直接移植 oflim `Shaders.metal` 的明暗通透（直方图黑/白场 Levels）与颜色通透（高光/阴影互补色中和）
- 影调/色彩/画质公式：RapidRAW（AGPL-3.0）技术文档中的对比度、阴影/黑场、饱和度/自然饱和度、HSL 8 色带、clarity/structure、去雾、两尺度 USM、暗角
- 不引入任何 C++ / Rust / WGSL 运行时；全部用 NumPy/SciPy 在 Python 内重写

## 2. 非目标

- 不做局部蒙版、画笔、径向/线性渐变
- 不做裁切/旋转/镜头校正几何变换（v1 不进入调色台）
- 不做历史撤销栈（v1 先保证配方与预览正确；撤销可在后续版本加）
- 不改变显影台现有快速/专业参数与渲染管线
- 不把调色结果写回交接图

## 3. 输入与输出

### 输入

`handoff_path(item_id)` 指向的 TIFF：

- `uint16`、ProPhoto RGB primaries、线性（无 CCTF）、内嵌 ICC
- 读取后立即转为 `float32`，避免 float64 常驻内存

### 输出

- 预览：sRGB 编码、`float32`、`0..1`，长边上限 1600 px
- 全尺寸导出：sRGB 编码、`float32`、`0..1`，由 `save_image_oiio` 编码
- 配方：JSON 可序列化，写入 `state['grade']['recipe']`

### 恒等约定

默认配方（全部中性）只做「线性 ProPhoto → 线性 sRGB → sRGB 编码」的色彩空间转换，不再改动像素；测试以这条为恒等基准。

## 4. 文件清单

### 新增

| 文件 | 职责 |
| --- | --- |
| `src/spektrafilm_gui/grade_recipe.py` | `GradeRecipe` 及子结构、默认值、范围校验、`to_dict/from_dict`、`is_identity` |
| `src/spektrafilm_gui/grade_engine.py` | 色彩空间转换、影调/色彩/通透/画质/光学/LUT 渲染、`analyze_tone`、`.cube` 解析 |
| `src/spektrafilm_gui/grade_worker.py` | `QRunnable` 预览/全尺寸渲染线程，signals + generation id |
| `src/spektrafilm_gui/grade_presets.py` | 内置/用户预设读写、导入导出 |
| `tests/gui/test_grade_recipe.py` | 配方模型测试 |
| `tests/gui/test_grade_engine.py` | 引擎方向/恒等/极值/通透/LUT 测试 |
| `tests/gui/test_grade_page.py` | 调色台 UI 与信号测试 |
| `tests/gui/test_grade_presets.py` | 预设库测试 |

### 重写

| 文件 | 改动 |
| --- | --- |
| `src/spektrafilm_gui/grade_page.py` | 占位页 → 完整调色台（顶栏 / 左 LUT+预设栏 / 中预览 / 右参数台） |

### 修改

| 文件 | 改动 |
| --- | --- |
| `src/spektrafilm_gui/handoff.py` | 新增 `read_grade_recipe`、`write_grade_recipe`，保留 handoff 信息 |
| `src/spektrafilm_gui/controller.py` | 新增 `export_graded_image(image, direct=False)` |
| `src/spektrafilm_gui/workspace.py` | 调色台加载/配方防抖保存/导出代理/页面往返 |
| `src/spektrafilm_gui/theme_shell.py` | 如需要，补 `gradeTopBar` / `gradeRail` / `gradeDeck` 的 QSS；优先在页面内自带样式 |
| `tests/gui/test_workspace.py` | 适配调色台进入路径（当前 fake handoff 不是真实 TIFF，页面需容错） |

## 5. 配方模型（`grade_recipe.py`）

顶层：

```python
@dataclass(slots=True)
class GradeRecipe:
    schema: int = 1
    light: LightRecipe
    color: ColorRecipe
    transparency: TransparencyRecipe
    quality: QualityRecipe
    optics: OpticsRecipe
    lut: LutRecipe
    def is_identity(self) -> bool
    def to_dict(self) -> dict
    @classmethod from_dict(cls, data) -> GradeRecipe
```

### LightRecipe（光影）

| 字段 | 范围 | 默认 | 语义 |
| --- | --- | --- | --- |
| `exposure` | -5..5 | 0 | EV，线性域乘 `2**ev` |
| `contrast` | -100..100 | 0 | S 曲线对比度 |
| `highlights` | -100..100 | 0 | 高光 |
| `shadows` | -100..100 | 0 | 阴影 |
| `whites` | -100..100 | 0 | 白场 |
| `blacks` | -100..100 | 0 | 黑场 |
| `midtones` | -100..100 | 0 | 中间调 |
| `highlight_rolloff` | 0..100 | 0 | 高光过渡/滚降 |
| `curve_highlights` | -100..100 | 0 | 参数曲线高光 |
| `curve_lights` | -100..100 | 0 | 参数曲线亮调 |
| `curve_darks` | -100..100 | 0 | 参数曲线暗调 |
| `curve_shadows` | -100..100 | 0 | 参数曲线阴影 |

### ColorRecipe（色彩）

| 字段 | 范围 | 默认 | 语义 |
| --- | --- | --- | --- |
| `temperature` | -100..100 | 0 | 冷暖，线性域 R/B 增益 |
| `tint` | -100..100 | 0 | 绿/品红 |
| `vibrance` | -100..100 | 0 | 自然饱和度（按现有饱和度衰减） |
| `saturation` | -100..100 | 0 | 总饱和度 |
| `hue_shift` | -180..180 | 0 | 全局色相旋转 |
| `color_density` | 0..100 | 0 | 色彩浓度/分离度 |
| `hsl` | 8 个 `HslBand` | 全 0 | 8 色带色相/饱和度/明度 |
| `grading` | `ColorGrading` | 全中性 | 三区颜色分级 |

`HslBand`：`hue -100..100`、`saturation -100..100`、`luminance -100..100`，顺序固定：

`red(358°), orange(25°), yellow(60°), green(115°), aqua(180°), blue(225°), purple(280°), magenta(330°)`

`ColorGrading`：

- `shadows/midtones/highlights: GradeZone(hue 0..360, saturation 0..100, luminance -100..100)`
- `blending 0..100` 默认 50
- `balance -100..100` 默认 0

### TransparencyRecipe（通透）

| 字段 | 范围 | 默认 |
| --- | --- | --- |
| `tonal` | 0..100 | 0 |
| `color` | 0..100 | 0 |

### QualityRecipe（画质）

| 字段 | 范围 | 默认 |
| --- | --- | --- |
| `clarity` | -100..100 | 0 |
| `texture` | -100..100 | 0 |
| `dehaze` | -100..100 | 0 |
| `sharpen_amount` | 0..100 | 0 |
| `sharpen_radius` | 0.5..3.0 | 1.0 |
| `sharpen_threshold` | 0..100 | 0 |
| `noise_luminance` | 0..100 | 0 |
| `noise_color` | 0..100 | 0 |

### OpticsRecipe（光学）

| 字段 | 范围 | 默认 |
| --- | --- | --- |
| `vignette_amount` | -100..100 | 0 |
| `vignette_midpoint` | 0..100 | 50 |
| `vignette_roundness` | -100..100 | 0 |
| `vignette_feather` | 0..100 | 50 |
| `grain_amount` | 0..100 | 0 |
| `grain_size` | 0..100 | 25 |
| `grain_roughness` | 0..100 | 50 |
| `chromatic_aberration` | 0..100 | 0 |

### LutRecipe

- `path: str = ''`
- `strength: 0..100 = 100`

### 序列化规则

- `from_dict` 对未知键忽略、缺失键取默认、越界钳制、类型错误回退默认
- `hsl` 长度不足补 8 个默认 band，超出截断
- `is_identity()`：所有数值等于默认、所有 HSL/分级 zone 中性、`lut.path` 为空

## 6. 引擎（`grade_engine.py`）

### 6.1 色彩空间

常量矩阵：

- `PPRO_TO_XYZ_D50`（ROMM RGB → XYZ D50）
- `XYZ_D50_TO_SRGB_D65`（Bradford 适配后的线性 sRGB）
- `LUMA_REC709 = (0.2126, 0.7152, 0.0722)`

函数：

```python
def prepare_source(prophoto_linear: np.ndarray) -> np.ndarray   # 线性 sRGB float32
def srgb_encode(linear) -> np.ndarray
def srgb_decode(encoded) -> np.ndarray
def load_handoff_image(path) -> np.ndarray                      # float32 线性 ProPhoto
def downsample_linear(image, max_long_edge) -> np.ndarray       # skimage resize 抗锯齿
def analyze_tone(display_image) -> ToneAnalysis
def render(source_linear_srgb, recipe, analyze=True) -> (display_image, ToneAnalysis)
```

`ToneAnalysis`：

```python
black_point: float       # 亮度直方图 0.4% 分位
white_point: float       # 99.6% 分位
highlight_rgb: tuple
shadow_rgb: tuple
highlight_cast: str      # 偏红/偏黄/.../中性
shadow_cast: str
summary: str             # "黑场 2.1% · 白场 97.4% · 高光偏黄 · 阴影偏绿"
```

### 6.2 管线顺序

1. 线性域：曝光 `×2**ev` → 白平衡 R/G/B 增益
2. `srgb_encode`
3. 对比度 → 高光/阴影/白场/黑场/中间调 → 高光过渡 → 参数曲线
4. 自然饱和度/饱和度/色彩密度 → 全局色相偏移
5. HSL 8 色带（高斯权重归一化）
6. 三区颜色分级
7. **通透**：
   - 明暗通透：取当前画面亮度 0.4%/99.6% 作为黑/白场，`leveled=(enc-black)/(white-black)`，`mix`
   - 颜色通透：高光/阴影平均 RGB 求互补 delta，按亮度 mask 加回
8. 清晰度/纹理（log2 亮度，高斯基底，detail 限幅）
9. 去雾（暗通道 + airlight）
10. 亮度/色彩降噪
11. 两尺度 USM 锐化
12. 光学：暗角 → 色差 → 颗粒
13. LUT（sRGB 编码域，三线性插值，按 strength 混合）
14. 裁剪到 `0..1`，`nan_to_num`

所有步骤在默认参数下必须是数值恒等（除色彩空间转换）。

### 6.3 关键公式

- 对比度：`p^(1/2.2)` 域，`s=2**(1.25*contrast/100)`，`p'=0.5*(2p)**s` / `1-0.5*(2(1-p))**s`
- 阴影/黑场 lift：`(slider/100)*k*Y*(1-Y)**n`
- 饱和度：`rgb = Y + (rgb-Y)*(1+saturation/100)*(1+vibrance/100*(1-S)**1.25)`
- HSL：8 个中心色相，`sigma≈24°`，权重归一化；色相 ±30°、饱和 ±50%、明度 ±15%
- clarity/structure：
  - `I=log2(max(Y,1e-4))`
  - `base=gaussian_filter(I, radius)`
  - `detail=I-base`
  - `shape(d)=d/(1+(d/sigma)**2)`
  - `rgb *= 2**(amount*0.5*shape)`
  - clarity 半径按短边 0.008，texture 半径 0.003
- 去雾：
  - 正：`strength=1-(1-amount/100)**2`，`dark=min(RGB)`，`A=percentile(Y,99)`，`t=clip(1-strength*0.95*dark/A,0.1,1)`，`J=A+(I-A)/t`
  - 负：抬黑 + 降对比
- 锐化：`detail=core(Y-blur1)+0.5*core(blur1-blur3)`，`core(d)=d**3/(d**2+t**2)`
- 暗角：归一化半径 `smoothstep(mid-feather/2, mid+feather/2, dist)`；正 amount 变暗，负 amount 提亮
- 颗粒：固定种子、按 grain_size 模糊、按 roughness 提对比、亮度权重
- LUT：`.cube` 的 `LUT_3D_SIZE` / `DOMAIN_MIN` / `DOMAIN_MAX`，红最快，三线性插值

### 6.4 性能

- 预览长边 1600，先下采样再渲染
- 全尺寸只在导出时从磁盘重新读取，不在内存常驻
- 单次预览目标：1600 px 长边、默认配方 < 150 ms；开启 clarity/去雾/锐化/颗粒 < 700 ms
- 所有数组 `float32`，避免 float64 峰值

## 7. 预览线程（`grade_worker.py`）

```python
class GradeRenderSignals(QObject):
    finished = Signal(int, object, object)   # generation, image, ToneAnalysis
    failed = Signal(int, str)

class GradeRenderTask(QRunnable):
    def __init__(self, generation, source, recipe, *, analyze=True)
```

- `GradePage` 持有 `QThreadPool`
- 参数变化后 140 ms 去抖启动
- 新任务递增 generation；旧结果到达直接丢弃
- 失败只更新页面状态，不弹模态框
- 页面关闭/切走时递增 generation 使在途结果失效

## 8. 调色台 UI（`grade_page.py`）

整体：`QVBoxLayout` = `GradeTopBar` + `QSplitter(Horizontal)`

### 8.1 顶栏 `GradeTopBar`

- 左：`显影台` 返回按钮
- 中：文件名 + 元信息（尺寸 / 胶片 / 相纸 / 交接图格式）
- 右：`调色台` 徽标、`前后对比` 按钮、`导出` 主按钮 + 箭头菜单
- 导出菜单：`直接导出（90% PNG）`、`导出设置…`
- 导出按钮在渲染中禁用并显示 `渲染中…`
- 样式：`SURFACE_0` + 底部分隔线

### 8.2 左栏 `GradeRail`（固定 244 px）

- 顶部 `Tabs(['LUT', '预设'], variant='underline')`
- LUT 页：
  - `QListWidget`，条目来自 `app_data_dir()/luts/*.cube`
  - `导入 LUT`、`移除`
  - `强度` 滑块 0..100
  - 选择即应用；无 LUT 时为空态说明
- 预设页：
  - `QListWidget`：内置预设 + 用户预设
  - `保存当前`、`重命名`、`删除`、`导入`、`导出`
  - 选中即套用
- 样式：`SURFACE_1` + 右发丝线

内置预设：`中性`、`清透`、`暖调`、`冷夜`、`黑白`

### 8.3 中间 `GradeCanvas`

- 深色背景，等比居中绘制
- 空态/加载中显示说明
- 前后对比：按下 `前后对比` 时绘制交接图的显示预览（未调色）
- 状态行：`宽×高 · sRGB · 预览 1:N`

### 8.4 右栏 `GradeDeck`（固定 348 px）

结构严格对齐 oflim：

1. 头部：`调色参数` 标题 + 脏参数计数徽标 + `重置`
2. 滚动体：
   - 直方图卡片（复用 `parameter_deck.HistogramView`）
   - `Tabs(['光影', '色彩'], variant='segmented')`
   - 当前 Tab 内容：
     - **光影**：曝光、对比度、高光、阴影、白色、黑色、中间调、高光过渡 + `参数曲线` 组（高光/亮调/暗调/阴影）
     - **色彩**：白平衡（色温/色调）；色彩（自然饱和度/饱和度/色相偏移/色彩密度）；色彩混合（8 色块选择器 + 色相/饱和度/明度）；颜色分级（阴影/中间调/高光选择器 + 色相/饱和度/明度 + 混合/平衡）
   - `通透` 折叠区：明暗通透、颜色通透、分析读数、偏色说明
   - `画质` 折叠区：清晰度、纹理、去雾、锐化/半径/阈值、亮度降噪、色彩降噪
   - `光学` 折叠区：暗角/中点/圆度/柔和度、颗粒/尺寸/粗糙度、色差

### 8.5 控件

- 复用 `WheelSafeSlider`：滚轮只滚动面板，不改参数
- 行高 44：上行标签 + 等宽读数，下行 3 px 轨道
- 读数非默认值时变黄铜
- 双击标签恢复该参数默认值
- `Tabs`、`HistogramView` 复用 `parameter_deck` 的实现
- 参数变更 → 更新配方 → 发出 `recipe_changed(dict)` → 140 ms 后预览渲染

### 8.6 信号

```python
class GradePage(QWidget):
    back_requested = Signal()
    recipe_changed = Signal(dict)
    export_requested = Signal(bool)          # True = 直接导出
    export_settings_requested = Signal()
    grade_image_ready = Signal(object, bool) # 全尺寸 sRGB 图 + direct
    status_message = Signal(str)
```

## 9. 持久化（`handoff.py` + `workspace.py`）

`state['grade']`：

```json
{
  "schema": 1,
  "handoff": {"path": "...", "fingerprint": "...", "width": 0, "height": 0, "format": "tiff16-prophoto-linear"},
  "recipe": { ...GradeRecipe.to_dict()... },
  "preset_id": "",
  "updated_at": 0.0
}
```

新增函数：

```python
def read_grade_recipe(state_data) -> GradeRecipe
def write_grade_recipe(state_data, recipe, preset_id='') -> dict
```

- `write_grade_recipe` 只改 `grade.recipe/preset_id/updated_at`，保留 `handoff`
- `workspace` 用 600 ms 防抖写盘，避免每拖一格滑块写 JSON
- 切回显影台、切照片、关闭窗口前 flush
- `_persist_active_state` 继续保留已有 `grade`，不被显影参数保存冲掉
- `has_grade_recipe` 继续基于 `grade.recipe` 非空判断

## 10. 导出（`controller.py` + `workspace.py`）

`Controller.export_graded_image(image, *, direct=False)`：

1. 取 `image` 的 `float32 sRGB encoded`
2. `direct=True` → `DirectExportSettings.to_export_settings(长边)`；否则用当前 `ExportSettings`
3. 强制 `filename_template='{name}_graded'`
4. 复用 `_export_with_settings(settings, payload=(image, 'sRGB', True, source_metadata))`
5. 状态栏显示导出路径

`workspace` 连接：

- `grade_page.export_requested` → 若页面已有全尺寸结果则直接导出，否则让页面渲染
- `grade_page.grade_image_ready` → `controller.export_graded_image`
- `grade_page.export_settings_requested` → 复用 `_on_export_settings`

## 11. 测试与验收

### 11.1 自动测试

`test_grade_recipe.py`

- 默认配方 `is_identity() == True`
- `to_dict/from_dict` 往返一致
- 越界值被钳制、错误类型回退默认、未知键忽略
- HSL 长度补齐
- 修改任一字段后 `is_identity() == False`

`test_grade_engine.py`

- 默认配方输出 == `prepare_source` 后 `srgb_encode`（逐位近似）
- 曝光 +1 EV 平均亮度上升；-1 EV 下降
- 对比度 ±100 不产生 NaN/Inf
- 饱和度 -100 输出接近灰度；+100 色度增加
- 明暗通透：黑场/白场读数在合理区间；50% 时对比度提高
- 颜色通透：偏色图的高光/阴影 delta 方向正确
- 锐化/清晰度/去雾/暗角/颗粒极值不崩、shape/dtype 正确
- LUT：单位 LUT 近似恒等，强度 100 生效
- 所有输出 `dtype == float32`、`0..1`、finite
- `analyze_tone` 返回 summary 且包含「黑场/白场」

`test_grade_presets.py`

- 内置预设数量与名称
- 保存/重命名/删除/导入/导出往返

`test_grade_page.py`

- 页面构建、Tab 切换、滑块改配方
- 重置回中性
- 双击恢复默认
- 前后对比切换
- 导出按钮在渲染中禁用
- 配方 signal 去抖

`test_workspace.py` 适配

- fake handoff 不是真实 TIFF 时，调色台仍能进入并显示错误态，不崩溃
- 配方持久化往返；切回显影台不丢
- 导出信号转发到 controller

### 11.2 手工冒烟

1. 打开真实 RAW/PNG → 显影 → 调色
2. 生成交接图 → 进入调色台 → 拖动光影/色彩/通透/画质/光学
3. 预览在 1 秒内更新，无闪退、无累积叠加
4. 切回显影台再进入，配方保持
5. 库卡片显示「已调色」
6. 导出生成 `{name}_graded.png`，可正常打开

### 11.3 回归门槛

- `pytest tests/gui -q`：全绿（含新增测试）
- `pytest tests -q`：除已知 4 条核心快照失败外无新增失败
- 不修改 `spektrafilm/` 核心管线

## 12. 关键决策与风险

| 决策 | 理由 |
| --- | --- |
| 默认配方仅做色彩空间转换 | 保证交接图与调色台首帧一致 |
| 通透分析基于调色后的当前画面 | 符合 oflim「取最终亮度直方图」语义 |
| HSL 8 带用色块选择器 + 3 滑块 | 保留 Lightroom 完整能力，避免 24 行挤压 |
| 三区颜色分级用分区选择器 | 同上 |
| 预览 1600 px / 全尺寸重读 | 控制内存与首帧速度 |
| LUT 在 sRGB 编码域应用 | 与常见 `.cube` 制作流程一致 |
| 不嵌入 RapidRAW 代码 | AGPL 传染性与架构不匹配；只重写公式 |

## 13. 需要用户确认

请确认本 Spec 后开始实现。若以下任一项需要调整，请在确认前指出：

1. 右栏「光影 / 色彩」Tab + 下方「通透 / 画质 / 光学」是否符合预期
2. 色彩混合与颜色分级采用「色块/分区选择器 + 3 滑块」的紧凑交互
3. 导出默认 `{name}_graded`，主按钮走当前导出设置，箭头菜单走 90% PNG
