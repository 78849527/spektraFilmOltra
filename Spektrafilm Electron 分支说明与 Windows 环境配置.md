# Spektrafilm Electron 分支说明与 Windows 环境配置

> 分支：`electron`　远端：`oltra`（Ote65/spektraFilmOltra）
> 基线：Python 支最新提交 `7f43f06`（film frame presets and grade preview parity）
> 本文同时说明「相对 Python 支改了什么」和「Windows 上怎么最快跑起来」。

---

## 1. 一句话

算法一行没改。Electron 只负责界面，Python 引擎以本地子进程运行；两者之间只传状态 JSON 和文件路径，不传像素。

---

## 2. 分支与关键提交

| 提交 | 内容 |
|---|---|
| `ad44100` | 服务层 + Electron 外壳 + 三页前端首版 |
| `6936264` | 导航前强制保存状态、相对路径打包修正 |
| `a7b3d82` | 媒体协议 CORS、直方图可读像素、Electron 国内镜像 |
| `a7bfcd0` | 修复预览全白（0–255 误当 0–1 写 PNG） |
| `dcf006f` | 调参时中断在跑的显影，只保留最后一组参数 |

---

## 3. 目录结构

```
src/spektrafilm/                原引擎，算法未改
  runtime/topology.py           新增可选取消钩子（默认关闭）
  runtime/pipeline.py           把取消钩子透传下去
  runtime/process.py            Simulator.process 新增 cancel_callback

src/spektrafilm_gui/            Qt 界面保留作对照，服务层不 import Qt
  display_pixels.py             新增：从 controller_runtime 抽出的纯像素处理
  controller_runtime.py         只剩 Qt 线程包装，并兼容重导出纯函数
  library_store.py              删除未使用的 Qt 导入
  persistence.py                QSettings 改为函数内懒加载

src/spektrafilm_service/        新增：Electron 用的本地服务层
  __main__.py                   启动入口，向 stdout 打印 ready 行
  server.py                     127.0.0.1 HTTP + 令牌鉴权 + 路由
  jobs.py                       单工作线程队列、取代、取消
  session.py                    照片会话、状态、模拟器缓存、预览/导出/交接
  develop.py                    载入、缩放、显示编码、导出写盘
  catalog.py                    胶片/相纸/快速轴/选项/默认状态
  library_api.py                图库扫描、缩略图、收藏、单张状态
  grade_api.py                  调色预览/导出/预设/LUT
  thumbs.py                     Qt-free 缩略图生成
  paths.py                      渲染缓存目录

electron/                      新增：Electron + React 前端
  electron/main.ts              窗口、菜单、IPC、媒体协议、引擎守护
  electron/sidecar.ts           启动 Python、解析 ready、退出清理
  electron/preload.ts           白名单 API
  src/pages/                    照片库 / 显影台 / 调色台
  src/components/               控件、直方图、参数面板、导出弹窗
  启动 Electron 应用.command    macOS 双击启动

tests/service/                 新增：队列、目录、预览导出往返、令牌鉴权
```

---

## 4. 相对 Python 支改了什么

| 文件 | 改动 | 是否影响结果 |
|---|---|---|
| `runtime/topology.py` | 新增 `PipelineCancelled` 与可选 `cancel` 参数，在节点之间检查 | 否，默认关闭 |
| `runtime/pipeline.py` | `process()` 透传 `cancel_callback` | 否 |
| `runtime/process.py` | `Simulator.process()` 透传 `cancel_callback` | 否 |
| `src/spektrafilm_gui/display_pixels.py` | 新增，从 `controller_runtime` 原样搬出的显示函数 | 否 |
| `controller_runtime.py` | 删除重复实现，改为重导出；保留 Qt 线程包装 | 否 |
| `library_store.py` | 删除未使用的 `qtpy` 导入 | 否 |
| `persistence.py` | 删除未使用的 Qt 常量，QSettings 改为懒加载 | 否 |
| `pyproject.toml` | 包发现列表加入 `spektrafilm_service` | 否 |
| `tests/gui/test_controller_output.py` | 显示器 ICC 的 patch 目标改为 `display_pixels` | 否 |
| `.gitignore` | 忽略 `electron/node_modules|dist|dist-electron` | 否 |

没有改动：`spektrafilm/model/*`（密度曲线、颗粒、光晕、扩散、眩光）、`spektrafilm/utils/*` 算法内核、`data/profiles` 与光谱 LUT。

---

## 5. 架构与接口

```
Renderer (React/TS)
   │  IPC（小 JSON，无像素）
Electron main
   │  HTTP 127.0.0.1 + X-Spektra-Token
Python sidecar (spektrafilm_service)
   │  import 现有引擎
SimulationPipeline → PNG / TIFF
```

图像一律落盘再回路径：预览 PNG 在 `~/Library/Application Support/Spektrafilm/render_cache/preview/`，交接图在 `library/projects/<item_id>/handoff.tif`。

作业规则：

- 单 worker，同一时间只渲染一个任务。
- 预览请求会取消排队中的旧预览，并中断正在运行的旧预览（在管线节点边界）。
- 导出与交接图排队执行，不丢请求。
- 前端状态提交串行，出图请求不阻塞下一次提交。

主要接口：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/v1/bootstrap` | 胶片/相纸、快速轴、选项、默认状态、导出设置 |
| POST | `/v1/photos/open` | 打开 RAW/RGB，返回尺寸、色彩空间、原图预览 |
| POST | `/v1/state` | 应用 GUI 状态 |
| POST | `/v1/quick/axis` | 快速模式单轴 |
| POST | `/v1/preview` | 提交预览渲染 |
| POST | `/v1/export` | 全尺寸导出 |
| POST | `/v1/handoff` | 生成 16-bit ProPhoto 线性交接图 |
| GET | `/v1/library` | 图库快照 |
| POST | `/v1/library/scan|photos|thumb|mark|state` | 导入、缩略图、标记、单张状态 |
| GET/POST | `/v1/grade/*` | 调色预览、导出、预设、LUT |
| GET | `/v1/jobs/{id}` | 作业状态与进度 |

---

## 6. macOS 运行

双击 `electron/启动 Electron 应用.command`，首次会自动安装前端依赖并构建。

热更新开发：

```bash
cd electron
npm install          # 首次
npm run dev          # Vite + Electron
```

首次安装 Electron 若卡住，脚本已使用国内镜像：

```bash
ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/ npm install
```

---

## 7. Windows 环境（最快路径）

### 7.1 前置

- Windows 10/11 x64
- Python 3.13（<https://www.python.org/downloads/windows/>，安装时勾选 Add to PATH）
- Node.js 22 LTS（<https://nodejs.org/>）
- Git for Windows

不需要 Visual Studio，也不需要 conda：所有关键依赖都有 Python 3.13 的 Windows 官方轮子（已核实）：

| 依赖 | Windows cp313 轮子 |
|---|---|
| OpenImageIO 3.1.19 | 有 |
| exiv2 0.18.1 | 有 |
| lensfunpy 1.18.0 | 有 |
| pyfftw 0.15.1 | 有 |
| rawpy 0.26.1 | 有 |
| numba / numpy / scipy / scikit-image / Pillow | 有 |

### 7.2 安装 Python 依赖

在仓库根目录（`Spektrafilm`）打开 PowerShell：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
```

只装引擎与服务层需要的包（不装 PySide6/napari，省几百 MB）：

```powershell
.\.venv\Scripts\pip install "numpy~=2.4" "scipy~=1.17" "colour-science~=0.4.6" `
  "scikit-image~=0.26" "matplotlib~=3.10" "opt-einsum~=3.4.0" "numba~=0.64" `
  "OpenImageIO~=3.1.11" "pyfftw~=0.15.0" "rawpy~=0.26.1" "exiv2~=0.18.1" `
  "lensfunpy~=1.18.0" "Pillow~=12.1"
```

把本仓库以可编辑模式装进环境（不重复拉依赖）：

```powershell
.\.venv\Scripts\pip install -e . --no-deps
```

验证引擎能启动：

```powershell
.\.venv\Scripts\python -m spektrafilm_service --port 0
```

看到一行 `{"event": "ready", "port": ...}` 即成功，按 Ctrl+C 退出。

### 7.3 安装前端并启动

```powershell
cd electron
$env:ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"
npm install
npm run build
npx electron .
```

引擎路径会自动解析：优先 `SPEKTRA_PYTHON` 环境变量，其次 `.venv\Scripts\python.exe`，最后 PATH 里的 `python`。

如果 Python 环境在别处：

```powershell
$env:SPEKTRA_PYTHON="C:\path\to\python.exe"
npx electron .
```

### 7.4 Windows 下的已知差异

- 窗口暂时使用系统标题栏；自绘顶栏与红绿灯按钮只适用于 macOS，Windows 自绘按钮尚未实现。
- 没有 macOS 的显示器 ICC 匹配逻辑，预览直接输出 sRGB，由 Chromium 做显示色彩管理。
- 打包未做：目前从仓库运行。后续用 PyInstaller 打 sidecar + electron-builder 打 NSIS。
- 首次渲染会做 numba JIT 预热，前几十秒偏慢，之后正常。
- 中文路径与长路径已用 `pathlib` 处理；若遇到 MAX_PATH 限制，启用 Windows 长路径策略。

### 7.5 常见问题

| 现象 | 处理 |
|---|---|
| 启动提示“引擎启动失败” | 在仓库根目录手动跑 7.2 的验证命令，看缺哪个包 |
| Electron 下载卡住 | 重新执行 `npm install`，确认 `ELECTRON_MIRROR` 已设置 |
| 打开 RAW 崩溃/报错 | 确认文件后缀在 RAW 列表内；非 RAW 文件不要走 RAW 解码 |
| 预览很慢 | 正常；先看是否已预热，再看是否在跑全尺寸 |
| 导出找不到目录 | 检查导出目录是否存在或改用原文件目录 |

---

## 8. 已知差距（诚实清单）

- 旋转按钮、Polaroid 显影动画、边框预设（film_frame）未接。
- 调色台 HSL 8 色带、颜色分级四分区面板未做。
- 调色预设导入/重命名未接；保存、删除可用。
- 调色配方未写入图库单张状态（交接图已按片保存）。
- 「专业」参数台是精选分组，不是 877 行参数清单的逐项全量。
- Windows 自绘窗口按钮、安装包未做。

---

## 9. 验收清单

- [ ] `python -m spektrafilm_service` 能打印 ready 行
- [ ] 打开一张 RAW，预览正常（不是全白/死黑）
- [ ] 连续快速改 5 次参数，只看到最后一组参数的显影
- [ ] 预览中按“调色”，能生成交接图并进入调色台
- [ ] 调色台改参数能实时预览，导出文件正常
- [ ] 返回照片库后单张状态保留
- [ ] 退出应用后没有残留 Python 进程

---

## 10. 维护约定

- 引擎算法保持在 `src/spektrafilm/`，服务层只调用，不改写。
- 用户资产（照片库、预设、导出）不进 Git。
- `electron/` 与 `src/spektrafilm_service/` 之外的改动必须说明理由。
- 前端视觉基准：`SpektraSkin/Sources/SpektraSkin/Design/Tokens.swift`。
