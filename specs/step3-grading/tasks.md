# 第三步调色台 · Tasks

> 依赖顺序：T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8
> 每项完成后立即跑对应测试；T8 为全量回归与冒烟。

## T1 配方模型

- [x] 已完成

**文件**

- 新增 `src/spektrafilm_gui/grade_recipe.py`

**内容**

- `LightRecipe`、`ColorRecipe`、`HslBand`、`GradeZone`、`ColorGrading`、`TransparencyRecipe`、`QualityRecipe`、`OpticsRecipe`、`LutRecipe`、`GradeRecipe`
- 字段与范围严格按 `spec.md` 第 5 节
- `DEFAULT_HSL` 8 带中心色相
- `GradeRecipe()` 默认全中性
- `is_identity()`、`to_dict()`、`from_dict()`
- 内部 `_number` / `_range` 校验：越界钳制、类型错误回退、未知键忽略
- `HslBand` 列表长度补齐/截断

**验证**

```bash
pytest tests/gui/test_grade_recipe.py -q
```

## T2 调色引擎

- [x] 已完成

**文件**

- 新增 `src/spektrafilm_gui/grade_engine.py`

**内容**

- 矩阵：`PPRO_TO_XYZ_D50`、`XYZ_D50_TO_SRGB_D65`
- `prepare_source`、`srgb_encode`、`srgb_decode`
- `load_handoff_image`（复用 `spektrafilm.utils.io.load_image_oiio`，转 float32）
- `downsample_linear`（`skimage.transform.resize`，`anti_aliasing=True`）
- `ToneAnalysis` + `analyze_tone`
- `render(source, recipe, analyze=True)` 按 spec 6.2 顺序
- 影调：`_apply_exposure_wb`、`_apply_contrast`、`_apply_tone_masks`、`_apply_highlight_rolloff`、`_apply_parametric_curve`
- 色彩：`_apply_saturation`、`_apply_hue_shift`、`_apply_hsl_bands`、`_apply_color_grading`
- 通透：`_apply_transparency`
- 画质：`_apply_clarity_structure`、`_apply_dehaze`、`_apply_noise_reduction`、`_apply_sharpening`
- 光学：`_apply_vignette`、`_apply_chromatic_aberration`、`_apply_grain`
- LUT：`parse_cube(path)` + `apply_lut(image, lut, strength)`
- 全程 `float32`、`np.errstate`、最终 `clip(0,1)` + `nan_to_num`

**验证**

```bash
pytest tests/gui/test_grade_engine.py -q
```

## T3 预览线程

- [x] 已完成

**文件**

- 新增 `src/spektrafilm_gui/grade_worker.py`

**内容**

- `GradeRenderSignals(QObject)`：`finished(int, object, object)`、`failed(int, str)`
- `GradeRenderTask(QRunnable)`：持有 generation / source / recipe / analyze
- `run()` 调 `grade_engine.render`，异常转 `failed`
- 结果只通过 signal 回主线程；不在 worker 里碰 Qt widget

**验证**

- `test_grade_page.py` 中构造任务并 `QThreadPool` 跑一张 64×48 图，确认 signal 收到结果

## T4 调色台 UI

- [x] 已完成

**文件**

- 重写 `src/spektrafilm_gui/grade_page.py`

**内容**

- `GradeTopBar`：返回、标题、调色台徽标、前后对比、导出 + 箭头菜单
- `GradeRail`：LUT/预设 Tab；LUT 列表、导入、移除、强度；预设列表、保存/重命名/删除/导入/导出
- `GradeCanvas`：等比绘制、空态、前后对比、状态行
- `GradeDeck`：
  - 头部：标题、脏计数、重置
  - 直方图（复用 `parameter_deck.HistogramView`）
  - `Tabs(['光影','色彩'])`（复用 `parameter_deck.Tabs`）
  - 光影页：8 滑块 + 参数曲线 4 滑块
  - 色彩页：白平衡 2 + 色彩 4 + 色彩混合（8 色块 + 3 滑块）+ 颜色分级（3 分区 + 3 滑块 + 混合/平衡）
  - 下方 `CollapsibleSection`：通透、画质、光学
- `RecipeSliderRow`：`WheelSafeSlider` + 标签 + 等宽读数 + 双击复位 + 黄铜脏态
- 所有控件改动写回 `GradeRecipe` 并发出 `recipe_changed`
- 140 ms 去抖 + `GradeRenderTask`
- `load(item, handoff_path, recipe)`：
  - 成功：加载 → `prepare_source` → 下载到 1600 px → 立即渲染首帧
  - 失败：画布显示错误态，仍可返回，不弹模态
- 导出：`export_requested(bool)` → 若无全尺寸结果则启动全尺寸任务 → `grade_image_ready`
- `unload()`：递增 generation、清空图像与线程结果

**验证**

```bash
pytest tests/gui/test_grade_page.py -q
```

## T5 预设库

- [x] 已完成

**文件**

- 新增 `src/spektrafilm_gui/grade_presets.py`

**内容**

- `BUILTIN_PRESETS`：中性、清透、暖调、冷夜、黑白
- `GradePresetStore`：`all()`、`save()`、`rename()`、`delete()`、`import_file()`、`export_file()`
- 存储 `app_data_dir()/grade_presets.json`
- 原子写（临时文件 + replace）
- 内置预设不可删除/重命名

**验证**

```bash
pytest tests/gui/test_grade_presets.py -q
```

## T6 Workspace 集成与持久化

- [x] 已完成

**文件**

- 修改 `src/spektrafilm_gui/handoff.py`
- 修改 `src/spektrafilm_gui/workspace.py`
- 修改 `src/spektrafilm_gui/controller.py`

**内容**

- `handoff.py`：`read_grade_recipe`、`write_grade_recipe`
- `workspace.py`：
  - 连接 `grade_page.grade_changed/export_requested/export_settings_requested/grade_image_ready/status_message`
  - `_open_grade_page` 从 `state['grade']['handoff']['path']` 加载；失败仍进入并提示
  - `_grade_persist_timer` 600 ms；`_save_grade_recipe()` 写 `state['grade']`
  - `show_editor()` / `show_library()` / `closeEvent()` flush
  - 更新库卡片「已调色」与显影台调色按钮状态
- `controller.py`：`export_graded_image(image, *, direct=False)`，复用 `_export_with_settings`，`filename_template='{name}_graded'`

**验证**

```bash
pytest tests/gui/test_workspace.py tests/gui/test_controller_handoff.py -q
```

## T7 测试补齐

- [x] 已完成

**文件**

- 新增 `tests/gui/test_grade_recipe.py`
- 新增 `tests/gui/test_grade_engine.py`
- 新增 `tests/gui/test_grade_page.py`
- 新增 `tests/gui/test_grade_presets.py`
- 修改 `tests/gui/test_workspace.py`

**内容**

- 覆盖 `spec.md` 11.1 全部用例
- fake handoff 非 TIFF 时页面容错
- 配方持久化往返

**验证**

```bash
pytest tests/gui -q
```

## T8 全量回归与真实冒烟

- [x] 已完成

**步骤**

1. `pytest tests/gui -q` → 全绿
2. `pytest tests -q` → 除既有 4 条核心快照失败外无新增
3. 离线冒烟：
   - 读取一张真实交接图或合成 16-bit ProPhoto TIFF
   - `GradeRecipe()` 渲染 → 输出 sRGB 图
   - 逐个滑块改值 → `render` 输出有限、方向正确
   - 全尺寸导出 → `{name}_graded.png` 可读
4. 启动应用预览：
   - 打开照片 → 显影 → 调色 → 拖动 → 返回 → 再进入 → 配方保持

**验收**

- `spec.md` 第 11 节全部通过
- 无新增核心失败
- 无闪退、无内存暴涨
