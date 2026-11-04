# 胶片边框 验收清单

- [x] G1 开关默认开启且位于右侧栏底部；关闭后预览窗白色留白隐藏
      （离屏渲染快照 `/tmp/deck_frame_row.png` 确认；`_apply_white_border_layout` 隐藏 `white_border` 层）
- [x] G2 切换边框预设即时更新预览，且不重跑显影
      （`test_apply_frame_state_recomposites_without_rerunning` 确认复用 `pipeline_display_output` 像素）
- [x] G3 导出（直接导出 / 导出对话框 / 保存输出图层）像素包含边框
      （`test_export_composites_the_selected_frame`、`test_export_can_skip_the_frame`）
- [x] G4 调色台交接图与调色导出不带边框
      （`test_graded_export_never_includes_the_frame`；交接图仍读 `float_image` metadata）
- [x] G5 边框状态随照片持久化，切换照片正确还原
      （`test_workspace_persists_and_restores_frame_state`）
