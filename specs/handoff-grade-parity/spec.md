# 显影台 → 调色台交接一致性 Review Spec

## 1. 用户要求

「review 胶片显影台和调色台的串联是否正常，正常是调色台会接收显影台处理后的完整最高质量 PNG 然后调色，也就是照片从显影台进入调色台不能有色差，也就是显影台直接导出的最高质量 PNG 和输入到调色台的 PNG 本质是一个。」

本次是 **review**，不是改算法；只有存在真实缺陷才动代码。

## 2. Review 结论（已按代码逐条核实）

### 2.1 交接图与显影台输出是同一份像素（无缺陷）

| 环节 | 代码位置 | 事实 |
| --- | --- | --- |
| 交接图入参 | `controller.py` `start_handoff`（397-434） | `image=np.double(self._current_input_image)` —— 全尺寸原图，不走预览缩放 |
| 参数来源 | 同上 | 与 Scan 完全相同：`collect_gui_state` → `build_params_from_state` |
| 预览妥协 | `params_builder.py:82-92` `<br>` `controller.py:1192-1198` | Scan 与 Handoff 都把 `settings.preview_mode` 置 False，颗粒/模糊/锐化全部保留 |
| 唯一差异 | `controller.py:419` | `io.output_cctf_encoding=False` |
| 该差异的影响面 | `scanning.py:130-139` `_apply_cctf_encoding` | 只跳过最后一步 CCTF；`compress_rgb`（输出色域压缩）在其之前完成，线性信号逐位不变 |

结论：交接图 = 显影台全尺寸线性的同一份显影结果，没有二次显影、没有预览降级。

### 2.2 色彩空间往返误差 ≤ 1 LSB（无缺陷）

- 写出：`controller.py:436-471` `_finish_handoff`，`colour.RGB_to_RGB(线性, output_color_space → ProPhoto RGB)`，`apply_cctf_decoding/encoding=False`，`save_image_oiio(bit_depth=16, color_space='ProPhoto RGB', cctf_encoding=False)` → 内嵌 `LargeRGB-elle-V2-g10.icc`（`utils/io.py:138`）。
- 读入：`grade_engine.py:82-90` `prepare_source` 用 `colour.matrix_RGB_to_RGB('ProPhoto RGB','sRGB')` 反向。
- 实测往返误差 ≈ `2.9e-5`，8-bit 量化后 ≤ 1 LSB。
- 真实工程实测（4032×3024）：同一份显影输出走「线性 → ProPhoto 16-bit TIFF → 读回 → 线性 sRGB → srgb_encode → 8-bit」，
  与显影台导出 8-bit 相比 **平均差 0.008/255、p99 = 0、36,578,304 像素中仅 20 个超过 1（最大 6）**。
  这 20 个像素是 ProPhoto 矩阵产生的**负值**（色域外欠冲），uint16 TIFF 无法表示负数而截为 0；显影台 PNG 同样会截为 0，
  因此差异只在近黑处、不可见，属于 16-bit 无符号格式的固有极限，不作为缺陷处理。

### 2.3 中性调色 = 显影台导出（无缺陷）

- 调色：`grade_engine.py:785-824` `render`，中性配方路径为 `srgb_encode(线性)` → 其余步骤全部 early-return → `clip[0,1]`。
- 显影导出：`controller.py:584-616` `_export_image_payload`，`saving_color_space` 默认 `sRGB`、`saving_cctf_encoding` 默认 True → 同空间转换为恒等（实测 2.4e-5）→ `save_image_oiio` clip 到 `[0,1]` 写 uint8（`utils/io.py:288-293`）。
- 两者都是 `uint8(clip(srgb_encode(线性)))`，因此本质相同；差异只在分辨率（直接导出 90% 长边，交接图 100%）。

### 2.4 交接图过期判定覆盖显影参数（无缺陷）

- `handoff.py` `_IGNORED_KEYS` = display / quick / grade / auto_preview / saving_color_space / saving_cctf_encoding。
- `quick` 被忽略是安全的：`quick_controls.py:244-` `expected_values` 把每个快速轴的意图写回 **原生字段**（`camera.exposure_compensation_ev`、`simulation.enlarger.print_exposure`、`chemistry.gamma_factor`、`grain.density_min` 等），这些字段仍在指纹里。
- `display.settings` / `saving_*` 只影响显示与另存，不影响显影像素。
- `workspace.py:223-292` 每次进调色台都校验 `version==2 + fingerprint + 文件存在`，不通过就先跑全尺寸显影。

### 2.5 唯一颜色缺陷：调色台导出写死 sRGB

`controller.py:634-657` `export_graded_image` 固定传 `payload=(data, 'sRGB', True, source_metadata)`，而显影台导出 `_export_image_payload` 会按 `workflow.saving_color_space` / `saving_cctf_encoding` 做转换（`controller.py:599-608`）。

后果：当用户把「保存色彩空间」设为 Display P3 / Adobe RGB 时，`{name}_spektrafilm.png` 是 P3/AdobeRGB 编码并内嵌对应 ICC，`{name}_graded.png` 却是 sRGB 编码 —— 两张文件不是同一色彩编码，违反「本质是一个」。默认 sRGB 时两者一致，所以平时看不出来。

### 2.6 真实工程复核暴露的根因：显影本身不可复现

用 `IMG_6459.DNG`（4032×3024）在同一进程里对**同一份输入、同一份参数**连跑两次显影：

| 对比 | 8-bit 平均差 | p99 | 最大差 |
| --- | --- | --- | --- |
| 两次相同参数的显影 | 1.63 | — | 38 |
| 关掉颗粒后再跑两次 | 0.108 | — | 6 |
| 已存 `handoff.tif` vs 新跑显影 | 6.42 | 31 | 92 |

结论：显影像素在两次运行之间本来就会变（随机颗粒占绝大部分），并且被胶片密度曲线放大到局部 30~90/255。
因此「交接图 = 显影台导出」**必须复用同一份显影结果**，重跑一次注定对不上——这才是「本质不是一个」的真实原因，不是色彩转换问题。

修复（`controller.py`）：

- `_on_simulation_finished` 在全尺寸 Scan 完成后，把当前状态的 `handoff_fingerprint` 记到 `_output_scan_fingerprint`。
- `start_handoff(..., fingerprint=...)` 先尝试 `_reuse_cached_scan`：指纹一致、输出图层浮点数据是全尺寸、色彩空间/编码一致时，直接把这份像素
  `编码 → 线性 → ProPhoto 16-bit TIFF`，不再重跑显影；否则照旧跑一次全尺寸显影。
- `workspace._on_grade_requested` 把已算好的指纹传进去。
- 载入新图时清空指纹，避免跨照片误用。

复用后交接图与显影台导出同源：同一份显影输出走 hop 测试得到 **平均差 0.008/255、p99 = 0、最大 6（仅 20 个像素）**。

### 2.7 信息性发现（不改）
- 调色台预览已改为全尺寸渲染，1600 上限那条作废（见 G5）。
- `analyze_tone`（`grade_engine.py:415-456`）现在预览与导出都在全尺寸上算，采样密度一致。
- 显影台预览的白边（`white_padding`）只用于 napari 世界坐标装饰（`controller_layers.py:312-364`），不进像素、也不进交接图。

## 3. 目标

- **G1** 用自动化测试锁死「交接图 → 中性调色 → 8-bit sRGB」与「显影台导出 → 8-bit sRGB」差值 ≤ 1 LSB。
- **G2** 修复 `export_graded_image`，让它与显影台导出使用同一套保存色彩空间/编码。
- **G3** 一次真实工程的端到端数值复核（4032×3024 交接图 vs 重新生成的显影台导出）。
- **G4** 调色台画布按显示器 ICC 显示（与显影台预览同一条 `prepare_output_display_image` 路径，跟随「使用系统色彩显示」开关），保证同一块屏幕上 显影台预览 / 调色台预览 / 导出文件 三者观感一致。
- **G5** 调色台预览不再降采样（原 1600 长边上限），按全尺寸渲染，避免画布放大后发糊。

## 4. 非目标

- 不改显影算法、不改调色算法与配方结构。
- 不改预览缩放上限（1600/1920 的差异属观感，不属色差）。
- 不动 `handoff.py` 的指纹定义（已核实覆盖显影参数）。

## 5. 改动清单

### 5.1 `src/spektrafilm_gui/controller.py`

`export_graded_image`（634-657）——把写死的 sRGB 换成与显影台导出同源的保存设置：

```python
gui_state = collect_gui_state(widgets=self._widgets)
saving_color_space = str(gui_state.simulation.workflow.saving_color_space or 'sRGB')
saving_cctf_encoding = bool(gui_state.simulation.workflow.saving_cctf_encoding)
data = np.asarray(image, dtype=np.float32)
if data.ndim != 3 or data.shape[2] < 3:
    ...
data = np.ascontiguousarray(data[..., :3])
if saving_color_space != 'sRGB' or not saving_cctf_encoding:
    data = np.asarray(
        colour.RGB_to_RGB(
            data, 'sRGB', saving_color_space,
            apply_cctf_decoding=True,
            apply_cctf_encoding=saving_cctf_encoding,
        ),
        dtype=np.float32,
    )
...
payload=(data, saving_color_space, saving_cctf_encoding, source_metadata)
```

阶调曲线保持现有 `np.clip(0,1)`（在 `save_image_oiio` 内），不新增剪裁。

### 5.2 测试

- 新增 `tests/gui/test_grade_handoff_parity.py`：
  - `test_neutral_grade_matches_develop_export_bits`：用合成线性图，先按显影导出路径 `uint8(clip(srgb_encode(linear))*255)` 得到基准；再写成 16-bit ProPhoto TIFF → `prepare_source` → `srgb_encode` → uint8；断言逐像素差 ≤ 1。
  - `test_graded_export_honours_saving_color_space`：mock `controller._export_with_settings`，在 `saving_color_space='Display P3'` 下调用 `export_graded_image`，断言 payload 色彩空间为 `Display P3` 且数据已转换（与原图均值差 > 0）。
  - `test_graded_export_identity_in_srgb`：默认 sRGB 时 payload 与输入逐像素差 ≤ 1。
- 既有 `tests/gui` 全绿。

## 6. 验证步骤

1. `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui -q` → 全绿。
2. 端到端数值复核（脚本临时文件，不提交）：读现有 `handoff.tif`（4032×3024）→ `prepare_source → srgb_encode` → 与重新生成的 `{name}_spektrafilm.png` 全尺寸比对，均值差 ≤ 2/255、最大差 ≤ 3/255。
3. 手工：调色台不调参数直接导出 `_graded.png`，与显影台 `_spektrafilm.png` 同点取色，8-bit 差 ≤ 2（分辨率差异用缩放对齐）。

## 7. 风险

- `export_graded_image` 增加一次色彩转换，非 sRGB 保存空间下耗时 +几十毫秒，可接受；sRGB 默认路径保持恒等，不改变现有输出。
- 新增测试依赖 `OpenImageIO` 与 `colour`，与现有 `tests/gui` 依赖一致。
