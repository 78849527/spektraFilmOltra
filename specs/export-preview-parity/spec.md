# 导出与预览一致性修复 Spec

## 1. 现象

用户反馈：「就算我直接导出，导出和预览也不一样」。附 Finder 快速查看对比截图：左图偏亮、偏灰、对比度低；右图偏暗、饱和度高、略偏黄绿。

## 2. 取证结论（已核实，非推测）

| 证据 | 数值 |
| --- | --- |
| `~/Pictures/IMG_6459_spektrafilm.png`（11-03 10:19，1728×1296，显影台直接导出模板 `{name}_spektrafilm`） | 均值 RGB `117.8 / 124.5 / 115.4` |
| 同一工程的 `handoff.tif` 走 `prepare_source → srgb_encode`（全尺寸 4032×3024） | 均值 RGB `118.4 / 124.8 / 116.9` |
| `library.json` 中该图持久化的 `grade.recipe`（11 项非默认：contrast −19、highlights −100、shadows −100、curve_highlights −64、curve_lights −70、curve_darks −27、curve_shadows +67 等）渲染 handoff | 预览 `111.3 / 121.8 / 109.7`；全尺寸 `109.2 / 119.2 / 106.2` |

结论：

1. 磁盘上那份 PNG **就是未调色的显影台输出**，不是调色台结果；调色台导出模板是 `{name}_graded`，磁盘上没有 `_graded` 文件。
2. 全仓库 `src/spektrafilm_gui` **没有任何 `contrast_limits` 设置**。napari 的 `add_image` 对 float 图像默认把 `[data.min(), data.max()]` 作为对比度上下限并拉伸到满量程，而导出写的是绝对像素值。取值为 `0 … 0.88` 时，预览会被抬亮约 13% 并压平暗部 —— 与截图「左图偏亮偏灰」完全吻合。
3. 同时存在两套导出命名（显影台 `{name}_spektrafilm`、调色台 `{name}_graded`）且显影台在有配方时仍静默导出未调色结果，用户无法判断哪份文件对应屏幕上看到的画面。

## 3. 目标

- **G1** 预览像素 = 导出像素：所有 RGB 图层固定 `contrast_limits=(0.0, 1.0)`，显影台预览不再被自动拉伸。
- **G2** 有非默认调色配方时，显影台的「直接导出」给出明确状态提示，说明该导出不含调色参数、应到调色台导出；不静默。
- **G3** 补回归测试，锁死上述两条。

## 4. 非目标

- 不改调色算法、不动调色台布局与参数面板。
- 不处理「1600 预览 vs 全尺寸」带来的颗粒/锐化细节尺度差异（属正常缩放差异，不是色彩问题）。
- 不比对历史遗留文件、不清理用户 Pictures 目录。

## 5. 改动清单

### 5.1 `src/spektrafilm_gui/controller_layers.py`

1. 新增模块级助手：

```python
DISPLAY_CONTRAST_LIMITS = (0.0, 1.0)

def _lock_contrast_limits(layer) -> None:
    layer.contrast_limits = DISPLAY_CONTRAST_LIMITS
```

2. `_set_or_add_image_layer`（约 469 行）：新建分支 `viewer.add_image(image, name=layer_name)` 之后、更新分支 `_set_layer_data(existing_layer, image)` 之后，都调用 `_lock_contrast_limits(layer)`。
3. `set_or_add_output_layer`（约 358 行）：在 `set_output_layer_metadata` / `set_output_layer_interpolation` 之后、`_refresh_layer(layer)` 之前，再调用一次 `_lock_contrast_limits(layer)`（幂等，覆盖动画/交叉淡入路径）。

### 5.2 `src/spektrafilm_gui/workspace.py`

`_request_direct_export`（约 212 行）：在委派 `controller.request_direct_export()` 之前，读取当前 `LibraryItem.state`，用 `read_grade_recipe(state)` + `recipe.dirty_count()` 判定；若 `dirty_count() > 0`，先 `self._show_status('当前照片有调色配方，显影台导出不含调色参数；请进入调色台导出')`，然后照常导出（不阻断）。

> 说明：判定逻辑放 workspace 而非 controller，因为 controller 不持有 `LibraryItem.state`。

### 5.3 测试

- `tests/gui/test_controller_layers.py`：新增 `test_output_layer_contrast_limits_are_locked` —— 用 `max < 1.0` 的合成图调用 `set_or_add_output_layer`，断言 `layer.contrast_limits == (0.0, 1.0)`；再用更高亮度的第二帧更新，断言仍为 `(0.0, 1.0)`。
- `tests/gui/test_workspace*.py`（实现时就近选择已有 workspace 测试模块）：新增一条用例，mock `controller.request_direct_export`，断言有配方时 status 被调用且导出仍被委派。
- 既有 `tests/gui` 全部保持通过。

## 6. 验证步骤

1. `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui -q` → 全绿。
2. 重启 `启动_Spektrafilm.command`，同一张图、同一参数：显影台预览取色与 `直接导出` 的 PNG 同一点取色，8-bit 差值 ≤ 2。
3. 调色台：改任一滑块 → 直接导出 → 产出 `*_graded.png`（长边为原图 90%），canvas 与文件同点差值 ≤ 3。
4. 主「导出」按钮（JPEG / 面板设置）同样满足第 2 条。

## 8. 补充取证：显影台 PNG vs 显影台预览（用户最新反馈）

导出文件与显影台输出的像素本身一致：把 `handoff.tif` 走 `prepare_source → srgb_encode` 后缩到导出尺寸，与 `IMG_6459_spektrafilm.png` 平均差 **3/255**，γ=1 最优（γ=0.8 时升到 15.5、γ=2.2 时升到 49），说明导出链没有二次编码。

剩下的可见差异来自**显示器色彩管理**：

- Finder/预览器会按显示器 ICC 把 sRGB 文件做色彩管理；app 预览在 macOS 上 `ImageCms.get_display_profile()` 返回 `None`，于是 `sync_display_transform_availability` 把「使用系统色彩显示」自动关掉，预览是未管理的原始 sRGB。
- 本机主显示器 `DELL U2720Q` 的 ICC 换算会把同一张图压到 `117.8/124.5/115.5 → 110.8/116.8/109.2`（最大差 11/255）——正是「预览偏亮、文件偏暗」。

修复：`controller_runtime` 增加 macOS 回退——从 `system_profiler` 取主显示器型号，匹配 `/Library/ColorSync/Profiles/Displays/` 下最新的 ICC 并载入；启动时若找到 ICC 就保持「使用系统色彩显示」为开。这样预览与 Finder 中对同一文件的渲染一致。

## 7. 风险

- 固定 `contrast_limits` 后，若输出确实超出 `[0, 1]`，预览会裁切；但这与 `save_image_oiio` 的 clip 行为一致，符合「预览即导出」的优先级。
- 显影台导出提示只是状态栏文案，不改变既有导出行为，不会破坏现有测试中的导出断言。
