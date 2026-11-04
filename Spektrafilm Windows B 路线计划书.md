# Spektrafilm Windows 版（B 路线）计划书
## Electron 外壳 + 现有 Python 引擎

> 状态：仅计划，未开工。
> 分支：`electron`（从最新 Python 版 `skin` 的 `52f7dab` 拉出）。
> 本阶段只做 Windows；macOS 走 Swift 原生，两条线互不依赖。

---

## 0. 结论

- Windows 版 = Electron 前端 + 原封不动的 Python 计算引擎（子进程运行）。
- 算法零改造：`src/spektrafilm/` 一行不改，只新增一层服务包装。
- 第一个目标是"能看效果"的原型，不是完整功能。
- 最大的未知数不是界面，而是 **Windows 上那几个科学计算/图像库能不能装上**。所以开工第一步是依赖体检，不是搭外壳。

---

## 1. 当前基线

| 项目 | 事实 |
|---|---|
| 核心 `src/spektrafilm/` | 9,844 行，光谱胶片模拟运行时 |
| 界面 `src/spektrafilm_gui/` | 23,343 行，PySide6 + napari |
| LUT CLI | 11,522 行，本次不做 |
| 测试 | 729 个 test 函数（GUI 303 个） |
| 出厂数据 | 16 MB，28 个 profile，214 个文件 |
| 打包产物 | DMG 240 MB / app 537 MB（Qt + napari 为主） |
| 性能 | 6MP 约 10 秒（作者机）；12MP 全尺寸 50–90 秒（用户机）；预览长边上限 1920 |
| 依赖 | numpy / scipy / colour-science / scikit-image / numba / OpenImageIO / pyFFTW / rawpy / exiv2 / lensfunpy / PySide6 / napari |

关键接口（新服务层只调用，不改动）：

- `spektrafilm.runtime.process.Simulator.process(image, progress_callback=...)`
- `spektrafilm.runtime.params_builder.init_params(film_profile, print_profile)` / `digest_params(params)`
- `spektrafilm_gui.params_mapper.build_params_from_state(state)`（现有 GUI 状态 → 运行时参数）
- `spektrafilm.utils.io.load_image_oiio` / `save_image_oiio`
- `spektrafilm.utils.preview.resize_for_preview(image, max_size)`
- `spektrafilm_gui.grade_engine`：`load_handoff_image` / `prepare_source` / `render` / `parse_cube` / `apply_lut`
- `spektrafilm_gui.handoff`：`handoff_path` / `write_handoff` / `handoff_is_current`

---

## 2. 硬约束

1. **不改核心算法。** `src/spektrafilm/` 与 `src/spektrafilm_gui/grade_engine.py` 不改行为；只允许新增 `src/spektrafilm_service/`。
2. **不动用户资产。** 照片库、预设、导出文件、交接图都在用户数据目录，不进 Git。
3. **状态格式沿用现有 JSON。** 前端只发 GUI 状态 JSON，服务端用 `build_params_from_state` 还原，保证与 mac 版参数语义一致。
4. **GPLv3 合规。** 分发时必须附带完整对应源码。
5. **UI 实测由用户本人完成。** 助手只做代码修改、编译校验、打包，不启动浏览器或应用去点击验证。
6. **视觉沿用已验收的暖石墨 + 黄铜语言。** 不另起视觉体系，不改版式。

---

## 3. 目标架构

```
┌──────────────────────────────────────────────┐
│ Electron main (Node / TypeScript)            │
│  · 启动并守护 Python sidecar（随机端口+token）│
│  · 注册 spektra-media:// 只读缓存目录         │
│  · 窗口、菜单、文件对话框、退出保护            │
└───────────────▲──────────────────────────────┘
                │ 小 JSON（无像素）
┌───────────────┴──────────────────────────────┐
│ Renderer（React + TS，Canvas/WebGL2）         │
│  · 照片库 / 显影台 / 调色台                    │
└──────────────────────────────────────────────┘
                │ HTTP 127.0.0.1 + token
┌───────────────▼──────────────────────────────┐
│ Python sidecar（spektrafilm_service，新增）   │
│  · JobQueue：单 worker、排队、generation 取消  │
│  · /preview /export /handoff                  │
│  · /grade/*（复用 grade_engine）               │
│  · /library/*（复用 library_store）            │
│  · 直接 import 现有 spektrafilm / spektrafilm_gui │
└──────────────────────────────────────────────┘
```

为什么选 HTTP 而不是 stdin/stdout：

- Windows 下 stdout 编码、缓冲、行尾都有坑，日志和协议容易互串。
- HTTP 天然支持"提交任务 → 轮询进度"和并发请求。
- 只绑 `127.0.0.1`，每次启动生成随机 token，放在请求头，外部进程无法调用。

### 3.1 图像传输原则

**不传像素。** 所有渲染结果写成文件，接口只返回路径：

- 预览图：`%LOCALAPPDATA%\Spektrafilm\cache\preview\<photo>-<hash>.png`
- 全尺寸导出：直接写用户选定路径
- 调色交接图：现有 `handoff.tif`（16-bit / ProPhoto / 线性 / 内嵌 ICC）
- 前端通过自定义协议 `spektra-media://` 读取，该协议只映射到缓存目录，渲染进程拿不到任意路径读权限

这样避免了 12MP 图在 IPC 里做 base64 的内存与拷贝开销。

---

## 4. 服务契约（草案）

统一请求头：`X-Spektra-Token: <启动时随机生成>`。

| 方法 | 路径 | 用途 | 返回 |
|---|---|---|---|
| GET | `/v1/health` | 启动探活 | `{version, ready}` |
| POST | `/v1/photos/open` | 打开一张图（RAW/RGB），生成显示用源与元数据 | `{photo_id, size, format, exif}` |
| POST | `/v1/preview` | 按 GUI 状态渲染预览（长边 ≤1920） | `{job_id}` |
| POST | `/v1/export` | 全尺寸渲染并导出 | `{job_id}` |
| POST | `/v1/handoff` | 生成/复用 16-bit 交接图 | `{job_id, path, fingerprint}` |
| POST | `/v1/grade/preview` | 调色预览（复用 `grade_engine.render`） | `{job_id}` |
| POST | `/v1/grade/export` | 调色结果导出 | `{job_id}` |
| POST | `/v1/library/scan` | 递归扫描文件夹，建索引 | `{items}` |
| POST | `/v1/library/thumb` | 生成缩略图 | `{path}` |
| GET | `/v1/jobs/{id}` | 查询状态与进度 | 见下 |

作业状态：

```json
{
  "id": "j_1842",
  "state": "queued|running|done|failed|cancelled",
  "progress": {"label": "扫描", "index": 2, "total": 7},
  "result": {"image_path": "...", "width": 1920, "height": 1280,
             "elapsed_ms": 8200, "timings": {...}},
  "error": null
}
```

规则：

- **单 worker 串行**。同一时间只渲染一个任务，其余排队（与现在 Qt 版行为一致）。
- **导出排队**：渲染中提交导出，排进队列，当前任务结束后自动执行，不丢请求。
- **最新优先**：预览请求带 `generation`；新任务到来时，排队中的旧预览直接标记 `cancelled`，不浪费算力。
- **取消**：在 `progress_callback` 里抛 `JobCancelled`，异常沿管线向上抛出终止；不改核心代码。
- **预热**：sidecar 启动后台跑 `numba_warmup.warmup()` 与一次小图完整管线，减少首次渲染卡顿。
- **参数来源**：请求体 `state` 即现有 GuiState JSON；服务端 `build_params_from_state(state)` → `digest_params()`。

---

## 5. 前端设计

技术栈：Electron（最新稳定版）+ Vite + React + TypeScript；画布 Canvas2D/WebGL2；状态用轻量 store，不引入重型框架。

进程安全：`contextIsolation: true`、`nodeIntegration: false`，所有能力经 `preload.ts` 暴露的白名单 API。

页面与组件对照：

| Qt 现有 | Web 目标 |
|---|---|
| `LibraryPage` | 照片库网格 + 筛选胶囊 + 搜索/排序 |
| `EditorPage` | 顶栏 54 / 左 300 / 右 300 / 胶片条 96 |
| `PresetRail` | 预设卡 54，横向滚动 |
| `PreviewStage` | 画布：缩放平移带阻尼、100/200/400%、适应窗口、对比滑杆 |
| `ParameterDeck` | 参数行 44（快速 46），Tab 下划线段 |
| `GradePage` | 左 LUT 库 + 中预览 + 右「光影/色彩 Tab + 折叠区」 |
| `ExportDialog` | 格式/位深/压缩/长边/目录/文件名模板 |

视觉规格（与已验收皮肤一致）：

| 令牌 | 值 |
|---|---|
| 窗口 | 1460×940，最小 1180×760 |
| 背景阶 | `#141311 / #191713 / #1F1C18 / #26231D / #302C25`，画布 `#0E0D0B` |
| 文字 | `#F2EFE8 / #B6B0A4 / #8A8478 / #605B52` |
| 强调 | 黄铜 `#C5A373`（hover `#D8BB8C`，press `#9E7E55`） |
| 字号 | 标题 23 medium / 区块 13 semibold / 正文 12 / 读数 11.5 / 微字 9–10 |
| 圆角 | 卡片 10–12 / 控件 7 / 缩略图 8 |
| 动效 | hover 130ms / state 180ms / page 240ms |

唯一来源：以 `SpektraSkin/Sources/SpektraSkin/Design/Tokens.swift` 为准，生成 `tokens.css` 给 Web 使用；数值改动必须两边同步，加一个校验脚本比较两处数值。

Windows 差异：

- 无系统红绿灯，窗口自绘顶栏，右侧按钮左移让位。
- 字体回退：`Segoe UI` → `Microsoft YaHei UI`；等宽数字用 `Consolas` 回退。
- 高 DPI：125%/150% 缩放下必须验收。

---

## 6. Windows 依赖体检（M0，开工第一件事）

| 依赖 | 用途 | Windows 预期 | 不行时的备用方案 |
|---|---|---|---|
| numpy / scipy / numba / scikit-image / colour-science / matplotlib / opt-einsum | 数值核心 | 官方轮子，预期可用 | — |
| rawpy | RAW 解码（LibRaw，ACES 输出） | 有 Windows 轮子 | 自行编 LibRaw Python 绑定 |
| pyfftw | 扩散/光晕 FFT | 有 Windows 轮子 | 改走 numpy FFT（结果同精度、略慢，仅原型允许） |
| OpenImageIO | TIFF/EXR/PNG/JPEG + ICC | 不确定 | conda-forge 安装；或原型阶段用 Pillow + tifffile 替读写 |
| exiv2 | EXIF/IPTC/XMP | 不确定 | exiftool 子进程；元数据暂不写 |
| lensfunpy | 镜头校正 | 不确定 | 原型阶段跳过镜头校正 |
| PySide6 / napari | 旧界面 | 有轮子但本路线不用 | 不安装，减小环境 |

体检脚本（M0 唯一产物，只读调用现有 API）：

1. 逐个 `import` 上述包并打印版本；
2. 打开一张 12MP RAW，走完整管线做一次预览（1920）与一次全尺寸；
3. 记录：耗时、峰值内存、是否闪退、numba 编译耗时；
4. 输出一份 `windows_env_report.md`（不写进仓库的 `specs/`）。

判定：任意一项不可用，先确定替代方案再继续 M1；替代方案会影响像素一致性，需标注为"原型偏差"。

---

## 7. 里程碑

| 阶段 | 内容 | 完成标准 |
|---|---|---|
| M0 | Windows 依赖体检 | 12MP 图能完整跑完预览 + 全尺寸导出，报告有数字 |
| M1 | Python 服务层 | 本机可 `python -m spektrafilm_service`，`/health` 通，`/preview` 返回文件路径，单测通过 |
| M2 | Electron 外壳 | 窗口能打开、显示一张真实渲染图、进度条走完、取消生效、退出无僵尸进程 |
| M3 | 照片库 + 显影台 | 导入文件夹、缩略图网格、打开照片、改参数出图、胶片条切换、原片对比 |
| M4 | 调色台 + 导出 | LUT/预设可用、四模块参数可用、交接图生成、导出四格式三位深 |
| M5 | 打包分发 | PyInstaller 打 sidecar，electron-builder 打 NSIS 安装包，干净 Windows 机器安装即用 |

M2 是第一个"看效果"的节点；M0–M2 之前不碰界面细节。

---

## 8. 验收标准

- 功能以现有 Python Qt 版为唯一对照，不新增、不删减可见功能。
- 输出一致性：确定性参数下，同一配方导出的图与 Qt 版逐像素一致（颗粒/眩光按统计标准）。
- 性能：预览不慢于同机 Qt 版 1.5 倍；全尺寸导出不慢于 Qt 版（引擎相同，理应持平）。
- 稳定性：连续 20 次参数调整不崩；取消后无残留进程；连续导出 5 张不涨内存。
- 异常：非 RAW 文件不进 RAW 解码；损坏文件给友好弹窗，不崩进程。
- 分发：中文路径、长路径、125%/150% 缩放、无 Python 环境的机器均可用。

---

## 9. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| Windows 缺轮子（OIIO/exiv2/lensfun） | 阻塞 | M0 先验；conda-forge 兜底；原型期可局部降级，必须标注 |
| Python 子进程卡死/被杀 | 卡界面 | main 进程守护：心跳 + 超时重启 + 任务标记失败并告警 |
| 首次渲染慢（numba JIT） | 体验差 | 启动即后台预热；进度条给真实阶段 |
| 大图内存峰值 | 崩溃 | 预览 1920 封顶；全尺寸单任务；渲染完立即释放 |
| 前后端两套代码漂移 | 长期维护 | 先接受；里程碑后评估是否并到 C++ 统一引擎 |
| 杀软误报（未签名） | 无法安装 | 代码签名 + 安装说明；M5 处理 |
| 字体/DPI 差异 | 排版错乱 | 回退字体表 + 125%/150% 专项验收 |
| GPLv3 | 合规 | 源码随包，About 页放许可与来源 |

---

## 10. 目录规划

```
electron/                       # 新增
  package.json
  electron/main.ts              # 窗口、菜单、sidecar 守护
  electron/sidecar.ts           # 启动 Python、端口/token、健康检查
  electron/protocol.ts          # spektra-media:// 只读缓存
  electron/preload.ts           # 白名单 API
  src/                          # React 渲染层
    pages/Library.tsx
    pages/Editor.tsx
    pages/Grade.tsx
    canvas/
    styles/tokens.css           # 由 Tokens.swift 生成

src/spektrafilm_service/        # 新增，只 import 现有模块
  __main__.py                   # 启动 HTTP 服务
  server.py                     # 路由 + token 校验
  jobs.py                       # 队列、generation、取消
  handlers_develop.py           # preview / export / handoff
  handlers_grade.py             # 调色预览与导出
  handlers_library.py           # 扫描、缩略图
```

约束：`electron/` 与 `src/spektrafilm_service/` 之外不改任何源码。

---

## 11. 开工步骤（按顺序，未开始）

1. 在 Windows 机器建 Python 3.13 虚拟环境，逐包安装并记录结果（M0）。
2. 写体检脚本，跑 12MP 预览 + 全尺寸，把耗时/内存填进报告。
3. 根据报告确定替代方案，冻结 Windows 依赖版本清单。
4. 搭 `spektrafilm_service` 最小骨架：`/health` + `/preview` + 作业查询。
5. 搭 Electron 最小壳：启动 sidecar、显示一张真实预览、进度与取消。
6. 进入 M3 界面。

---

## 12. 明确不做

- 不做 macOS 版（Swift 线另行推进）。
- 不做 LUT Creator CLI。
- 不做多窗口、批量导出、插件系统。
- 不重写任何引擎算法，不改现有 JSON 状态结构。
- 不做自动更新；M5 只做安装包。
