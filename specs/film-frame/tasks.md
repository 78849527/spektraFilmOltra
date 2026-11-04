# 胶片边框 实施任务

- [x] T1 新建 `src/spektrafilm_gui/film_frame.py`：`FramePreset`、6 个预设、`preset_by_key`、`apply_frame`
- [x] T2 `preset_rail.py` 增加「边框」tab、`_FrameSwatch`、`frame_selected`、`set_current_frame`
- [x] T3 `parameter_deck.py` 右侧栏底部「添加边框」开关 + `frame_state` / `set_frame_state` / `frame_changed`
- [x] T4 `editor_page.py` 透传 `frame_selected` / `frame_changed` / `set_frame_state`
- [x] T5 `workspace.py` 持久化 `state['frame']`、`open_item` 还原、注入 `set_frame_provider`、直方图改用未加边框像素
- [x] T6 `controller.py` 预览合成、`apply_frame_state` 即时切换、白边布局、导出合成、调色导出不带边框
- [x] T7 新增 3 个测试文件 + 扩展 `test_workspace.py`，`tests/gui` 333 项全部通过
- [x] T8 重启预览 + 离屏渲染目视验收 G1–G5
