# iOS 专项 Skills 调研报告

- 日期：2026-11-06
- 目的：为 Spektrafilm iOS 建立可长期复用的 TRAE 项目级 Skills 体系，先核查外部 Skill 的真实性、许可证与可用性，再决定采用 / 改造 / 自研。

> 核查口径：只记录**本次实际打开过**的页面信息。未逐一验证的候选在文末单独列出，不作为依据。

---

## 1. 候选与核查结果

### 1.1 采用：Dimillian/Skills

| 项 | 值 |
|---|---|
| 地址 | https://github.com/Dimillian/Skills |
| 许可证 | **MIT**（仓库 LICENSE 页确认） |
| 最近活跃 | 2026-01（LICENSE 最新提交） |
| 规模 | 16 个自包含 Skill |
| 格式 | 每个目录一份 `SKILL.md`，符合 Agent Skill 约定 |

与本项目相关的四个：

| Skill | 能提供什么 | 采用方式 |
|---|---|---|
| `swiftui-ui-patterns` | 导航、sheet、应用装配、异步状态的写法 | **参考**，不直接复制 |
| `swiftui-performance-audit` | 失效风暴、身份漂移、布局抖动、Instruments 指引 | **参考**，沉淀为 `spektra-swiftui-performance` |
| `swiftui-view-refactor` | 拆小视图、显式依赖注入、Observation | **参考** |
| `swiftui-liquid-glass` | iOS 26 Liquid Glass 正确用法 | 暂缓（当前设计是暗房石墨风格，不追 Liquid Glass） |

**结论：许可证允许商用与修改；因它是通用 SwiftUI 内容，本项目按 TRAE Skill 格式重写，只保留方法不复制文本。**

### 1.3 采用（工具方法论）：CharlesWiltgen/Axiom

| 项 | 值 |
|---|---|
| 地址 | https://github.com/CharlesWiltgen/Axiom |
| 许可证 | **MIT**（仓库 LICENSE 页确认，最新提交 2025-11-30） |
| 规模 | 289 skills / 44 agents / 18 commands |
| 自带工具 | `xcui`（模拟器 UI 与无障碍断言）、`xcprof`（xctrace 录制分析）、`xclog`（模拟器日志）、`xcsym`（崩溃符号化）、`xcbuild`（构建日志摘要） |
| 与 TRAE 的关系 | 是 Claude Code / Codex / Cursor 的原生插件形态，**不能直接作为 TRAE Skill 安装** |

**采用方式：只吸收方法论，不安装、不复制。**

- `xcui` / `xclog` 的思路 → 本项目用 `xcrun simctl` + `Tools/acceptance.sh` 复刻（已落地）。
- `xcprof` 的思路 → 用 `Tools/bench.sh`（引擎侧 Release 计时）+ Instruments 手工复核（已落地）。
- 原因：引入它的插件体系会与 TRAE 的 Skill 触发机制冲突，且本项目需要写死自己的红线常量。

### 1.4 参考：Apple 官方文档与 WWDC

| 来源 | 用途 |
|---|---|
| developer.apple.com/metal/sample-code/ | Metal 计算与渲染 sample 索引 |
| WWDC26-322《Compose advanced graphics effects with SwiftUI》 | `colorEffect` / `distortionEffect` / `layerEffect` 与 stitchable shader |
| developer.apple.com/documentation/Metal（Metal 4 inline tensor ops） | 未来 GPU 管线的可行路径 |


**用途：GPU 迁移方案的依据，不构成 Skill 内容。**

### 1.5 仅登记、未采用

| 候选 | 来源 | 不采用原因 |
|---|---|---|
| `sickn33/antigravity-awesome-skills`（ios-developer） | raw.githubusercontent 可见 SKILL.md | 未核查仓库许可证与更新时间；内容为通用 iOS 概览，无本项目所需深度 |
| `dpearson2699/swift-ios-skills`（swiftui-performance） | skill4agent.com 列表页 | 未核查仓库本体；且与 Dimillian 的 performance-audit 高度重叠 |
| `mpazaryna/claude-toolkit`（swift-ui） | skillmd.ai 列表页 | 未核查仓库本体 |
| `lev-os/swiftui-performance-audit` | skillmd.com 列表页 | 未核查仓库本体 |
| `curiositech/metal-shader-expert` | skillmd.com 列表页 | 定位是游戏渲染管线（MTKView / MetalFX），与图像处理管线的需求不同；未核查许可证 |
| `rajanthar/ce-test-xcode` | skillmd.com 列表页 | 只是「截图 + 看日志」的流程描述，本项目已用 `acceptance.sh` 覆盖；未核查许可证 |

> 以上仓库**不是不可用**，而是本轮没有完成许可证与内容核查，按「不得因开源即认定可商用」的原则暂不引入。

### 1.6 按研究方向的覆盖情况

| 方向 | 找到的可用来源 | 结论 |
|---|---|---|
| A. iOS 原生设计 | Dimillian `swiftui-ui-patterns`；Axiom 的 UI 类 skill；Apple HIG | 方法可吸收，规则需按本项目重写 |
| B. SwiftUI 动画 | Dimillian（UI patterns 内含手势/动画）；Axiom `axiom-swiftui`；Apple WWDC26-322 | 外部只有通用建议；本项目的「假循环 / 定时器接力」是具体反模式，必须自研 |
| C. SwiftUI 性能 | Dimillian `swiftui-performance-audit`；Axiom 的 audit agents；Apple Instruments | 通用失效风暴方法可用；**AttributeGraph 循环**是本项目独有教训，写进自研 Skill |
| D. 图像处理与 GPU | Apple Metal sample code；WWDC26-322；Metal 4 inline tensor ops | 无 Agent Skill 达到可用深度，全部自研 |
| E. 渲染调度 | **没有可信来源** | 完全是本项目自身工程（LUT 预测 + 精算双层），自研 |
| F. 自动化验收 | Axiom `xcui` / `xclog` / `xcprof`；Apple `xcrun simctl` | 方法论可用；TRAE 下用脚本复刻，自研 |

### 1.7 未找到可信来源的方向

- **Swift Metal 图像管线专用 Skill**：没有找到维护中的、可直接使用的 Agent Skill；Apple sample code 是唯一可靠来源。
- **渲染调度（latest-wins / 双层预览）专用 Skill**：未找到。这部分知识来自本项目自身实现（`PreviewLUTService` + `MobileDevelopSession`），只能自研。
- **iOS 视觉回归**：找到的都是「截图 + 人眼/模型检查」流程，没有像素级 diff 引擎；本项目用 `acceptance.sh` 落截图 + 日志门禁，暂不做像素 diff（LUT 预测会让每次渲染有微小抖动，diff 噪声大于信号）。


---

## 2. 采用决策

| 方向 | 决策 | 落点 |
|---|---|---|
| 原生设计 | 自研（吸收 HIG 与 Dimillian 的 ui-patterns 方法） | `spektra-ios-native-design` |
| SwiftUI 动画 | 自研（项目已有具体反模式需要点名） | `spektra-swiftui-animation` |
| SwiftUI 性能 | 自研（AttributeGraph 循环是本项目专属教训） | `spektra-swiftui-performance` |
| 图像管线 | 自研 | `spektra-image-pipeline` |
| 渲染调度 | 自研 | `spektra-render-scheduler` |
| 机型几何 | 自研 | `spektra-device-geometry` |
| 媒体导入导出 | 自研 | `spektra-media-export` |
| 构建验收 | 自研 | `spektra-build-verify` |
| 总控 | 自研 | `spektra-ios-engineering` |

**为什么全部自研而不直接安装外部 Skill：**

1. 外部 Skill 描述的是通用 SwiftUI，本项目的问题（`[Double]` 全尺寸缓冲、LUT 烘焙键、双层预览、开孔几何）都需要具体路径与常量。
2. 外部 Skill 的触发词是英文，与本项目中文工作流的匹配度低。
3. 直接安装会让 Agent 在「通用建议」与「本项目红线」之间摇摆；自研版本可以写死红线。

---

## 3. 许可证结论

| 仓库 | 许可证 | 可否商用 | 可否改写 |
|---|---|---|---|
| Dimillian/Skills | MIT | 是 | 是（保留版权声明） |
| CharlesWiltgen/Axiom | MIT | 是 | 是（保留版权声明）；但未复制 |
| 其余候选 | 未核查 | 未知 | 未知 |

本项目未复制任何第三方 Skill 的正文；如后续引入 MIT 内容，需在 Skill 目录内保留原始版权与许可证声明。

---

## 4. 后续可做的事

1. 核查 `dpearson2699/swift-ios-skills` 与 `curiositech/metal-shader-expert` 的许可证与内容，若质量高于自研版本可合并。
2. 关注 Apple 每年 WWDC 的 SwiftUI 图形 API（`layerEffect` / Metal 4），把 GPU 迁移方案写进 `spektra-image-pipeline`。
3. 每季度复核一次 Dimillian/Skills 与 Axiom 的更新，吸收新的 SwiftUI 反模式与验收工具链思路。
