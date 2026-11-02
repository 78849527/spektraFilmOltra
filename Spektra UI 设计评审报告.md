# Spektra UI 设计评审报告

**评审对象**：`src/spektrafilm_gui/`（Python/Qt + napari 桌面 GUI，约 1.5 万行）
**评审基准**：`../Oflim/`（SwiftUI 原生 macOS 暗房应用）——其 `DESIGN.md` 为团队认可的 UI 标杆
**评审方法**：impeccable critique 规范。Assessment A：隔离子代理设计评审（通读基准 4 个核心文件 + 对象 30 余个文件）；Assessment B：确定性扫描（`impeccable detect` 对 Qt 原生应用 0 findings——检测器只读 web markup，此结果不构成"干净"证据，浏览器证据在本平台不适用）
**评审日期**：2026-11-01
**总分**：**21 / 40 — Acceptable（下半区）**
**快照存档**：`.impeccable/critique/2026-11-01T01-44-00Z__src-spektrafilm-gui.md`（首次评审，暂无趋势基线）

---

## 一、评审基准摘要（oflim 标准）

oflim 的世界观是「关灯后 safelight 暖起来的工业暗房」：近黑表面五级阶梯（#0B0B0B → #262624，相邻 1–3% 亮度差）、**唯一强调色黄铜 #C8A97E**（没有第二色相与照片竞争）、1px 发丝线分隔（white 4.5%，无黑边）、SF Pro 单字体家族 + 暗色字重降一档、8.5–10pt 大写加字距的区块标签、所有数值 tabular-nums 等宽数字、iOS 弹簧动效规格（280ms expo-out / spring 0.34-0.82）、Toast 与「正在显影」进度层、带齿孔与黄铜光圈的空态胶片框。禁令：无嵌套卡片、无彩色左边框、无渐变文字、无 emoji 图标、平台控件优先。

## 二、Nielsen 十项评分

| # | 启发式 | 分 | 关键问题 |
|---|--------|----|----------|
| 1 | 系统状态可见性 | 2 | 导出/全尺寸扫描只有状态栏一行字（controller.py:784），无进度覆盖层、无取消，导出按钮不置灰（editor_page.py:71） |
| 2 | 贴近真实世界 | 3 | 中文暗房词汇极好，但字段级 tooltip 大量英文回退（i18n.py:206 仅 15 条译文），出现 'napari layers' 英文区块 |
| 3 | 用户控制与自由 | 2 | 全程无撤销；无 before/after 分屏对比；「从库中移出」无确认（library_page.py:1120） |
| 4 | 一致性与标准 | 2 | px/pt 混排、双文本主色、双焦点样式、双色板系统、彩色左边框、macOS 无暗色标题栏（napari_layout.py:159 仅 win32） |
| 5 | 错误预防 | 2 | 缺失文件有守卫（workspace.py:163），但模拟中导出按钮可点、移出库无确认 |
| 6 | 识别而非回忆 | 3 | 同一参数三套名字（友好/精确/英文）迫使用户记映射 |
| 7 | 灵活与高效 | 1 | **全 GUI 零快捷键**（无 QShortcut/QKeySequence）；自绘 Tabs/ToggleSwitch 纯鼠标操作 |
| 8 | 美学与极简 | 2 | 26 枚黄铜区块图标稀释强调色；红黄绿蓝四色标签 dots 与 7 个 filter chips 同屏 |
| 9 | 错误恢复 | 2 | QMessageBox 直接倾倒异常文本（controller.py:820、workspace.py:202），无 toast 体系 |
| 10 | 帮助与文档 | 2 | tooltip 覆盖率高是优点，但无 onboarding、无帮助菜单，隐藏知识全靠悬停 |
| | **总分** | **21/40** | **Acceptable（20–27 带的下半区）** |

## 三、设计专属性判定

**这套 UI 移植了 oflim 的皮肤 tokens，没有移植 oflim 的纪律，更没有建立自己的世界观。**

- **认真的一半**：`theme_oflim.py:15-42` 一比一搬来表面五级阶梯、黄铜、发丝线、圆角；`parameter_deck.py` 的 38px 行高、等宽读数、双击重置、直方图卡逐条对应 oflim InspectorView。这是成体系的移植，不是随手套皮。
- **失守的一半**：DESIGN.md:66「唯一强调色」全面失守——`icons.py:17-44` 给 26 个折叠区块每个都配黄铜图标；`library_page.py:54-59` 引入红/黄/绿/蓝四色标签并做成常驻 filter chips；`theme_shell.py:335-342` 选中预设卡用 3px 彩色左边框，DESIGN.md:148 明令禁止。黄铜在 oflim 是「黑暗房间里的安全灯」，在 spektra 是撒在每一行标题上的调料。
- **双轨制暴露三次改版的地质层**：活动壳层（workspace/editor_page/parameter_deck）之外，`napari_layout.py:690` 旧主窗（'spektrafilm' 小写标题、'●'字符当 logo）、`inspector_simple.py:344` InspectorPanel、`parameters_panel.py:132` 六页签整套是死代码。两套文本主色（`#C9C9C9` vs `#FFFFFF`）、两套焦点样式（黄铜 55% vs white 9%）、两套色板绘制系统同屏共存。这不是被设计出来的产品，是未被收拾的工 地。
- **最典型的个性缺席**：oflim 要求「照片打开后，胶片卡缩略图换成当前照片的动态预览」（DESIGN.md:79-80）。spektra 有整套缩略图服务（library_thumbs.py）却仍用品牌+哈希色相的程序化渐变色块（preset_rail.py:68-126）；LookCard 无论选什么胶片都显示同一个黄铜渐变（widget_lookcard.py:39-63）。oflim 的每个像素在说「这是你的照片的暗房」，spektra 的界面在说「这是一个装了很多滑块的 Qt 窗口」。

## 四、认知负荷：失败 4/8（工具型应用可接受上限为 2）

| 检查项 | 结论 | 证据 |
|--------|------|------|
| 每屏单一焦点 | 通过 | 编辑页四区结构与 oflim 布局同构 |
| 分块 ≤4 | 通过 | ParameterDeck 四页：光影/色彩/胶片/画面 |
| 明确分组 | 通过 | GroupLabel + 组间距 |
| 视觉层级 | **失败** | 暗色下满屏 600 字重（theme_shell.py:57,75,82,245），违反「暗色字重降一档」，层级被压平 |
| 一次一事 | 通过 | 打开→调参→导出链路清晰 |
| 可见选项 ≤4 | **失败** | 库页首同屏 7 chips + 搜索 + 排序 + 4 钮（library_page.py:743-751） |
| 工作记忆 | **失败** | LIGHT_PAGE 16 行、FILM_PAGE 18 行一屏滚完，同参数三处换名 |
| 渐进披露 | **失败** | ParameterDeck 全部行常开无折叠；真正的渐进披露（六页签）在死代码里 |

## 五、情感旅程

第一印象尚可（库页 26px 大标题 + 大缩略图网格）。高峰是双击重置的 140ms 淡入与黄铜开关拖尾。**结尾与风险时刻塌方**：点导出进入可能数十秒的全尺寸扫描，屏幕上只有状态栏一行字沉默等待；RAW 打不开时弹出倾倒异常字符串的模态框；关闭窗口时被「显影计算还没有结束」拒绝——没有安抚、没有进度、没有预估。oflim 为同样的时刻准备了 ExportProgressOverlay（「正在显影」）与 toast，spektra 全部交给 Qt 默认对话框。

## 六、做得好的（保持不动）

1. **`parameter_deck.py`**——全包最接近标杆的文件：38px 行高 + 标签/读数上下两行、Menlo 等宽读数且仅「改过」时变黄铜、双击标签重置、脏参数计数徽章、74px 直方图卡带 1.3px 字距微型标签。
2. **`ui_names.py` 文案分层**——友好名（亮度/明暗对比）给日常、精确名（印相曝光/胶片伽马系数）给专业，PARAM_TIPS 全部用效果语言（「往左偏冷（蓝），往右偏暖（黄）」），完全符合 DESIGN.md 文案标准。
3. **`shell_icons.py`**——全部 QPainter 手绘：2x DPR、1.6px 圆头笔触，避开 emoji/字符凑数禁令。

## 七、优先问题（P0–P3）

### 【P0】专业参数在活动编辑器中不可达（功能性回归）
- **现状**：ParameterDeck 四页只覆盖约 50 个叶子参数；`crop_center/crop_size`、`input_color_space`、`apply_cctf`、输入/输出色域压缩、光谱上采样、`preview_max_size`、`output_interpolation` 等在活动 UI 无任何入口。承载它们的 `parameters_panel.py` / `inspector_simple.py` 是死代码。
- **为什么重要**：用户买的是光谱模拟引擎，引擎的招牌能力在 UI 里消失。
- **修法**：把六页签作为 ParameterDeck 第 5 页「专业」（同一 38px 行规格）；物理删除 `napari_layout.build_main_window`、`_build_top_bar`、`_build_inspector_header`、`InspectorPanel`、`build_main_window_for_app` 全部死路径。
- 对应命令：`/impeccable distill`

### 【P0】键盘与无障碍归零
- **现状**：零快捷键（无 ⌘E 导出、⌘O 导入、空格对比）；自绘 Tabs/ToggleSwitch 无键盘焦点路径、无 QAccessible 注记；motion.py 无 reduce-motion 开关；7.5px 黄铜 26% 文本（theme_shell.py:347）在 surface-2 上对比度约 1.9:1，TEXT_4 `#424242` 用于正文 WCAG 全面不及格。
- **修法**：补 ⌘E/⌘O/⌘R/空格；自绘控件实现关键事件 + `QAccessible.setName`；全局 reduce_motion 开关；正文下限 10px，TEXT_4 只用于装饰线。
- 对应命令：`/impeccable harden`

### 【P1】强调色纪律崩坏 + 禁令违反
- **现状**：选中预设卡 3px 黄铜左边框（theme_shell.py:335-342）；下拉/菜单/列表选中项 2px 黄铜左边框（theme_styles.py:544,562,575）；26 枚黄铜区块图标 + inspectorCount 黄铜版本号 + LookCard 黄铜品牌字；红/绿/蓝标签上屏。
- **修法**：选中改整卡 1px `rgba(ACCENT,0.72)` 描边 + surface-2 + 右侧 3.5pt 黄铜圆点（照抄 oflim FilmCard 规格）；删除三处 border-left；区块图标只留激活页签或全删（oflim 的 section 只有 chevron + 大写标签）；标签色只出现在卡片角小点，chips 行只留全部/收藏/已调整。
- 对应命令：`/impeccable quieter`

### 【P1】长任务反馈与错误呈现缺失
- **现状**：导出/全尺寸扫描只有状态栏文字，按钮不置灰、无进度、无取消、无完成提示；所有错误走 QMessageBox 倾倒异常文本。与 DESIGN.md:115 Toast 规格、:131「错误要点名文件与恢复方式」直接冲突。
- **修法**：surface-3/94% 透明度 + 偏移阴影 + 2.5s 自动消失的 toast 挂 WorkspaceWindow 顶部；ExportProgressOverlay（「正在显影」+ 状态行）；导出与扫描按钮同步置灰；错误改「人话 + 文件名 + 下一步动作」，异常详情收进「显示细节」。
- 对应命令：`/impeccable clarify`

### 【P2】文本规格失控
- **现状**：`theme_shell.py` 全 px 制 vs `widget_primitives.py` QFontDatabase 点值制，两套体系 DPI 下必然错位；TEXT_MAIN 两色并存；焦点两套样式；折叠展开零动画（widget_primitives.py:167-170 直接 setVisible）违反 280ms expo-out 规格；motion.py 170/260ms 与 oflim 180/280ms 对不上，OutBack 过冲用在 oflim 明令「zoom 无 bounce」的场景。
- **修法**：立唯一 type scale（px 制、最小 10px、全大写标签 8.5-10px + 1.2-1.7 字距）；TEXT_MAIN 统一到 white 阶；焦点统一黄铜 40% 1px；CollapsibleSection 加 280ms 高度动画；motion 时长曲线对齐，OutBack 只允许用于开关。
- 对应命令：`/impeccable typeset` + `/impeccable animate`

## 八、人物红线

- **Alex（熟练用户）**：零快捷键 + 无 before/after 对比是每天撞的墙。oflim 的 Canvas Original 玻璃按钮 + 可拖分屏在 spektra 无对应物，PreviewStage 顶只有静态「照片/底片」chip。对 Alex，这个界面是「鼠标的单行道」。
- **Jordan（新手）**：「快速预览/生成全尺寸/保存当前画面」三个词没有一个说「把调好的照片存成 JPG」（editor_page.py:87-90）；一键导出藏在顶栏主按钮里且无文案解释；RAW 失败看到栈级异常文本而非「文件是 CR3，请升级 rawpy」；空态指路「右上角导入」但按钮实际在右上角下方 88px 的页头里。
- **Sam（无障碍）**：7.5px 黄铜 26% 字不可读；Tabs/开关/滑块行键盘 Tab 无声失效；模拟中唯一状态通道是状态栏 showMessage，无 accessible event 广播，屏幕阅读器完全感知不到「正在计算」。

## 九、次要观察

- macOS 无暗色标题栏处理（napari_layout.py:159 仅 win32），默认标题栏与 46px 自绘顶栏形成双重 chrome；oflim 是 chrome-less + 居中交通灯。
- `configure_napari_chrome` 未处理 napari viewer 按钮条与 dims 轴条，画布残留 Qt 默认 chrome。
- 入口仍是 `napari.run()`（app.py:320），应用身份（菜单/关于/Dock 名）寄居在 napari 之下；`setWindowIcon(QIcon())` 空图标。
- 空态卡用虚线描边（theme_shell.py:239-241）——Bootstrap 拖放区通用语言，恰是「可替换性」的证据；空态图标是 46px 灰文件夹，oflim 是带齿孔与黄铜光圈的胶片框，世界观缺席。
- 阶梯外硬编码色散布：开关 off `#3D3D3B`（parameter_deck.py:470）、滑块 `#454543`（:214-224）、占位渐变 `#1E1E1C→#141414`（library_page.py:145-148）、星标硬编码十六进制（editor_page.py:124-137）。
- 库页计数「240 / 320 张照片」用比例字体会跳动（library_page.py:999-1000）——oflim 要求全部 tabular-nums；editorMeta 尺寸串同病。
- README 宣称的「特色 UI」（polaroid_animation、virtual_photo_paper_back）实为纯 numpy 模型代码，GUI 无任何调用点。
- 状态栏启动播报「照片库已就绪」属噪声（workspace.py:105,152）。
- 直方图三色在两个文件重复定义且无 token（inspector_simple.py:47-49、parameter_deck.py:638，死代码里还有第三份）。

## 十、发人深省的问题

1. **如果明天把黄铜换成青色、表面换成深蓝，这套界面会失去什么？** 如果答案是「什么都不会失去」，说明 spektra 还没有自己的视觉判断——oflim 的黄铜来自安全灯与齿孔的叙事，spektra 的黄铜只来自一次抄写。
2. **三个死壳层是在「保留回退能力」，还是在「推迟一个产品定义决策」？** UI 里的每一具僵尸都是一次未做的决定。
3. **当用户等 30 秒导出时，暗房 metaphor 应该发生什么？** 以「显影」为世界观的产品，在显影发生时没有任何显影的仪式感——这是检验设计专属性的试金石。

## 十一、结论与建议行动

**结论**：21/40，Acceptable 下半区。骨架（parameter_deck、ui_names、token 层）证明团队读懂过 oflim；差距在纪律的执行（强调色、禁令、字重、px/pt）、功能的诚实（死代码与不可达参数）、以及对「显影时刻」的漠视。

**建议行动**（按优先级，本轮仅记录、不执行）：
1. `/impeccable distill` — 专业参数并入第 5 页 + 物理删除死壳层（P0）
2. `/impeccable harden` — 快捷键/键盘可达/reduce-motion/对比度（P0）
3. `/impeccable quieter` — 强调色纪律与禁令修复（P1）
4. `/impeccable clarify` — Toast + 显影进度层 + 错误人话化（P1）
5. `/impeccable typeset` + `/impeccable animate` — type scale/主色/焦点/动效规格统一（P2）
6. `/impeccable polish` — 收尾质检（最后一步）
