# 胶片边框（Film Frame）规格

## 0. 调研结论

- 上游 Spektrafilm 主仓与常见 fork / 变体都**没有**内置边框（frame / rebate）功能，也没有可直接复用的边框预设资源。
- 业界通行做法（35mm 齿孔与片基色、120 背纸边、暗房白边、宝丽来白框、黑卡纸装裱）都是后期叠加，不是显影管线的一部分。
- 因此本功能在 GUI 层**程序化合成**，不引入外部图片素材、不修改 `spektrafilm` 显影管线。

参考来源（通用概念，非本项目代码）：
- 35mm 胶片片边（sprocket holes / rebate / edge codes）：<https://en.wikipedia.org/wiki/135_film>
- 120 卷片与背纸边：<https://en.wikipedia.org/wiki/120_film>
- 暗房印相留白与宝丽来边框：<https://en.wikipedia.org/wiki/Instant_film>

---

## 1. 目标

1. 显影台右侧栏**底部**新增「添加边框」开关，**默认开启**。
2. 开启时：预览窗显示边框；导出（直接导出 / 导出对话框 / 保存输出图层）的像素中也带边框。
3. 关闭时：预览窗原有的白色留白（`white_border` 图层）一并隐藏，导出不带边框。
4. 左侧预设台在「胶片 / 相纸」之外新增**「边框」tab**，列出下方预设，点击即切换（不重跑显影）。
5. 调色台：交接图与调色导出**始终不带边框**，保持纯像素源。

---

## 2. 预设清单（`film_frame.py`）

| key | 名称 | 形态 |
| --- | --- | --- |
| `none` | 无边框 | 原样返回 |
| `paper_white` | 白相纸边 | 均匀暖白边 |
| `matte_black` | 黑卡纸边 | 均匀深灰边 + 细内线 |
| `film_135` | 135 彩色负片 | 琥珀片基 + 上下齿孔 + 片边标记 |
| `film_120` | 120 卷片 | 窄深色边 + 上边卷片编号刻度 |
| `polaroid` | 宝丽来白框 | 白框 + 下边明显加宽 |

默认：`enabled=True`、`preset='paper_white'`。

边距规则：`margin = max(preset.margin, gui_only.display.white_padding)`，
即「白边」滑杆继续负责外框粗细，预设提供最小边距（齿孔类预设 ≥ 0.07 短边，保证齿孔画得下）。

---

## 3. 状态与数据流

- 持久化位置：`LibraryItem.state['frame'] = {'enabled': bool, 'preset': str}`，与 `quick` 同级。
- `workspace._persist_active_state()` 写入；`workspace.open_item()` 读出并下发。
- 读取链：`PresetRail.frame_selected(str)` / `ParameterDeck.frame_changed()` → `EditorPage` → `Workspace` → `GuiController.apply_frame_state()`。
- 控制器通过 `set_frame_provider(fn)` 注入 `fn() -> (enabled, preset)`，避免 workspace 逻辑渗入控制器。

---

## 4. 文件改动清单

### 4.1 新增 `src/spektrafilm_gui/film_frame.py`

```python
@dataclass(frozen=True)
class FramePreset:
    key: str
    name: str
    subtitle: str
    margin: float                 # 相对短边的最小留白
    bottom_extra: float = 0.0     # 下边额外留白（宝丽来）
    base: tuple[float, float, float] = (0.96, 0.95, 0.92)
    accent: tuple[float, float, float] = (0.55, 0.45, 0.32)
    style: str = 'plain'          # plain | matte | sprocket | rollfilm | polaroid

FRAME_PRESETS: tuple[FramePreset, ...]
DEFAULT_FRAME_PRESET = 'paper_white'

def preset_by_key(key: str) -> FramePreset   # 未知 key 回退默认
def apply_frame(image, key: str, *, padding: float = 0.03) -> np.ndarray
```

`apply_frame` 约定：
- `key == 'none'` 或 `preset.margin <= 0` → 原样返回同一数组。
- 保持输入 dtype（`uint8` / `uint16` / `float32`），颜色按 0..1 定义后按 dtype 满量程折算。
- 支持 `ndim == 3` 且通道 ≥ 3；其他形状原样返回。
- 画布尺寸 = `(h + top + bottom, w + 2*margin)`；照片居中，`bottom_extra` 只加在下边。
- `sprocket`：上下边距内画等距圆角齿孔；`rollfilm`：上边画刻度短线；`polaroid`：下边加宽。
- 纯 numpy 实现，无 PIL / Qt 依赖，便于测试。

### 4.2 `src/spektrafilm_gui/preset_rail.py`

- `PresetRail` 新增 `frame_selected = Signal(str)`。
- 新增 `_frame_entries()`，条目字段与胶片/相纸一致（`raw/name/brand/meta`）。
- `_build_ui`：header 增加第三个 `modeTab`「边框」；`_set_tab` 接受 `'frame'`（切到边框时隐藏品牌行，保留搜索）。
- `_entries()` 增加 frame 分支。
- 新增 `_FrameSwatch(QWidget)`：42×42，用 `apply_frame` 把纯色样本渲染成缩略图。
- `PresetCard` 增加 `is_frame` 参数，选中框选中态与现有逻辑一致。
- `_on_card_selected` 增加 frame 分支并发出 `frame_selected`；新增 `_current_frame`、`set_current_frame(raw)`。
- `set_current(film, paper)` 签名不变，内部同时刷新边框选中态。

### 4.3 `src/spektrafilm_gui/parameter_deck.py`

- `ParameterDeck` 新增 `frame_changed = QtCore.Signal()`。
- 新增 `_build_frame_row()`：卡片式行，左侧标题「添加边框」，副标题「胶片边框 / 相纸留白」，右侧复用 `ToggleSwitch`，默认勾选。
- `_build_body()` 在 `layout.addWidget(self._mode_stack, 1)` **之后**追加 `layout.addWidget(self._build_frame_row())`（即右侧栏底部）。
- 新增：
  - `frame_state() -> tuple[bool, str]`
  - `set_frame_state(raw: object) -> None`（接受 `{'enabled','preset'}`、`None`；不触发信号）
  - `set_frame_preset(preset: str) -> None`
  - 开关切换时 `frame_changed.emit()`。

### 4.4 `src/spektrafilm_gui/editor_page.py`

- `EditorPage` 新增 `frame_selected = Signal(str)`、`frame_changed = Signal()`。
- `__init__` 连接 `preset_rail.frame_selected`、`inspector.frame_changed`。
- 新增 `set_frame_state(raw)` / `frame_state_dict()`。
- `refresh_after_state_change()` 保持现有胶片/相纸同步，不动边框（边框不依赖参数）。

### 4.5 `src/spektrafilm_gui/workspace.py`

- `__init__`：`self._controller.set_frame_provider(self._frame_settings)`。
- 新增 `_frame_settings() -> tuple[bool, str]`：读 `editor_page.frame_state_dict()`，异常回退 `(True, DEFAULT_FRAME_PRESET)`。
- `_connect_signals`：`frame_selected → _on_frame_selected`、`frame_changed → _on_frame_changed`。
- 新增 `_on_frame_selected(raw)` / `_on_frame_changed()`：更新 UI → `controller.apply_frame_state()` → `_schedule_persist()`。
- `_persist_active_state()`：`data['frame'] = self.editor_page.frame_state_dict()`。
- `open_item()`：在 `set_quick_state` 附近调用 `self.editor_page.set_frame_state(item.state.get('frame'))`。
- `_on_simulation_finished(result)`：直方图数据改用 `result.display_image`（避免把边框像素计入直方图）。

### 4.6 `src/spektrafilm_gui/controller.py`

- `__init__`：`self._frame_provider = None`。
- 新增 `set_frame_provider(provider)`、`_frame_settings() -> tuple[bool, str]`、`_framed_display(image)`、`apply_frame_state()`、`_apply_white_border_layout()`。
  - provider 为 `None` → `(False, 'none')`，保持旧行为（测试不受影响）。
  - `_framed_display`: 开启时 `apply_frame(image, preset, padding=display.white_padding)`。
  - `_apply_white_border_layout`: 边框开启时 `_sync_white_border(0.0)`；两种状态都隐藏 `WHITE_BORDER_LAYER_NAME`（用户要求关闭时白边隐藏、开启时由边框取代白边）。
  - `apply_frame_state()`: 仅重合成当前输出层（读取层 metadata 中的原始显示像素），不重跑显影。
- 三处 `_sync_white_border(white_padding=state.gui_only.display.white_padding)` 改为 `_apply_white_border_layout()`（`_start_simulation`、`_run_simulation`、`_set_or_add_input_stack`）。
- `show_startup_placeholder()` 的 `white_padding` 传 `0.0`，随后调用 `_apply_white_border_layout()`。
- `_on_simulation_finished()`：`display = self._framed_display(result.display_image)` 再传给 `_set_or_add_output_layer`；`result` 本身不改，`_result_is_full_size()` 与 `_output_scan_fingerprint` 逻辑不受影响。
- `_run_simulation()` 同样合成边框。
- `_export_with_settings(settings, *, payload=None, with_frame=True)`：缩放之后、保存之前，若 `with_frame` 且边框开启 → `apply_frame(...)`。
- `export_graded_image()` 调用时传 `with_frame=False`。
- `save_output_layer()`：保存前同样合成边框。
- 输出层 metadata 增加原始（未加边框）显示图，供 `apply_frame_state()` 复用；`apply_frame_state()` 没有 metadata 时回退到 `_framed_display(layer.data)`。

### 4.7 测试

新增 / 修改：
- `tests/gui/test_film_frame.py`
  - `none` 原样返回；`paper_white` 尺寸与边距正确；dtype 保持；`film_135` 上下齿孔区域出现非纯色像素；`polaroid` 下边 > 上边；未知 key 回退默认。
- `tests/gui/test_parameter_deck_frame.py`
  - 默认 `(True, 'paper_white')`；`set_frame_state` 静默；切换开关发出 `frame_changed`。
- `tests/gui/test_controller_frame.py`
  - `_framed_display` 关闭时原样；开启时尺寸变大；`export_graded_image` 路径 `with_frame=False`（用 spy 校验）。
- `tests/gui/test_workspace_frame.py`
  - `_persist_active_state` 写入 `state['frame']`；`open_item` 还原开关与预设。

### 4.8 验证命令

```bash
python -m pytest tests/gui/test_film_frame.py tests/gui/test_parameter_deck_frame.py tests/gui/test_controller_frame.py tests/gui/test_workspace_frame.py -q
python -m pytest tests/gui -q
```

目视验证：重启 GUI，确认
1. 右侧栏底部有「添加边框」，默认开启；
2. 左侧「边框」tab 有 6 张卡片；
3. 点击卡片预览即时变化，不触发显影进度；
4. 关闭开关后预览白边消失；
5. 导出的 PNG 像素包含所选边框。

---

## 5. 验收条件

- **G1** 开关默认开启且位于右侧栏底部；关闭后预览窗白色留白隐藏。
- **G2** 切换边框预设即时更新预览，且不重跑显影（复用已有输出像素）。
- **G3** 导出（直接导出 / 导出对话框 / 保存输出图层）的像素包含边框，边框为绝对像素值，不受预览对比度拉伸影响。
- **G4** 调色台交接图与调色导出**不带**边框。
- **G5** 边框状态随照片持久化，切换照片后开关与预设正确还原。

---

## 6. 明确不做

- 不修改 `spektrafilm` 显影 / 扫描管线。
- 不新增外部边框图片素材。
- 不改变「调色台与显影台完全独立」的既有边界（边框只在显影台 GUI 层合成）。
- 不改动 `display.white_padding` 的取值范围与滑杆位置。
