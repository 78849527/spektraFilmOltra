# 实施任务清单（spec.md 对应）

> 顺序即依赖顺序。每项完成需 `./build.sh` 通过；G1/G4/G6 需附对拍证据。

## T1 DIR couplers（G1）
- [x] 新建 `Model/Couplers.swift`：`computeMatrix` / `curvesBeforeCouplers` / `exposureCorrection` / `applyDensityCorrection`
- [x] `FilmingStage.develop` 串入 couplers（`developSimple` → couplers → grain 占位）
- [x] 新增 numpy `interp` 语义工具（异号/非单调 x 段），复用 `Interpolation`
- 验收：grain off、couplers on，`cmy_film` 4×4 与 32×24 对拍 ≤1e-9；`active=false` 与基线逐位一致

## T2 随机统计与颗粒（G2）
- [x] `Utils/RandomStats.swift`：SplitMix64 + poisson/binomial/lognormal（`.toNearestOrEven`）
- [x] `Model/Grain.swift`：`layerParticleModel` / `interpDensityCMYLayers` / `applyToDensity` / `applyToDensityLayers` / `addMicroStructure` / `apply`
- [x] `FilmingStage.develop` 接入 grain；尊重 `debug.deactivateStochasticEffects`
- 验收：`active=false` 与 T1 输出逐位一致；`active=true` 时 256×256 灰度块 5 档密度统计：均值偏差 ≤2%，RMS 与 Python 同量级；子层/非子层两条路径均跑到

## T3 眩光（G3）
- [x] `Model/Glare.swift` 的 `addGlare`
- [x] `ScanningStage.addGlare` 调用；`scanFilm` 传 nil
- 验收：`percent=0` 恒等；`percent=0.03/roughness=0.7/blur=0.5` 时 XYZ 增量均值 ≈ percent/100×illuminant（±3%），空间相关长度与 blur 一致

## T4 柔光镜（G4）
- [x] `Model/DiffusionFilter.swift`：家族表、`strengthToScatter`、`expandGroup`、`haloChannelWeights`、`resolveFamilyCfg`、`psf`
- [x] `Utils/FFTConvolution.swift`：vDSP 实数 FFT、same 裁剪、reflect pad
- [x] `SpatialEffects.diffusionFilter` 实现；四家族 × strength 0.25/1/2 × warmth 0/1 覆盖
- 验收：单位脉冲响应与 Python `diffusion_filter_psf` 中心/边缘 ≤1e-9（用 `psf` 直出比对）；全链路 `active=false` 与 T3 基线一致；`black_pro_mist, 0.5` 图像对拍 ≤1e-9（无随机项）

## T5 印相像素尺寸（G5）
- [x] `PrintingStage.pixelSizeUM` + `Pipeline.preprocess` 写入
- 验收：`enlarger.diffusion.active=true` 时 `log_e_print` 与 Python 对拍 ≤1e-9；关闭时基线不变

## T6 输出色域压缩（G6）
- [x] `Color/CAM16UCS.swift`：CAM16 forward/inverse + UCS 变换
- [x] `Model/OutputGamutCompression.swift`：`reinhardKnee`、`cMaxLookup`、表构建与缓存、`aces_rgc`、`cam16ucs`（oklch/oklrab 已实现，jzazbz 暂缺）
- [x] `ScanningStage.compressRGB` 接线
- 验收：`algorithm=off` 与 T5 基线逐位一致；`cam16ucs` 在 sRGB 输出的 `rgb_out` 对拍 ≤1e-9（4×4、32×24 各一组，含超白与高饱和像素）；表构建耗时 <3 s

## T7 对拍与回归
- [x] `Tools/PipelineSmoke` 增加 JSON 导出/导入
- [x] `Tools/parity/dump_reference.py`（跑 Python 参考管线，输出同结构 JSON）
- [x] 备份「G1-G6 全关」基线 JSON，回归 6 个 tap
- [x] 汇总对拍报告（写入 `docs/parity_report.md`，仅数据表）

## 完成后
- [x] 更新 `docs/PORTING_PLAN.md` 的「已完成/剩余」段落
- [x] 向用户汇报：哪些模块与 Python 逐位一致、哪些为统计等价、剩余缺口（UI 接线、RAW、导出）

## 第三阶段（用户追加：jzazbz / RAW / 导出）
- [x] `Color/JzAzBz.swift`：Safdar 2017 正逆变换 + ST2084 PQ
- [x] `OutputGamutCompression` 补齐 `jzazbz` 表与逐像素路径
- [x] `Services/ImageExport.swift`：TIFF（8/16/32-bit + ICC + EXIF）、EXR（half/float）、PNG/JPEG（8-bit + ICC）
- [x] `Services/RawDecoder.swift`：CIRAWFilter 解码 + EXIF 读取（原生 macOS 路径）
- 验收：jzazbz 正逆 0 / 3.6e-15；jzazbz 压缩 2.3e-13；oklch 2.6e-15、oklrab 1.6e-15、aces_rgc 0；
  导出像素 8/16/32-bit TIFF 与 half/float EXR 全部精确；PNG/JPEG 8-bit（JPEG 有损 ±2 LSB）；ICC 已嵌入

## 第四阶段（引擎收尾）
- [x] 自动曝光 7 种方法对拍（原始尺寸与 256 预览路径）
- [x] `Resize.smallPreview` 对齐 skimage `rescale(order=0)` 坐标/边界规则
- [x] TIFF Deflate（系统 zlib via `dlopen`，Compression=8）
- [x] 导出支持复制源 EXIF/IPTC（PNG/JPEG）
- [x] `upscale_factor != 1` 走双三次 Catmull-Rom 并同步像素尺寸
- 验收：autoexposure ≤1.4e-14；TIFF compression=8 且像素不变；放大尺寸一致（像素值近似，偏差 ≤2.5e-2）

## 第五阶段（性能与健壮性）
- [x] 颗粒二项分布对称采样（消除 p≈1 时的 O(n) 退化）
- [x] vDSP Double FFT（dlopen）+ 转置列变换 + 三通道并发
- [x] 光谱上采样：光源 xy 与 RGB→XYZ 矩阵提出循环
- [x] `PreviewRenderer`：串行队列、代际取消、共享 LUT、降采样、`keepTaps`
- [x] `SimulationPipeline` 协作式取消与共享 `SpectralLUTService`
- 验收：640×480 全效果 193 s → 2.06 s；预览 184 s → 1.66 s；全管线基线仍 ≤5e-13

## 第六阶段（库与导出队列）
- [x] `Services/ImageLoader.swift`：RAW / EXR / 编码图识别与解码
- [x] `Services/LibraryStore.swift`：原图拷贝、索引持久化、缩略图、PhotoEdit（Codable）
- [x] `Services/ExportQueue.swift`：串行全尺寸渲染、进度、取消、保存
- 验收：示例 JPEG 识别为 Adobe RGB；库重载后编辑可恢复；导出 500×343 uint16 Deflate TIFF + ICC

## 第七阶段（SpektraSkin 引擎接入）
- [x] `SpektraSkin/Engine/EngineHost.swift`：库快照、编辑器快照、快速/专业动作、预览渲染、导入、导出
- [x] 九个快速控制按计划书映射 + 基线锚定 + 色盘；快速意图与基线持久化（`quickBaselineData`）
- [x] `PreviewStage` 注入真实预览与缩略图；`FilmThumbnail` / 库网格 / 列表全部改用引擎缩略图
- [x] 库内缺失缩略图后台补渲染（`warmThumbnails`，串行队列，320px）
- [x] 直方图改为从预览输出计算（56 桶 RGB，桶峰值归一）；调色台注入当前预览
- [x] 顶部与空态的「导入照片/文件夹」接到 `NSOpenPanel`；文件夹递归只收 RAW
- 验收：`HostSmoke` 预览 3.5 s、快速/专业写回生效、缩略图生成、导出 16-bit TIFF 成功

## 第八阶段（RAW 闪退与交互修复）
- [x] 修复 RAW 极端像素导致 `OutputGamutCompression.cMaxLookup` 的 NaN/Inf 索引陷阱
- [x] 扫描输出与 RAW 解码统一 `sanitizedNonFinite()`；预览/导出/8·16-bit 写盘再兜底
- [x] 显影台改为只接受 RAW：库导入、文件夹导入、旧索引过滤；删除 JPEG/样图与 JPEG 导出
- [x] 预览不再强制 `preview_mode=True`：颗粒、锐化、柔光、halation 按实际参数渲染
- [x] 预览降采样改用 `Resize.smallPreview`（与 Python GUI 同一重采样规则）
- [x] 窗口拖动只保留顶部状态栏 `WindowDragArea`，`isMovableByWindowBackground = false`
- [x] 预览支持滚轮/触控板缩放、拖拽平移、双击复位、旋转与适应窗口
- [x] 预览工具栏：渲染比例（1/8–1/1）、对比原图、重新渲染、显示倍率全部可交互
- [x] 导出菜单（sRGB TIFF 16/8、ProPhoto 线性 TIFF 16、ACES 线性 EXR half）+ `NSSavePanel`
- [x] 库搜索/筛选/排序、收藏、颜色标签、移除照片；编辑器收藏写回
- 验收：`HostSmoke` 载入 12 MP DNG 预览 3.5 s、导出 TIFF 71 MB，无闪退；NaN/Inf 色域压缩回归通过



