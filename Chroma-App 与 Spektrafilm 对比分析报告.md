# Chromasmith（Chroma-App）源码评估报告

**评估对象**：`https://github.com/TareqAmeer/Chroma-App`（产品名 **Chromasmith**），HEAD `c04e90c`（2026-11-02）
**对照对象**：本机 Spektrafilm 项目（Python 光谱模拟内核 + Qt/napari 界面 + Electron 壳）
**评估时间**：2026-11-03

---

## 0. 一句话结论

**不是"我们 Spektrafilm 的更完整版本"，而是"把 Spektrafilm 的物理模型离线烘成 20 个 LUT 后，套进一个 Lightroom 式消费级修图 App"的另一种产品。**
两者的关系是 **渲染内核 / 成品应用**，不是版本迭代关系。它在**产品完整度、性能、工程化**上确实远超我们；在**物理正确性与参数自由度**上则明确、主动地放弃了——源码里写得很清楚，不是能力不足的猜测。

---

## 1. 它到底是什么

| 项目 | 事实 |
|---|---|
| 定位 | Gallery. Studio. Film Lab —— 本地图库 + 修图 + 胶片 look 三合一 |
| 卖点 | 133 个胶片 look、真实颗粒/光晕/辉光、RAW 解码、蒙版修图、全分辨率导出、全平台、离线、免账号 |
| 平台 | 网页（单 HTML，无构建步骤）/ macOS+Windows（Tauri 2 + Rust）/ iOS+Android（Capacitor 壳） |
| 许可证 | GPL-3.0（与 spektrafilm 同族，但 LUT 部分另行声明 CC BY-SA 4.0） |
| 代码体量 | `src/` 296 个文件、**80,966 行**（其中 Web 编辑器 `src/app` 36,990 行）；主程序是**一个 17.7MB 的 `chromasmith-22.html`**；Rust 桌面内核 `desktop/src-tauri/src` 54 个文件 4.2MB |
| 技术栈 | WebGL2 + GLSL 着色器（全部渲染）、LibRaw→WASM（RAW）、Tauri2+Rust+SQLite（图库/脸/CLIP）、ONNX（EdgeSAM 主体分割、SegFormer 人脸解析、Depth-Anything V2）、mediabunny（视频） |
| 工程化 | `test/` 下有 300+ 个 Playwright/Node 闸门（golden 图导出门禁、UI 审计、perf 预算、蒙版往返、编辑器线框覆盖），CI 徽章 3 个 |

---

## 2. 关键证据：它和 Spektrafilm 到底是什么关系

这不是"参考了思路"，而是**直接把 spektrafilm 当成素材生产器**在调用，而且把边界划得非常明确：

1. **20 个内置 look 就是 spektrafilm 烘出来的 LUT**
   [LICENSES-MODELS.md](file:///Users/megmeet/Documents/开发%20APP/Spektrafilm/Chroma-App/LICENSES-MODELS.md#L35-L59) 写明：用 spektrafilm 官方 `spektrafilm-lut` CLI，按 `--input srgb --output srgb --resolution 33 --topology 1lut`，为 **20 个胶片（16 负片 + 4 反转片）** 各烘一个 33³ `.cube`，按 profile 里自带的 `target_print` 配相纸（Endura Premier / Crystal Archive / 2383），再量化成 8-bit `.bin` 落在 `vendor/luts/spektra_*.bin`。归属声明是 CC BY-SA 4.0 的"修改版"规范文本。
2. **16 个负片还有"真实高光肩部"表**
   同一文件 R4 附录：直接跑 spektrafilm 的 `SimulationPipeline`，在 -1 ~ +4.5 档合成曝光下采样，做成 256×1 每通道 uint8 表 `spektra_*_shoulder.bin`，用来在着色器里替代普通 LUT 的硬裁剪（见 [cont-gpupreference.js.html](file:///Users/megmeet/Documents/开发%20APP/Spektrafilm/Chroma-App/src/app/20-script/editor/cont-gpupreference.js.html#L144-L156)）。
3. **但它明确声明：不做实时光谱模型**
   `docs/ROADMAP.md` 的 R4 条目原话："**tier a's real roll-off, NOT the live spectral model**"；反转片的耦合剂串扰、halation、grain 模型 **explicitly out of scope**。原因很实在：浏览器每秒要出帧，光谱链路跑不动。
4. **其余 look 的来源也很明确**
   [CLAUDE.md](file:///Users/megmeet/Documents/开发%20APP/Spektrafilm/Chroma-App/CLAUDE.md#L54-L68)：`tools/calib/LUT LIBRARY/`（46 个）**+ `dehancer/cubes/`（67 个）= 全部预设来源**。即 133 = 46 + 67 + 20（spektrafilm）。`README` 里说的 133 个 look，其中 113 个与 spektrafilm 无关。
5. **光晕/辉光/颗粒是"照着 Dehancer 出图拟合"的经验模型，不是物理模型**
   [calibrated-halation-bloom-constants-meas.js.html](file:///Users/megmeet/Documents/开发%20APP/Spektrafilm/Chroma-App/src/app/20-script/renderer/calibrated-halation-bloom-constants-meas.js.html#L1-L13) 开头就说明：常量由 `tools/calib/optimize_hal.py`（Nelder-Mead）直接对 `dehancer halation x2.png` 做像素级拟合得到，最终 loss 0.0239；通道 sigma 是 σ_R=7.52 ≫ σ_G=2.97 ≫ σ_B=1.13（2400px 参考宽）。颗粒同理：8/16/35/65mm 只是换 clump cell 尺寸与强度系数，也是对着 Dehancer 的格式观感调的（同文件 L79-L83）。

> **判断**：Chromasmith 是 spektrafilm 的**下游消费者（LUT 烘焙目标）**，不是它的超集。它把 spektrafilm 压缩成"20 个固定预设 + 一条高光曲线"。

---

## 3. 渲染架构对比

| 维度 | Chromasmith (Chroma-App) | 我们的 Spektrafilm |
|---|---|---|
| 核心模型 | 33³ LUT（一次性全局色彩/色调映射）+ 经验 shader 特效 | 真光谱链路：感光层光谱灵敏度 → 密度曲线 → 耦合剂 → 印相/相纸 → 扫描 |
| 胶片可调性 | 选预设（20 个来自 spektrafilm，113 个来自 LUT 库/Dehancer），push 只有预烘的 push1/push2 | 28 个 datasheet profile，曝光/显影/推拉/相纸/放大机二向色滤色全可调 |
| 颗粒 | 程序化噪声，格式档位（8/16/35/65mm）+ 强度 | 负片上的随机颗粒生成模型（物理生成，随密度变化） |
| 光晕 | 通道分离高斯 + 规则化发光模型（拟合 Dehancer） | 由负片/片基光学扩散在链路内产生 |
| 高光 | LUT 白点硬裁 + BT.2390/AgX 肩部；16 个 spektra 用真肩部表 | 密度曲线饱和本身即"肩部"，物理自洽 |
| 计算位置 | GPU 实时（WebGL2），全分辨率分块导出 | CPU NumPy/Numba 光谱积分，预览要降采样，全分辨率导出慢（README 自述） |
| 性能量级 | 交互实时；5k 图库索引数秒级（有专门 perf 闸门） | 单图整链模拟，秒~分钟级 |
| 输出物 | JPEG/PNG/WebP/TIFF/HEIC gain-map + XMP + `.cube` | TIFF/EXR/PNG + `.cube`/`.3dl`/Hald CLUT + OCIO config |
| LUT 生成 | 运行时"从 before/after 截图回烘"（33³ 往返误差 1/510） | 官方 `spektrafilm-lut`：多色域、V-Log/PQ/HLG shaper、多 LUT 串联 |

---

## 4. 功能矩阵（谁有谁没有）

**Chromasmith 有、我们没有（或弱）：**

- **图库级工作流**：文件夹/日期/相册、星级+色彩标签、剔除（culling）、去重（pHash）、人脸识别命名、自然语言检索（CLIP）、关键词层级、虚拟副本、离线编辑队列、SD 卡导入+校验双备份、Lightroom 往返/云浏览
- **修图工具箱**：径向/线性/画笔/天空/AI 主体/颜色范围/亮度范围/深度蒙版、蒙版边缘细化、皮肤色调分离（含五官排除）、heal/clone、去污点
- **几何与输出**：裁剪比例、旋转翻转、水平仪、透视校正、边框/相纸留白、拼贴、HDR 合成、焦点堆叠、双图接片、全分辨率分块导出、导出预设、相机内 LUT（Lumix Lab 标签）
- **视频**：片段调色、裁切、音频直通、示波器、安全框、淡入淡出、片门晃动/曝光呼吸
- **跨端与分发**：网页即开即用、离线 service worker、手机触屏布局、家庭屏安装、APK/IPA
- **工程资产**：golden 图回归、UI/可达性/性能闸门、CI 出包

**我们有、Chromasmith 没有（且它明确放弃）：**

- 真实光谱计算：光谱灵敏度曲线、染料吸收谱、掩膜耦合剂、DIR 耦合剂扩散、二向色放大机、相纸/显影化学
- **参数自由度**：任意胶片×相纸组合、推拉档位、滤色片、光晕/颗粒的物理参数——它的 133 个 look 全是"定死的成品"
- 研究/验证工具链：曲线数字化、数据表绘图、revision 对比、仿真 QA
- 生产级 LUT 交付：OCIO config、多色域、log/HDR shaper、多 LUT 串联（我们 `spektrafilm_lut_creator` 已有）
- 中文界面与本地化（它有 i18n 工具但默认英文）、胶片边框的相纸质感（我们有 `film_frame.py` 程序化 6 种）

---

## 5. 两边"特点"定性

**Chromasmith 强在"产品"：**
导入→图库→选片→修图→look→颗粒光晕→边框→导出→分享，全链路闭环，四个平台一个内核，免费离线。它把"胶片感"拆成 6 个可独立调节的滑杆（look / light / colour / texture / output / info），普通用户 3 步出片。工程纪律罕见：shader 改动必须过 golden 导出闸门，UI 改动必须过线框/响应式/可达性审计。

**Spektrafilm 强在"模型"：**
它是可解释、可外推的物理仿真——能回答"Portra 800 push2 配 Endura 会怎样"，也能造出数据表里没有的组合。这份能力正是 Chromasmith 主动砍掉的那块（ROADMAP 原文 "NOT the live spectral model"）。

**所以：不是"更完整"，是"更产品化 + 更窄"。**

---

## 6. 可以直接借鉴的 5 件事（对我们落地最有用）

1. **两级近似交付**：先烘 33³ sRGB LUT 做实时预览，再对被裁掉的高光补一张 256×1 每通道肩部表——这正是我们 `spektrafilm_lut_creator` 能直接产出的东西，且成本极低（每片 768B）。我们的"预览慢"问题可以照此解决，而不必上 GPU 光谱。
2. **单文件离线分发**：17.7MB 一个 HTML 就能跑完整编辑器（LUT 放 `vendor/` 按需 fetch），无构建、无后端。对我们 Electron 壳是很好的降级方案（Web 版先行，桌面壳只加图库与原生能力）。
3. **测试闸门形态**：`export_harness` 把"每张 fixture × 每个 recipe"渲染成图与 golden 比对，shader/管线改动一律过闸门；`perf_bench` 有 7 条预算。我们现有 84 个测试偏数值单测，可补像素级 golden（我们已有 `tests/baselines/`，可扩成"每 profile × 每相纸"的快照矩阵）。
4. **全分辨率分块导出**：按 tile 渲染 + 缓存，RAM 有界，导出不再等整图。我们导出慢的根因是整图光谱积分，可先对"高分辨率成品"走 LUT + 分块。
5. **参数化才是我们的护城河**：它把 spektrafilm 降级成 20 个固定预设，我们只要把"推拉/相纸/耦合剂/放大机滤色"做成滑杆，就是它做不到的差异点。

---

## 7. 风险与许可（重要）

- **好的示范**：它对 spektrafilm 的归属做得非常规范（CC BY-SA 4.0 修改版声明、逐条 stock/print 对照表、CLI 只"运行"不 vendor 代码）。我们可以照抄这套合规写法。
- **它的灰色地带**：67 个预设来自 `dehancer/cubes/`，光晕/辉光/颗粒参数是对 Dehancer（**商业闭源付费产品**）出图做像素级拟合。这些派生 LUT 与拟合常量随 GPL 仓库公开分发，存在授权风险。**我们不应直接搬运它的 LUT 或常量表**，只用方法。
- **商标**：预设用 Kodak/Fuji/Agfa 商品名命名（如 `kodak_portra_400`），商用产品里这样列名有商标风险，建议我们保持"基于公开数据表"的表述并避免暗示官方授权。

---

## 8. 建议

1. **不要按它的架构重构 Spektrafilm**。它的取舍（放弃光谱、拥抱 LUT+拟合）是为"实时消费级"服务的，会直接抹掉我们唯一的护城河。
2. **采用它的分层**：内核（Python 光谱，保持现状）→ 烘焙层（我们已有的 `spektrafilm-lut`，加 shoulder 表）→ 前端（现有 Electron/React 调色台 + 图库）→ 分发（Web 单文件 / Tauri / 移动壳）。
3. **优先级建议**：先做 ①RGB→LUT+肩部表的实时预览通路；②分块全分辨率导出；③像素级 golden 回归；④图库/剔除/蒙版按需借鉴（这是它最重的工程量，也是我们最缺的消费级功能）。
4. **定位话术**：对外不要说"我们的胶片模拟更全"，而说"参数可调的物理胶片模拟"——这是 Chromasmith 结构上做不到的事。

---

## 附：评估方法与克隆状态

- 完整 `git clone` 因仓库约 1.5GB（含约 1GB 图片/素材）在弱网下连续 3 次中断（`early EOF` / `HTTP/2 CANCEL`）。
- 改用 `git clone --depth 1 --filter=blob:none --sparse` + 稀疏检出 `src/`、`desktop/src-tauri/src`，本地 38MB，代码完整可读（`Chroma-App/`）。
- 另单独抓取并阅读了 `README.md`、`CLAUDE.md`、`LICENSES-MODELS.md`、`docs/ROADMAP.md`、`docs/lut-workflows.md`、`tools/calib/README.md`、`tools/calib/ANALYSIS.md`。
- 未检出：`docs/`（314MB，多为图）、`site/`、`vendor/`（素材与 LUT 二进制）、`test/` 全量。结论均基于可复核的源码与文档原文，关键处已在正文给出文件与行号。
