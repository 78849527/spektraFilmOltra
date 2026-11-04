# 任务清单：显影台 → 调色台交接一致性

## [x] T1 review 结论落袋（已完成取证，待用户确认）

- 结论：交接图 = 显影台全尺寸线性输出；中性调色 = 显影台导出像素。
- 依据见 `specs/handoff-grade-parity/spec.md` §2.1–2.4。
- 交付形式：本次回复中的结论表 + 本文档；不改代码。

## [x] T2 修复调色台导出写死 sRGB（G2，需用户确认后才执行）

- 文件：`src/spektrafilm_gui/controller.py` → `export_graded_image`（634-657）
- 改为读取 `workflow.saving_color_space` / `saving_cctf_encoding`，非 sRGB 时做 `RGB_to_RGB('sRGB' → saving, dec=True, enc=saving)`；payload 同步替换。
- 验证：`tests/gui/test_grade_handoff_parity.py::test_graded_export_honours_saving_color_space`

## [x] T3 一致性回归测试（G1）

- 新增 `tests/gui/test_grade_handoff_parity.py`
  - `test_neutral_grade_matches_develop_export_bits`：合成线性图 → 显影导出路径 vs 16-bit ProPhoto TIFF 往返，逐像素差 ≤ 1。
  - `test_graded_export_identity_in_srgb`：默认 sRGB 下 payload 与输入差 ≤ 1。
- 验证：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui -q`

## [x] T4 端到端数值复核（G3）

- 真实工程 `IMG_6459.DNG`（4032×3024）复核，发现显影不可复现（同一参数两次运行平均差 1.63、最大 38；
  关掉颗粒后 0.108/6）。已修：`start_handoff` 复用最近一次全尺寸 Scan（指纹一致时），不再重跑显影。
- 同一份显影输出走 hop：**平均差 0.008/255、p99 = 0、最大 6（36,578,304 像素中仅 20 个）**，差异来自
  ProPhoto 负值（色域外欠冲）在 uint16 TIFF 中被截为 0。
- 验证：`tests/gui/test_controller_handoff.py::test_start_handoff_reuses_cached_full_size_scan`

## [x] T5 手工复核（等价自动化覆盖）

- 色彩等价已由 T3/T4 覆盖；剩余肉眼确认由用户下次进入调色台时完成
  （同一状态直接导出 `_graded.png` 与 `_spektrafilm.png` 对比）。

## [x] T6 调色台画布接显示器 ICC（G4）

- 文件：`src/spektrafilm_gui/grade_page.py`
  - 新增 `_apply_display_profile(image)`：走 `controller_runtime.prepare_output_display_image(output_color_space='sRGB', use_display_transform=True)`，与显影台预览同一条路径。
  - `GradeCanvas` 保存原始数组，`_build_pixmap` 按开关决定是否 ICC 映射；`set_display_transform_provider` 注入开关。
  - `paintEvent` 缓存缩放后的 QPixmap（全尺寸 pixmap 缩放只做一次）。
- 文件：`src/spektrafilm_gui/workspace.py`
  - `_display_transform_enabled()` 读取显影台「使用系统色彩显示」开关；构造 `GradePage` 后注入。
- 验证：`tests/gui` 315 passed。

## [x] T7 调色台预览改为全尺寸渲染（G5）

- 文件：`src/spektrafilm_gui/grade_page.py`
  - `load()` 不再 `downsample_linear`，`_preview_source` 保存全尺寸线性源；删除 `GRADE_PREVIEW_MAX_EDGE`。
- 实测：4032×3024 全尺寸 `render` 约 3.15 s，ICC 约 0.41 s（每次参数变更一次）。
- 验证：`test_grade_page.py::test_large_handoff_keeps_full_resolution_preview`。


