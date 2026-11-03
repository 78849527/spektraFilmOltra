# 任务清单：导出与预览一致性修复

## [x] T1 锁定图层对比度（G1）

- 文件：`src/spektrafilm_gui/controller_layers.py`
- 新增 `DISPLAY_CONTRAST_LIMITS = (0.0, 1.0)` 与 `_lock_contrast_limits(layer)`。
- `_set_or_add_image_layer`：新建与更新两条分支都固定对比度。
- `set_or_add_output_layer`：刷新前再固定一次（幂等）。
- 验证：`tests/gui/test_controller_layers.py` 新增锁定用例。

## [x] T2 显影台导出提示（G2）—— 已按用户要求撤回（先只保证显影台预览 = 导出，不介入调色）

- 文件：`src/spektrafilm_gui/workspace.py` → `_request_direct_export`
- 用 `read_grade_recipe(state)` + `dirty_count()` 判定；有配方时状态栏提示后照常导出。
- 验证：workspace 测试新增 mock 用例。

## [x] T3 回归

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui -q`
- 重启源码预览（`启动_Spektrafilm.command`），请用户肉眼确认预览 = 导出。

## [x] T4 显示台预览恢复系统色彩管理（显影台 PNG vs 预览）

- `src/spektrafilm_gui/controller_runtime.py`：`_macos_main_display_model` / `_macos_display_profile_bytes` / `_system_display_profile`，`display_profile_details` 与 `display_profile_available` 改走统一入口。
- `src/spektrafilm_gui/controller.py`：`sync_display_transform_availability` 在找到 ICC 时启动即保持「使用系统色彩显示」为开。
- `tests/gui/test_controller_output.py`：autouse fixture 固定 `_macos_display_profile_bytes`，测试不依赖本机显示器。
- 验证：`DELL U2720Q` ICC 被发现并应用；`tests/gui` 311 passed。

## T5 打包（用户确认后执行，不在本次范围）

- 现 DMG `Spektrafilm_胶片模拟引擎_0.3.4_macOS_arm64_调色台.dmg` 已过时（缺 resize 修复、色彩修复、本次对比度修复），待用户确认后重打。
