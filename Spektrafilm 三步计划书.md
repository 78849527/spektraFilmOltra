# Spektrafilm / OltraFilm 三步开发计划书

- 日期：2026-11-02
- 工作分支：`OltraFilm`（已从 `main` 切出，未改动任何代码）
- 范围：只改 `src/spektrafilm_gui/` 与 `tests/gui/`；`src/spektrafilm/`、`tests/baselines/` 一行不动
- 依据：《欧创 Quick Film Controls Engine 技术开发规范 V1.0》+ 现有 Spektrafilm 源码核对结果

---

## 0. 结论先行

1. **旧快速模式推倒重做**：它是把 Lightroom 的 15 个名词硬套到 Spektra 物理字段上，其中至少 6 项语义错误或重复（详见 1.2）。新方案改为 **9 个物理控制 + 基线锚定 + Custom 状态**。
2. **显影台只微改**：右上角主按钮由「导出」改为「调色」，导出收进右侧箭头菜单；三栏布局、左胶片/相纸、中预览/胶片条、右快速/专业全部保留。
3. **调色台是独立第三页**：输入固定为 **16-bit、线性、ProPhoto RGB 的 TIFF**（最大宽容度、可逆、Lightroom 生态可读），内部做非破坏式二次调色，不做胶片模拟。

```
主页（照片库/工程索引）
   └─ 点击照片 → 显影台（胶片/相纸 + 预览 + 快速/专业）
          ├─ 右上「调色」→ 调色台（LUT/预设 + 预览 + Lightroom 式调参）
          └─ 右上箭头「直接导出」→ PNG 90%
```

---

## 0.1 已核对的代码事实

| 事实 | 位置 | 对设计的影响 |
|---|---|---|
| `camera.exposure_compensation_ev` 在 `filming.expose` 里以 `raw *= 2**EV` 作用于线性原始图；自动曝光在其之前的 `preprocess` 里单独叠加 | `runtime/stages/filming.py:40-58`、`pipeline.py:200-204` | 「拍摄曝光」必须独立于「印相明暗」，自动曝光开着时它仍然有效 |
| `print_exposure_compensation=True` 时，印相中灰参考会用同一个 EV 重新计算，自动抵消相纸亮度变化 | `filming.py:125-133`、`printing.py:102-116` | 拖「拍摄曝光」可能只改变密度/宽容度而不改整体亮度，UI 必须提示 |
| `enlarger.print_exposure` 在印相阶段 `raw *= print_exposure`，值越大相纸受光越多、正片越暗 | `printing.py:54` | 「印相明暗」用 `print_exposure = b * 2**(-EV)`，与相机 EV 方向统一 |
| `density_curves_morph.gamma_factor` 通过 `centers/gamma`、`sigmas/gamma` 围绕 log 曝光 0 伸缩，中灰不动 | `utils/morph_curves.py:206-231` | 它是真正的「围绕中灰的反差」，可以单独作为快速项，不必再写胶片 gamma |
| `dir_couplers.amount` 乘的是整个抑制矩阵（含对角线与层间项） | `model/couplers.py:55-66,125-126` | 它同时改变反差与色彩，**不能**当饱和度滑块；色彩项应只动 `inhibition_interlayer` |
| 颗粒核心是 `particle_area_um2`（每像素粒子数）与 `density_min`（密度地板），`uniformity` 影响噪声均匀度，`blur` 影响颗粒边缘 | `model/grain.py:67-105` | 颗粒拆成「强度」「尺寸」两个子控制，不能只写 `density_min` |
| 扫描顺序是 `lens_blur` → `unsharp_mask` | `runtime/stages/scanning.py:123-128` | 「扫描清晰度」负半轴加模糊、正半轴加 USM，不能同时乱写 |
| 输出色彩由 `XYZ_to_RGB(color_space=output_color_space, apply_cctf_encoding=...)` 决定 | `scanning.py:79-97` | 调色台交接图可另跑一次「ProPhoto + 不编码 CCTF」的全尺寸模拟，直接得到线性广色域像素 |
| 保存层已支持 16-bit TIFF 与 ProPhoto 线性 ICC（`LargeRGB-elle-V2-g10.icc`） | `utils/io.py:128-150,226-280` | 交接格式无需改核心，复用现有 OIIO 写出 |
| GUI 强制 `preview_mode=False`，预览与全尺寸使用同一套颗粒/锐化参数 | `controller.py:992-998` | 快速模式的颗粒、清晰度在预览里看得见，不需要降级 |

---

## 0.2 全局约束

- 不改 `RuntimePhotoParams` 的字段、单位、值域、默认值；不改 `collect_gui_state → build_params_from_state → digest_params` 数据流。
- 快速模式不得建立第二套物理参数；所有写入最终都落到 `GuiState` 的现有字段。
- 新代码不引入大型依赖；调色用 NumPy / SciPy / scikit-image / colour-science 完成。
- 每步结束必须：`pytest tests/gui` 全绿 + 核心数值回归无新增失败 + 手工冒烟。
- 用户验收前不打包、不合并回 `main`。

---

# 第一步：快速模式（删除旧实现，0 → 1 重做）

## 1.1 目标

- 用户不需要懂 Gamma、DIR Couplers、Halation、密度曲线，也能在 9 个控制内完成胶片风格调整。
- 快速与专业始终共用同一份 `GuiState`；切换模式本身不修改任何参数。
- 每个控制「0 = 当前工程基线」，正负方向明确，极值有安全限，不会出全黑/全白/全灰。
- 专业模式改了某控制拥有的字段后，快速面板显示 **Custom**，不静默覆盖。
- 快速意图随工程保存，重新打开后恢复。

## 1.2 旧实现必须删除的内容与理由

**删除：**

- `src/spektrafilm_gui/quick_mode.py`（整个文件）
- `parameter_deck.py` 里的 `QuickSliderRow`、`_quick_params`、`_quick_rows`、`_on_quick_change`、`_sync_quick_from_state` 与快速页构建逻辑
- `tests/gui/test_quick_mode.py`（旧断言全部作废）
- `controller.py` 的 `_quick_mode_active` / `_active_simulation_quick_mode` 与退化画面提示（改由通用预览保护承接）
- `param_manifest.py` 不动；它仍是专业面板的唯一范围声明源

**旧映射的具体问题：**

| 旧快速项 | 旧写法 | 问题 |
|---|---|---|
| 曝光 | 写 `enlarger.print_exposure` | 名为「曝光」，实际是印相曝光；和相机曝光混为一谈 |
| 对比度 | 同时写 `chemistry.gamma_factor` 与 `film_render.density_curve_gamma` | 两个不同阶段的 gamma 双写，反差被放大两次 |
| 阴影 / 高光 | 写 `gamma_factor_fast/slow` | 这两个字段是印相曲线的快/慢层，不是传统阴影/高光提亮 |
| 白色 / 黑色 | 写 `scanner.white_level/black_level` 并开关校正 | 这是扫描端的全局黑白场，容易直接切掉高光/阴影 |
| 饱和度 / 自然饱和度 | `dir_couplers.amount` / `inhibition_interlayer` | `amount` 连对角线一起乘，会同时改反差和密度 |
| 锐化 / 清晰度 | 共用 `scanner.unsharp_mask`，靠 `sigma > 1` 猜谁生效 | 两个滑块互相覆盖，还会把默认 `(0.7, 0.7)` 改成 `(0.7, 0)` |
| 颗粒粗细 | 0 值把 `particle_area_um2` 写成 0.05 | 忽略 Profile 默认 0.2，进入快速模式即改变外观 |
| 全部 | 切换模式时从专业参数反推 | 没有用户意图持久化，专业一改快速值就漂移，也没有 Custom 态 |

## 1.3 九个控制（新快速模式的全部主控制）

符号：`q` = 快速值，`b` = 该控制进入工程时捕获的原生基线值，`clamp(x, lo, hi)`。

### 光调

**1. 拍摄曝光**
- 原生路径：`camera.exposure_compensation_ev`（GUI：`state.camera`）
- 范围：`q ∈ [-3, +3] EV`，step 0.1
- 映射：`value = clamp(b + q, -5.0, +5.0)`
- 说明：自动曝光开启时依然叠加；`print_exposure_compensation=True` 时亮度会被印相抵消，只改变底片密度与宽容度。行内显示「印相随动中」提示，但**不写** `print_exposure_compensation`。

**2. 印相明暗**
- 原生路径：`enlarger.print_exposure`（GUI：`state.simulation.enlarger`）
- 范围：`q ∈ [-2, +2] EV`，step 0.05
- 映射：`value = clamp(b * 2**(-q), 0.125, 8.0)`
- 说明：+EV = 更亮；基线通常是 1.0。

**3. 影调反差**
- 原生路径：`print_render.density_curves_morph.gamma_factor` + `.active`
- 范围：`q ∈ [-100, +100]`
- 映射：`value = clamp(b * (1 + 0.35 * q / 100), 0.55, 1.8)`；`q != 0` 时 `active = True`，`q == 0` 时恢复基线 `active`
- 说明：围绕中灰的反差；不再联动 `film_render.density_curve_gamma`。胶片反差留在专业页。

### 色彩

**4. 印相色彩（二维）**
- 原生路径：`enlarger.y_filter_shift`、`enlarger.m_filter_shift`
- 范围：`x, y ∈ [-100, +100]`
- 映射：`y_filter_shift = clamp(b_y + 40 * x / 100, -60, +60)`；`m_filter_shift = clamp(b_m + 40 * y / 100, -60, +60)`
- UI：二维色盘 + 两个 CC 读数；双击回中。
- **方向待标定**：按代码推测 Y+ 偏冷、M+ 偏绿（相纸减色法），但必须用中性灰卡实测后锁符号；标定前界面只写「暖冷 / 品红-绿」。

**5. 色彩浓度**
- 原生路径：`film_render.dir_couplers.inhibition_interlayer` + `.active`
- 范围：`q ∈ [-100, +100]`
- 映射：`value = clamp(b * (1 + 0.5 * q / 100), 0.5, 1.5)`；`q != 0` 时 `active = True`
- 说明：只动层间抑制（离对角线），**不动** `amount`、`inhibition_samelayer` 与 gamma 矩阵。这是「色彩浓度」，不是 Lightroom Saturation 语义。

### 质感

**6. 颗粒（强度 + 尺寸）**
- 原生路径：`film_render.grain.active`、`.density_min`、`.uniformity`、`.particle_area_um2`、`.blur`
- 强度 `q ∈ [-100, +100]`：
  - `density_min = clamp(b_d * (1 + 0.9 * q / 100), 0.005, 0.08)`（RGB 三元组同值）
  - `uniformity = clamp(b_u - 0.06 * q / 100, 0.90, 0.995)`
  - `q <= -99` → `active = False`；否则恢复基线 `active`
- 尺寸 `q ∈ [-100, +100]`：
  - `particle_area_um2 = clamp(b_a * 2**(0.9 * q / 100), 0.03, 1.2)`
  - `blur = clamp(b_blur * (1 + 0.25 * q / 100), 0.4, 1.2)`
- 说明：`particle_scale`、`particle_scale_layers`、`sublayers_active`、`micro_structure` 不动。

**7. 光晕（强度 + 范围）**
- 原生路径：`film_render.halation.active`、`.halation_amount`、`.halation_spatial_scale`
- 强度 `q ∈ [-100, +100]`：`halation_amount = clamp(b_h * (1 + 1.2 * q / 100), 0, 3.0)`
- 范围 `q ∈ [-100, +100]`：`halation_spatial_scale = clamp(b_s * 2**(0.6 * q / 100), 0.5, 2.5)`
- `强度 q <= -99` → `active = False`
- 说明：只动「片基背反射光晕」；`scatter_amount` 属于乳剂内散射（影响锐度），留在专业页。

**8. 光学柔化**
- 原生路径：`camera.diffusion_filter.active`、`.strength`（GUI：`state.camera_diffusion`）
- 范围：`q ∈ [0, 100]`
- 映射：`active = q > 0`；`strength = 0.125 + 1.375 * q / 100`（对应商用 1/8 → 2 档）
- 说明：首版只控制相机端柔光镜；放大机端 `enlarger.diffusion_filter` 留在专业页。`filter_family`、`spatial_scale`、halo 参数不动。

**9. 扫描清晰度**
- 原生路径：`scanner.unsharp_mask`、`scanner.lens_blur`
- 范围：`q ∈ [-100, +100]`
- 正半轴：`amount = clamp(b_amount + (1.8 - b_amount) * q / 100, 0, 2.0)`，`sigma` 保持基线
- 负半轴：`lens_blur = clamp(b_blur + 0.6 * (-q) / 100, 0, 0.8)`，USM 不动
- 说明：顺序固定为「先模糊后锐化」，与 `scanning.py` 一致；不允许用扫描锐化掩盖前级光学模糊。

## 1.4 基线锚定模型

为什么不直接用 0 = 出厂值：

- 颗粒默认 `density_min=0.03`、扫描 USM 默认 `(0.7, 0.7)`、光晕默认 `halation_amount=1.0`，都不是「中性 0」。
- 不同 Film / Print Profile 换片后会通过 `apply_profile_defaults → digest_after_selection` 刷新物理默认值。
- 旧实现一旦拖动就覆盖这些默认值，导致「进快速模式先丢一半胶片特征」。

新模型：

1. 打开工程或切换胶片/相纸时，为每个控制捕获 **baseline**：该控制所有 owned path 的当前原生值（含 bool / tuple）。
2. 快速值 `q=0` 表示「保持 baseline」，不做任何写入。
3. `q` 偏离 0 时，只把 `map(q, baseline)` 的结果写回 owned paths。
4. 反向拖动回 0 可逐位恢复 baseline。
5. 专业模式改动后，用 `map(q, baseline)` 的期望值与当前原生值比较；不一致 → 该控制 `custom`。
6. 用户主动拖动该控制时才覆盖其 owned paths，并清除该控制的 custom 标记。

## 1.5 模块与数据流

```
src/spektrafilm_gui/
  quick_controls.py    # 9 个控制声明：id/标签/分组/范围/单位/owned paths/映射函数（纯函数，无 Qt）
  quick_engine.py      # baseline 捕获、apply、status、reset、序列化
  quick_panel.py       # 快速面板 UI：分组、滑块、二维色盘、Custom 徽标、逐行复位
  parameter_deck.py    # 只负责把 quick_panel 放进「快速」页；保留快速/专业分段控件
```

写入流程（不新增第二套状态）：

```
QuickPanel 拖动
  → QuickEngine.apply(q, control, state)   # 克隆 GuiState，仅改 owned paths
  → apply_gui_state(new_state, widgets)    # 专业面板同步显示新值
  → controller.request_auto_preview()
  → WorkspaceWindow._schedule_persist()
```

专业 → 快速：

```
ParameterDeck._on_change()
  → 只更新快速面板的 custom 徽标（不重新同步滑块值，不覆盖用户意图）
切换到「快速」页
  → QuickEngine.refresh_status(state)      # 只读比较，不写参数
```

## 1.6 快速面板 UI

- 三组卡片，沿用 `GroupLabel` / 行高 / 12px 读数 / 11px 滑块手柄：
  - 光调：拍摄曝光、印相明暗、影调反差
  - 色彩：印相色彩（2D 色盘）、色彩浓度
  - 质感：颗粒（强度/尺寸）、光晕（强度/范围）、光学柔化、扫描清晰度
- 每行：标签 / 滑块 / 读数 / 状态点；双击标签复位到 `q=0`。
- Custom 态：读数旁小圆点 + tooltip「专业模式已改动，拖动将覆盖该控制的 N 个字段」；不弹确认框。
- `q=0` 时读数显示 `0` 而非物理原值；物理原值放在 tooltip。
- 二维色盘：十字线、中心复位、四角方向标签；下方显示实际 `Y/M CC` 值。
- 顶部保留「快速 / 专业」分段控件与脏参数计数；「重置」仍是整工程重置，快速面板内另有「重置快速」小按钮（只把 9 个控制的 owned paths 恢复到 baseline）。

## 1.7 持久化

在现有 `LibraryItem.state`（`gui_state_to_dict` 的字典）里新增旁路小节，不改变原有字段：

```json
"quick": {
  "schema": 1,
  "baseline": {
    "camera_exposure": {"camera.exposure_compensation_ev": 0.0},
    "print_brightness": {"simulation.enlarger.print_exposure": 1.0},
    "tonal_contrast": {"chemistry.gamma_factor": 1.0, "chemistry.active": true}
  },
  "intent": {
    "camera_exposure": 0.0,
    "print_brightness": 0.0,
    "tonal_contrast": 0.0
  },
  "updated_at": 0
}
```

- 打开工程：先 `apply_gui_state` 恢复原生参数，再读 `quick`；缺失则捕获当前值为 baseline、intent 全 0。
- 保存：由现有 1.5s 防抖持久化统一写入，不新增文件。
- 切换胶片/相纸：重捕 baseline → 保留 intent → 重新应用 → 全部重算状态。
- 整工程重置：清空 quick 小节，重新捕获 baseline。

## 1.8 测试与验收

新增 `tests/gui/test_quick_engine.py`、`tests/gui/test_quick_panel.py`：

1. `q=0` 对每个控制逐位恒等（bool/tuple 也比）。
2. 每个控制只改 owned paths；用全字段快照 diff 断言其他字段零变化。
3. 单调性：`-100 → +100` 目标值单调不反向。
4. 安全限：极值不越界；颗粒 `q=-100` 时 `active=False`。
5. Custom：专业模式改一个 owned 字段 → 对应控制 custom；拖动该控制后恢复 normal。
6. 持久化：保存 → 重开 → baseline/intent/status 一致。
7. 换片：切换 Film/Print 后 baseline 更新、intent 保留、无字段残留。
8. UI：9 个主控制 + 子控制存在；双击复位；Custom 徽标出现/消失。
9. 回归：`pytest tests/gui -q` 全绿；核心 `pytest tests -q -k "not gui"` 无新增失败。

手工冒烟：打开工程 → 9 个滑块各拖到两端 → 画面无全黑/全白 → 切专业确认字段随之变化 → 专业改 gamma → 切快速看到 Custom → 拖动该行 → Custom 消失 → 返回主页再打开，值恢复。

## 1.9 第一步风险 / 待标定

- 印相滤色片方向（Y/M 正负）必须用中性灰卡实测后锁死；未标定前只上 UI，不写死文案。
- `print_exposure_compensation` 与「拍摄曝光」的联动需要在 UI 上解释清楚，否则用户会觉得滑块「没用」。
- 颗粒强度与尺寸极端组合可能出现块状噪声，需 100% 视图检查，必要时收窄上限。
- `scanner.unsharp_mask` 默认 amount 0.7 较强，正半轴上限 1.8 需实拍验证边缘光晕。

---

# 第二步：显影台 UI 整改（微改）

## 2.1 顶栏

- `EditorTopBar`（`editor_page.py:45-148`）改为：
  - 左：返回照片库（保留）
  - 中：文件名 + 元信息（保留）
  - 右：阶段进度（保留）→ 收藏（保留）→ **主按钮「调色」** → 箭头菜单
- 箭头菜单：
  1. 直接导出（当前工程）
  2. 导出设置…
  3. 另存为…
- 「调色」点击条件：当前模拟结束；正在渲染时置灰并提示「显影完成后再调色」。
- 「调色」按钮带状态点：该工程已有调色配方时显示黄铜小点。

## 2.2 直接导出

- 新增独立配置 `DirectExportSettings`（不覆盖导出面板里的完整设置）：
  - 格式：PNG
  - 长边：原尺寸的 90%（按你的原话执行；PNG 无「质量」参数，见 5.1）
  - 压缩：9（最高，无损）
  - 位深：8-bit（当前核心 PNG 写出为 uint8）
  - 目录：源文件目录；文件名模板沿用 `{name}_spektrafilm`
- 导出面板（`export_dialog.py`）保留完整能力：JPEG/PNG/TIFF/EXR、位深、画质、长边、目录、模板、另存为。
- 直接导出也复制 EXIF/IPTC/XMP（复用 `_write_export_metadata`）。

## 2.3 显影台其余部分

- 左：胶片/相纸预设栏保持现状；仅把「胶片 / 相纸」切换与搜索的间距再对齐一次，不重构。
- 中：预览、渲染档位、工具条、胶片条保持现状。
- 右：快速/专业分段控件保持；快速页换成第一步的新面板；专业页一字不改。
- 照片库：卡片增加「已调色」角标（读 `item.state.grade` 是否存在）；双击进入显影台不变。

## 2.4 验收

- 顶栏在 1180px 最小宽度下不挤动：文件名省略、阶段文字固定宽、按钮不换行。
- 点击「调色」必须完成一次全尺寸交接（或复用已缓存交接），进度条走真实阶段。
- 直接导出产物：PNG、90% 长边、可被系统预览打开、EXIF 保留。
- `pytest tests/gui` 新增顶栏/导出/导航测试全绿。

---

# 第三步：调色台

## 3.1 定位

- 不做胶片模拟、不碰 `src/spektrafilm/`；只对「已经显影完成的图像」做二次调整。
- 交互沿用同一套壳：左预设/LUT、中预览、右调参、右上导出。
- 非破坏式：原始显影结果与调色配方分离保存，随时可关掉调色回到显影台。

## 3.2 交接图像格式（最大宽容度）

**主格式：16-bit TIFF / ProPhoto RGB / 线性（不编码 CCTF）/ 内嵌 ICC**

理由：

- 16-bit 每通道 65536 级，阴影和高光过渡不会被 8-bit 量化。
- 线性编码保留相纸扫描的真实亮度关系，调色台做曝光/高光恢复时不会先被 display gamma 压扁。
- ProPhoto RGB 覆盖范围远大于 sRGB，能容纳胶片的高饱和染料色，不在交接时提前切色域。
- 现有核心已能写出该组合：`save_image_oiio(..., bit_depth=16, color_space='ProPhoto RGB', cctf_encoding=False)`，且 `_ICC_FILENAMES` 已有 `LargeRGB-elle-V2-g10.icc`。
- Lightroom / Photoshop / Capture One 可直接读取，便于用户带走。

**备选：32-bit float EXR**（仅当需要保留 >1.0 的高光余量或做 HDR 往返时）。

**生成方式：**

1. 点击「调色」时，若该工程没有交接图或显影参数指纹已变：
   - 克隆当前 GUI 参数；
   - 仅覆写 `params.io.output_color_space='ProPhoto RGB'`、`params.io.output_cctf_encoding=False`、`params.settings.preview_mode=False`；
   - 跑一次全尺寸 `Simulator.process`；
   - 保存到 `应用数据/library/projects/<item_id>/handoff.tif`；
   - 在 `item.state['grade']['handoff']` 记录 `{path, fingerprint, width, height, format}`。
2. 指纹 = 现有显影参数字典的哈希（film/print + 所有 `film_render/print_render/camera/enlarger/scanner/io` 字段），显示/预览偏好不计入。
3. 同一工程再次进入调色，指纹一致则直接读文件，不重复显影。
4. 调色预览使用内存中的 float32 代理图（长边 1600），导出时才读全尺寸 TIFF 分块处理。

## 3.3 调色引擎范围（v1）

工作空间：**线性 ProPhoto RGB，float32**；显示/导出时再转目标色彩空间并编码 CCTF。

调整顺序（固定，写入配方版本号）：

```
白平衡（色温/色调）
→ 曝光
→ 高光/阴影/白色/黑色
→ 对比度
→ 参数曲线
→ HSL（8 色相 × 色相/饱和/明度）
→ 颜色分级（阴影/中间调/高光 三向轮）
→ 清晰度/纹理/去雾
→ 锐化/降噪（亮度/色彩）
→ 暗角/颗粒
→ LUT（.cube，可调强度）
→ 输出色彩管理
```

v1 模块：

- 基本：曝光 EV、对比度、高光、阴影、白色、黑色、色温、色调、自然饱和度、饱和度
- 曲线：参数曲线（阴影/暗部/亮部/高光）+ 点曲线
- 色彩混合：8 色相 HSL
- 颜色分级：三向色轮 + 混合/平衡
- 细节：锐化（amount/radius/masking）、亮度降噪、色彩降噪
- 效果：清晰度、纹理、去雾、暗角、颗粒
- 几何：裁切、旋转/拉直、比例锁定
- LUT：`.cube` 导入、强度、删除/重命名
- 预设：内置 + 用户预设；应用/另存/重命名/复制/删除/导入/导出 JSON
- 历史：撤销/重做（配方快照，上限 50 步）、前后对比

不在 v1：局部蒙版/画笔、AI 降噪、镜头畸变校正、HDR 合成、多图同步。

## 3.4 开源参考与选型

| 项目 | 技术栈 / 许可 | 可借鉴 | 不建议 |
|---|---|---|---|
| **RapidRAW** | Tauri + Rust + React，GPL-3.0（以仓库 LICENSE 为准） | 最接近现代 Lightroom 的信息架构、预设/LUT 交互、前后对比 | 不整体嵌入；wgpu 管线与 Qt/Python 不兼容 |
| **ART (artpixls/ART)** | C++ / GTK，GPL-3.0 | 「基本/曲线/HSL/颜色分级/细节」面板分组与参数语义 | 不搬 GTK 代码 |
| **darktable** | C / GTK，GPL-3.0 | 高光恢复、tone equalizer、color balance RGB 的数学公式 | 不搬整机管线 |
| **Filmulator** | Qt / C++，GPL-3.0 | 三栏 Qt 布局、轻量相册-编辑切换 | 其胶片显影模型不用于二次调色 |

结论：

- **UI/交互参考 RapidRAW**；**算法参考 darktable + ART**；**Qt 布局参考 Filmulator**。
- 只在 Python 里重写公式与参数语义，不嵌入 C++/Rust 引擎。
- 开工前用 GitHub LICENSE 复核许可；GPLv3 兼容后，在 `src/spektrafilm_gui/grade/ATTRIBUTION.md` 记录来源与改写范围。

## 3.5 调色台页面结构

```
GradePage
├─ GradeTopBar     返回显影台 · 文件名 · 前后对比 · 导出 + 箭头菜单
├─ QSplitter
│   ├─ GradeRail（左，260px）
│   │   ├─ Tab: LUT（.cube 列表、缩略图、导入）
│   │   └─ Tab: 预设（内置 / 我的；卡片：名称+缩略图+来源）
│   ├─ GradeCanvas（中）
│   │   └─ QGraphicsView：缩放/平移/适应窗口/前后分割
│   └─ GradeDeck（右，320px）
│       ├─ 直方图
│       └─ 可折叠模块：基本 / 曲线 / 色彩混合 / 颜色分级 / 细节 / 效果 / 几何
└─ 底部状态行：尺寸 · 色彩空间 · 预览倍率
```

- 视觉 token 全部复用 `theme_oflim.py`；组件复用 `Tabs`、`ElidedLabel`、`GroupLabel`、`shell_icons`、`motion`。
- 预览画布不复用 napari viewer（避免两个页面争用同一个 viewer widget），用 `QGraphicsView` 自绘。
- 右侧参数行沿用第一步的行高/读数/滑块规范，保证两页手感一致。

## 3.6 配方与持久化

```json
"grade": {
  "schema": 1,
  "handoff": {"path": ".../handoff.tif", "fingerprint": "...", "format": "tiff16-prophoto-linear"},
  "recipe": {
    "basic": {"exposure": 0.0, "contrast": 0.0, "highlights": 0.0, "shadows": 0.0, "whites": 0.0, "blacks": 0.0, "temperature": 0.0, "tint": 0.0, "vibrance": 0.0, "saturation": 0.0},
    "curve": {"parametric": [0, 0, 0, 0], "points": []},
    "hsl": {},
    "color_grading": {},
    "detail": {},
    "effects": {},
    "geometry": {},
    "lut": {"path": "", "strength": 1.0}
  },
  "preset_id": "",
  "updated_at": 0
}
```

- 存在 `LibraryItem.state` 里，随现有防抖持久化走；交接图是独立文件，不塞 JSON。
- 配方默认值 = 全部中性，应用后与交接图逐位一致（identity 测试）。
- 导入预设 JSON 必须校验 schema、字段类型、数值范围；拒绝任意路径与可执行内容。

## 3.7 调色台测试与验收

- 交接：格式/位深/色彩空间/ICC 正确；同一指纹不重复显影；显影参数改动后指纹失效并重建。
- 引擎：所有默认值恒等；每个滑块方向正确；极值不崩；HSL 对中性色不移动；LUT 插值正确。
- 持久化：调色 → 关闭 → 重开 → 配方与画面一致；删除交接图后能自动重建。
- 导航：显影台 ↔ 调色台往返不丢状态；正在显影时禁止进入。
- 导出：调色导出与预览一致（同一配方、同一色彩管理），支持 JPEG/PNG/TIFF/EXR。
- 性能：代理预览拖动不排队、过期任务可丢弃；全尺寸导出分块处理，内存不爆。

---

## 4. 提交与验收节奏

| 阶段 | 提交内容 | 验收 |
|---|---|---|
| 第一步 | 删除旧 quick；新增 engine/panel/tests；不改核心 | GUI 测试全绿；9 控制手工冒烟；Custom 态可见 |
| 第二步 | 顶栏调色入口；直接导出；库角标 | 导航、导出、几何审计通过 |
| 第三步 | handoff 服务；调色页；引擎；预设/LUT；导出 | 三段流程完整跑通；核心回归无新增失败 |

每阶段结束汇报：修改文件清单、实际完成项、测试结果、未验证/实验项。

---

## 5. 待你确认（开工前）

### 5.1 「90% 质量的 PNG」

PNG 是无损格式，没有「质量」参数。二选一：

- **A（推荐，按字面）**：直接导出 = PNG，长边缩到原图 90%，压缩 9。
- **B**：直接导出 = PNG，原尺寸，压缩 9（视觉无损，「质量」视为 100%）。

我按 A 写进了计划；你确认后我再落地。

### 5.2 快速模式是否保留「拍摄曝光」

它和「印相明暗」是两个物理阶段。保留会让 9 项更完整，但 `print_exposure_compensation=True` 时拖动它主要改变宽容度而不是亮度。若不保留，可换成「胶片反差」（`film_render.density_curve_gamma`）。

### 5.3 调色台是否要局部蒙版

v1 计划不做蒙版/画笔。若你要「完整 Lightroom 逻辑」，蒙版应作为 v2 单独立项。

### 5.4 调色台交接是否允许额外一次全尺寸显影

为保证 ProPhoto 线性输出，进入调色台时需额外跑一次全尺寸模拟（不改变屏幕显示的 sRGB 结果）。若不允许，可退化为从现有 float 输出做色彩空间转换，精度略低但不再计算。

---

## 6. 明确不做

- 不改 `src/spektrafilm/` 的任何物理算法、数据、LUT、ICC。
- 不把调色台做成第二个胶片模拟器。
- 不引入 Electron/Web 前端或 Rust 引擎。
- 不在快速模式里复制整套专业参数。
- 不为通过测试而删除断言或放宽数值基线。
- 不在用户验收前打包 DMG。
