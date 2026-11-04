import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { errorMessage, mediaUrl, request, waitForJob } from '../api'
import { Button, IconButton, Select, Tabs } from '../components/Controls'
import { ExportDialog } from '../components/ExportDialog'
import { Histogram } from '../components/Histogram'
import { FilmGlyph, Icon, PaperGlyph } from '../components/Icons'
import { BrandMark } from '../components/brands'
import { ProPanel } from '../components/ProPanel'
import { QuickPanel } from '../components/QuickPanel'
import { useElementSize, useSmoothScroll } from '../components/scroll'
import { Thumb } from '../components/Thumb'
import { formatBytes, formatSize, readPath, selectionOf, setString } from '../state'
import type {
  Bootstrap,
  ExportSettings,
  HandoffInfo,
  ItemRecord,
  LibrarySnapshot,
  OpenedPhoto,
  QuickPayload,
  StateTree,
} from '../types'
import './pages.css'

interface PreviewState {
  path: string
  width: number
  height: number
}

interface ProgressState {
  label: string
  index: number
  total: number
}

/* 渲染管线六步的英文节点名 → 中文 */
const STAGE_LABELS: Record<string, string> = {
  preprocess: '图像预处理',
  'filming.expose': '底片曝光',
  'filming.develop': '底片显影',
  'printing.expose': '相纸曝光',
  'printing.develop': '相纸显影',
  'scanning.scan_print': '相纸扫描',
  'scanning.scan_film': '反相扫描',
}

function stageLabel(label: string): string {
  return STAGE_LABELS[label] ?? label
}

function pickQuick(payload: QuickPayload): QuickPayload {
  return { intents: payload.intents, axes: payload.axes, disabled: payload.disabled }
}

function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value))
}

export function EditorPage({
  bootstrap,
  library,
  item,
  onBack,
  onGrade,
  onSwitchItem,
  onNotify,
}: {
  bootstrap: Bootstrap
  library: LibrarySnapshot
  item: ItemRecord
  onBack: () => void
  onGrade: (handoff: HandoffInfo) => void
  onSwitchItem: (item: ItemRecord) => void
  onNotify: (message: string, error?: boolean) => void
}) {
  const [state, setState] = useState<StateTree>(() => item.state ?? bootstrap.state)
  const [quick, setQuick] = useState<QuickPayload | null>(null)
  const [photo, setPhoto] = useState<OpenedPhoto | null>(null)
  const [preview, setPreview] = useState<PreviewState | null>(null)
  const [tab, setTab] = useState<'quick' | 'pro'>('quick')
  const [railTab, setRailTab] = useState<'film' | 'paper'>('film')
  const [scale, setScale] = useState(0.5)
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState<ProgressState | null>(null)
  const [compare, setCompare] = useState(false)
  const [compareAt, setCompareAt] = useState(50)
  const [zoom, setZoom] = useState(1)
  const [fitMode, setFitMode] = useState(true)
  const [borderOn, setBorderOn] = useState(true)
  const [favorite, setFavorite] = useState(item.favorite)
  const [exportOpen, setExportOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [hintId, setHintId] = useState(0)

  const stateRef = useRef(state)
  const scaleRef = useRef(scale)
  const readyRef = useRef(false)
  const submittedKeyRef = useRef('')
  const renderSeqRef = useRef(0)
  const commitChainRef = useRef<Promise<void>>(Promise.resolve())
  const canvasRef = useRef<HTMLDivElement>(null)
  const frameRef = useRef<HTMLDivElement>(null)
  const matRef = useRef<HTMLDivElement>(null)
  const zoomRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null)
  const quickTimerRef = useRef<number | null>(null)
  const hintTimerRef = useRef<number | null>(null)
  const rafRef = useRef(0)
  const initializedRef = useRef(false)
  const previewDimsRef = useRef({ width: 0, height: 0 })
  const viewRef = useRef({ scale: 1, x: 0, y: 0 })
  const targetRef = useRef({ scale: 1, x: 0, y: 0 })
  const chromeRef = useRef({ borderOn: true, whitePadding: 0.03 })

  const railRef = useSmoothScroll<HTMLDivElement>('y')
  const inspectorRef = useSmoothScroll<HTMLDivElement>('y')
  const filmstripRef = useSmoothScroll<HTMLDivElement>('x')

  stateRef.current = state
  scaleRef.current = scale

  const selection = selectionOf(state)
  const canvasSize = useElementSize(canvasRef)

  const rawPadding = readPath(state, 'display.white_padding')
  const whitePadding = typeof rawPadding === 'number' && Number.isFinite(rawPadding) ? rawPadding : 0.03
  chromeRef.current = { borderOn, whitePadding }

  const startRender = useCallback(
    async (scaleValue: number) => {
      const seq = ++renderSeqRef.current
      setBusy(true)
      setProgress(null)
      try {
        const { job_id } = await request<{ job_id: string }>('POST', '/v1/preview', { scale: scaleValue })
        const job = await waitForJob(job_id, (status) => {
          if (seq === renderSeqRef.current) setProgress(status.progress)
        })
        if (seq !== renderSeqRef.current) return
        const result = job.result as unknown as { image_path: string; width: number; height: number }
        setPreview({ path: result.image_path, width: result.width, height: result.height })
        setProgress(null)
      } catch (error) {
        if (seq !== renderSeqRef.current) return
        const message = errorMessage(error)
        if (!message.includes('取消')) onNotify(message, true)
      } finally {
        if (seq === renderSeqRef.current) setBusy(false)
      }
    },
    [onNotify],
  )

  useEffect(() => {
    let active = true
    readyRef.current = false
    ;(async () => {
      try {
        const initial = item.state ?? bootstrap.state
        await request('POST', '/v1/state', { state: initial })
        const opened = await request<OpenedPhoto>('POST', '/v1/photos/open', {
          path: item.path,
          item_id: item.id,
        })
        if (!active) return
        setPhoto(opened)
        setState(opened.state)
        setQuick(pickQuick(await request<QuickPayload>('GET', '/v1/quick')))
        readyRef.current = true
        submittedKeyRef.current = JSON.stringify(opened.state)
        await startRender(scaleRef.current)
      } catch (error) {
        if (active) onNotify(errorMessage(error), true)
      }
    })()
    return () => {
      active = false
    }
  }, [item.id, item.path])

  const saveItem = useCallback(
    async (snapshot: StateTree) => {
      const current = selectionOf(snapshot)
      try {
        await request('POST', '/v1/library/state', {
          id: item.id,
          state: snapshot,
          film_stock: current.film,
          print_paper: current.paper,
        })
      } catch {
        // 单张状态保存失败不打断编辑
      }
    },
    [item.id],
  )

  const commitAndRender = useCallback(
    (snapshot: StateTree) => {
      const run = async () => {
        try {
          const key = JSON.stringify(snapshot)
          const response = await request<{ state: StateTree } & QuickPayload>('POST', '/v1/state', {
            state: snapshot,
          })
          setQuick(pickQuick(response))
          await saveItem(response.state)
          if (JSON.stringify(response.state) !== key) {
            // 换胶片/相纸后后端会重捕基线，等新状态回流再渲染，避免重复出图。
            setState(response.state)
            return
          }
          const autoPreview = Boolean(readPath(response.state, 'simulation.auto_preview'))
          if (autoPreview && key !== submittedKeyRef.current) {
            submittedKeyRef.current = key
            void startRender(scaleRef.current)
          }
        } catch (error) {
          onNotify(errorMessage(error), true)
        }
      }
      commitChainRef.current = commitChainRef.current.then(run, run)
      return commitChainRef.current
    },
    [onNotify, saveItem, startRender],
  )
  useEffect(() => {
    if (!readyRef.current) return
    const snapshot = state
    const timer = window.setTimeout(() => {
      void commitAndRender(snapshot)
    }, 320)
    return () => window.clearTimeout(timer)
  }, [state, commitAndRender])

  /* ── 缩放/平移：阻尼插值，逐帧直接写 DOM ── */

  const applyView = useCallback(() => {
    const view = viewRef.current
    const dims = previewDimsRef.current
    const element = zoomRef.current
    if (!dims.width || !element) return
    element.style.width = `${Math.round(dims.width * view.scale)}px`
    element.style.height = `${Math.round(dims.height * view.scale)}px`
    if (matRef.current) {
      const chrome = chromeRef.current
      const padding = chrome.borderOn
        ? Math.round(Math.max(dims.width, dims.height) * chrome.whitePadding * view.scale)
        : 0
      matRef.current.style.padding = `${padding}px`
    }
    if (frameRef.current) {
      frameRef.current.style.transform = `translate3d(${view.x}px, ${view.y}px, 0)`
    }
  }, [])

  const startAnim = useCallback(() => {
    if (rafRef.current) return
    const step = () => {
      const view = viewRef.current
      const target = targetRef.current
      const damping = 0.16
      view.scale += (target.scale - view.scale) * damping
      view.x += (target.x - view.x) * damping
      view.y += (target.y - view.y) * damping
      if (
        Math.abs(target.scale - view.scale) < 0.0004 &&
        Math.abs(target.x - view.x) < 0.4 &&
        Math.abs(target.y - view.y) < 0.4
      ) {
        view.scale = target.scale
        view.x = target.x
        view.y = target.y
        applyView()
        rafRef.current = 0
        return
      }
      applyView()
      rafRef.current = window.requestAnimationFrame(step)
    }
    rafRef.current = window.requestAnimationFrame(step)
  }, [applyView])

  useEffect(() => {
    return () => {
      if (rafRef.current) window.cancelAnimationFrame(rafRef.current)
      if (hintTimerRef.current) window.clearTimeout(hintTimerRef.current)
    }
  }, [])

  const fitScale = useMemo(() => {
    if (!preview || canvasSize.width === 0) return 1
    const availableWidth = canvasSize.width - 96
    const availableHeight = canvasSize.height - 84
    return Math.max(
      0.04,
      Math.min(availableWidth / preview.width, availableHeight / preview.height),
    )
  }, [preview, canvasSize])

  useEffect(() => {
    if (!preview) return
    previewDimsRef.current = { width: preview.width, height: preview.height }
    if (!initializedRef.current) {
      initializedRef.current = true
      viewRef.current = { scale: fitScale, x: 0, y: 0 }
      targetRef.current = { scale: fitScale, x: 0, y: 0 }
      setZoom(fitScale)
    } else if (fitMode) {
      targetRef.current = { scale: fitScale, x: 0, y: 0 }
      setZoom(fitScale)
      startAnim()
    }
    applyView()
  }, [preview, fitScale, fitMode, applyView, startAnim])

  useEffect(() => {
    applyView()
  }, [borderOn, whitePadding, applyView])

  const showHint = useCallback(() => {
    setHintId((current) => current + 1)
    if (hintTimerRef.current) window.clearTimeout(hintTimerRef.current)
    hintTimerRef.current = window.setTimeout(() => setHintId(0), 3000)
  }, [])

  const resetView = useCallback(() => {
    targetRef.current = { scale: fitScale, x: 0, y: 0 }
    setFitMode(true)
    setZoom(fitScale)
    startAnim()
  }, [fitScale, startAnim])

  const zoomTo = useCallback(
    (nextScale: number) => {
      targetRef.current = { scale: nextScale, x: 0, y: 0 }
      setZoom(nextScale)
      startAnim()
    },
    [startAnim],
  )

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'SELECT' || target.isContentEditable)) {
        return
      }
      if (event.code === 'Space' && !event.repeat) {
        event.preventDefault()
        resetView()
        setHintId(0)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [resetView])

  function updatePath(path: string, value: unknown) {
    setState((current) => {
      const next = JSON.parse(JSON.stringify(current)) as StateTree
      const parts = path.split('.')
      let node = next as Record<string, unknown>
      for (const part of parts.slice(0, -1)) {
        const child = node[part]
        if (typeof child !== 'object' || child === null) node[part] = {}
        node = node[part] as Record<string, unknown>
      }
      node[parts[parts.length - 1]] = value
      return next
    })
  }

  function selectProfile(kind: 'film' | 'paper', id: string) {
    const path = kind === 'film' ? 'simulation.film_stock' : 'simulation.print_paper'
    setState((current) => setString(current, path, id))
  }

  function changeScale(next: number) {
    setScale(next)
    void startRender(next)
  }

  function quickLocal(axis: string, value: number) {
    setQuick((current) =>
      current ? { ...current, intents: { ...current.intents, [axis]: value } } : current,
    )
    if (quickTimerRef.current) window.clearTimeout(quickTimerRef.current)
    quickTimerRef.current = window.setTimeout(() => quickCommit(axis, value), 260)
  }

  async function quickCommit(axis: string, value: number) {
    if (quickTimerRef.current) {
      window.clearTimeout(quickTimerRef.current)
      quickTimerRef.current = null
    }
    try {
      const response = await request<{ state: StateTree } & QuickPayload>('POST', '/v1/quick/axis', {
        axis,
        value,
      })
      setState(response.state)
      setQuick(pickQuick(response))
    } catch (error) {
      onNotify(errorMessage(error), true)
    }
  }

  async function resetAll() {
    try {
      const response = await request<{ state: StateTree } & QuickPayload>('POST', '/v1/reset', {})
      setState(response.state)
      setQuick(pickQuick(response))
      onNotify('已重置为默认参数')
    } catch (error) {
      onNotify(errorMessage(error), true)
    }
  }

  async function toggleFavorite() {
    const next = !favorite
    setFavorite(next)
    try {
      await request('POST', '/v1/library/mark', { id: item.id, favorite: next })
    } catch (error) {
      onNotify(errorMessage(error), true)
    }
  }

  async function openGrade() {
    try {
      await commitChainRef.current
      await request('POST', '/v1/state', { state: stateRef.current })
      await saveItem(stateRef.current)
      const { job_id } = await request<{ job_id: string }>('POST', '/v1/handoff', {})
      const job = await waitForJob(job_id, (status) => setProgress(status.progress))
      setProgress(null)
      const result = job.result as unknown as HandoffInfo
      onGrade(result)
    } catch (error) {
      onNotify(errorMessage(error), true)
      setProgress(null)
    }
  }

  async function runExport(settings: ExportSettings) {
    setExportOpen(false)
    setExporting(true)
    try {
      await commitChainRef.current
      await request('POST', '/v1/state', { state: stateRef.current })
      const { job_id } = await request<{ job_id: string }>('POST', '/v1/export', { settings })
      const job = await waitForJob(job_id, (status) => setProgress(status.progress))
      setProgress(null)
      const result = job.result as unknown as { path: string }
      onNotify(`已导出到 ${result.path}`)
    } catch (error) {
      onNotify(errorMessage(error), true)
      setProgress(null)
    } finally {
      setExporting(false)
    }
  }

  async function switchPhoto(next: ItemRecord) {
    try {
      await commitChainRef.current
      await request('POST', '/v1/state', { state: stateRef.current })
      await saveItem(stateRef.current)
    } catch {
      // 忽略保存失败，继续切换
    }
    onSwitchItem(next)
  }

  async function leaveToLibrary() {
    try {
      await commitChainRef.current
      await request('POST', '/v1/state', { state: stateRef.current })
      await saveItem(stateRef.current)
    } catch {
      // 保存失败也要能回到照片库
    }
    onBack()
  }

  const filmsByKind = useMemo(() => {
    const groups = new Map<string, typeof bootstrap.films>()
    for (const film of bootstrap.films) {
      const key = film.kind === 'reversal' ? '正片' : film.kind === 'cinema' ? '电影卷' : '负片'
      const list = groups.get(key) ?? []
      list.push(film)
      groups.set(key, list)
    }
    return Array.from(groups.entries())
  }, [bootstrap.films])

  const mediaSrc = preview ? `${mediaUrl(preview.path)}?v=${preview.path.slice(-12)}` : ''
  const originalSrc = photo ? `${mediaUrl(photo.original_preview)}?v=compare` : ''

  const zoomOptions = useMemo(() => {
    const options = [
      { value: 'fit', label: '适应' },
      { value: '1', label: '100%' },
      { value: '2', label: '200%' },
      { value: '4', label: '400%' },
    ]
    if (!fitMode) {
      options.unshift({ value: 'free', label: `${Math.round(zoom * 100)}%` })
    }
    return options
  }, [fitMode, zoom])

  const exif = photo?.exif
  const cameraLabel = exif?.model || exif?.make || '未知机身'
  const lensLabel = exif?.lens || '未知镜头'
  const megapixels = Math.round((item.width * item.height) / 1e6)
  const params = exif
    ? [
        exif.iso ? `ISO ${exif.iso}` : '',
        exif.focal_length ? `${exif.focal_length} mm` : '',
        exif.aperture ? `ƒ${exif.aperture}` : '',
        exif.exposure ? `${exif.exposure} s` : '',
      ].filter(Boolean)
    : []

  return (
    <div className="editor-page">
      <header className="editor-topbar">
        <Button icon="chevronLeft" kind="secondary" height={28} onClick={() => void leaveToLibrary()}>
          照片库
        </Button>

        <span className="grow" />

        <IconButton
          name={favorite ? 'starFill' : 'star'}
          label="收藏这张照片"
          active={favorite}
          onClick={() => void toggleFavorite()}
        />

        <div className="split-button">
          <button className="split-main" onClick={() => void openGrade()} disabled={busy || exporting}>
            <Icon name="sliders" size={12} />
            调色
          </button>
          <button className="split-caret" onClick={() => setExportOpen(true)} title="导出设置">
            <Icon name="chevronDown" size={11} />
          </button>
        </div>
      </header>

      <div className="editor-body">
        <aside className="editor-rail">
          <div className="rail-info">
            <div className="photo-meta">
              <div className="photo-meta-head">
                <span className="photo-brand">
                  <BrandMark make={exif?.make} model={exif?.model} size={40} />
                </span>
                <span className="photo-meta-titles">
                  <span className="photo-meta-name truncate" title={item.name}>
                    {item.name}
                  </span>
                  <span className="photo-meta-sub truncate" title={cameraLabel}>
                    {cameraLabel}
                  </span>
                </span>
              </div>
              <div className="photo-meta-block">
                <div className="photo-meta-lens truncate" title={lensLabel}>
                  {lensLabel}
                </div>
                <div className="photo-meta-line">
                  {megapixels} MP<span className="dot">•</span>
                  {formatSize(item.width, item.height)}<span className="dot">•</span>
                  {formatBytes(item.file_size)}<span className="dot">•</span>
                  {photo ? photo.color_space : '—'}
                </div>
              </div>
              {params.length > 0 ? (
                <div className="photo-meta-params">
                  {params.map((value, index) => (
                    <span key={index}>{value}</span>
                  ))}
                </div>
              ) : null}
            </div>
          </div>

          <div className="rail-tabs">
            <Tabs
              tabs={[
                { value: 'film', label: '胶片' },
                { value: 'paper', label: '相纸' },
              ]}
              value={railTab}
              onChange={setRailTab}
            />
          </div>

          <div className="rail-scroll" ref={railRef}>
            {railTab === 'film'
              ? filmsByKind.map(([kind, entries]) => (
                  <div key={kind}>
                    <div className="rail-group-title">{kind}</div>
                    {entries.map((film) => (
                      <button
                        key={film.id}
                        className={`preset-card${selection.film === film.id ? ' active' : ''}`}
                        onClick={() => selectProfile('film', film.id)}
                        title={`${film.display_name} · ${film.name}`}
                      >
                        <span className="preset-glyph">
                          <FilmGlyph size={26} tint={`hsl(${filmIndexHue(film.id)} 46% 62%)`} />
                        </span>
                        <span className="stack grow" style={{ minWidth: 0 }}>
                          <span className="preset-name truncate">{film.display_name}</span>
                          <span className="preset-meta truncate">
                            {film.type === 'reversal' ? '正片' : film.kind === 'cinema' ? '电影' : '负片'} · {film.name}
                          </span>
                        </span>
                      </button>
                    ))}
                  </div>
                ))
              : bootstrap.papers.map((paper) => (
                  <button
                    key={paper.id}
                    className={`preset-card${selection.paper === paper.id ? ' active' : ''}`}
                    onClick={() => selectProfile('paper', paper.id)}
                    title={paper.display_name}
                  >
                    <span className="preset-glyph">
                      <PaperGlyph size={26} tint={`hsl(${filmIndexHue(paper.id)} 14% 70%)`} />
                    </span>
                    <span className="stack grow" style={{ minWidth: 0 }}>
                      <span className="preset-name truncate">{paper.display_name}</span>
                      <span className="preset-meta truncate">{paper.name}</span>
                    </span>
                  </button>
                ))}
          </div>
        </aside>

        <section className="editor-center">
          <div
            className="canvas-area"
            ref={canvasRef}
            onWheel={(event) => {
              if (!preview) return
              if (event.ctrlKey) event.preventDefault()
              const factor = Math.exp(-event.deltaY * 0.0018)
              const next = clamp(targetRef.current.scale * factor, Math.max(0.05, fitScale * 0.4), 8)
              targetRef.current = { ...targetRef.current, scale: next }
              setFitMode(false)
              setZoom(next)
              showHint()
              startAnim()
            }}
            onPointerDown={(event) => {
              if (event.button !== 0 || compare) return
              if (targetRef.current.scale <= fitScale * 1.01) return
              dragRef.current = {
                x: event.clientX,
                y: event.clientY,
                ox: targetRef.current.x,
                oy: targetRef.current.y,
              }
              event.currentTarget.setPointerCapture(event.pointerId)
            }}
            onPointerMove={(event) => {
              const drag = dragRef.current
              if (!drag) return
              targetRef.current = {
                ...targetRef.current,
                x: drag.ox + event.clientX - drag.x,
                y: drag.oy + event.clientY - drag.y,
              }
              startAnim()
            }}
            onPointerUp={() => {
              dragRef.current = null
            }}
          >
            <div className="canvas-glow" />

            <div className="canvas-frame" ref={frameRef}>
              <div className={`canvas-mat${borderOn && whitePadding > 0 ? '' : ' plain'}`} ref={matRef}>
                {preview ? (
                  <div className="canvas-zoom" ref={zoomRef}>
                    <img className="canvas-image" src={mediaSrc} alt={item.name} draggable={false} />
                    {compare && originalSrc ? (
                      <img
                        className="canvas-image original"
                        style={{ clipPath: `inset(0 ${100 - compareAt}% 0 0)` }}
                        src={originalSrc}
                        alt="原片"
                        draggable={false}
                      />
                    ) : null}
                    {compare ? (
                      <div
                        className="compare-layer"
                        onPointerDown={(event) => {
                          event.stopPropagation()
                          event.currentTarget.setPointerCapture(event.pointerId)
                          const box = zoomRef.current
                          if (!box) return
                          const rect = box.getBoundingClientRect()
                          setCompareAt(clamp(((event.clientX - rect.left) / rect.width) * 100, 0, 100))
                        }}
                        onPointerMove={(event) => {
                          if (event.buttons !== 1) return
                          const box = zoomRef.current
                          if (!box) return
                          const rect = box.getBoundingClientRect()
                          setCompareAt(clamp(((event.clientX - rect.left) / rect.width) * 100, 0, 100))
                        }}
                      >
                        <div className="compare-line" style={{ left: `${compareAt}%` }} />
                        <div className="compare-knob" style={{ left: `${compareAt}%` }} />
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div
                    style={{
                      width: Math.min(520, 520 * fitScale * 1.6),
                      aspectRatio: String(photo ? photo.width / photo.height : 4 / 3),
                      background: 'var(--surface-1)',
                    }}
                  />
                )}
              </div>
            </div>
            {progress ? (
              <div className="canvas-progress">
                <span>{stageLabel(progress.label)}</span>
                <div className="progress-track">
                  <div
                    className="progress-fill"
                    style={{ width: `${progress.total ? (progress.index / progress.total) * 100 : 0}%` }}
                  />
                </div>
                <span className="num">
                  {progress.index}/{progress.total}
                </span>
              </div>
            ) : null}

            {hintId > 0 ? (
              <div className="space-hint" key={hintId}>
                按空格复位
              </div>
            ) : null}

            <div className="canvas-toolbar">
              <button className="toolbar-text" onClick={() => changeScale(scale === 0.5 ? 1.0 : 0.5)}>
                {scale === 0.5 ? '1/2' : '1/1'}
                <Icon name="chevronDown" size={9} />
              </button>
              <span className="v-hairline" style={{ height: 14, alignSelf: 'center' }} />
              <button className={`toolbar-text${compare ? ' active' : ''}`} onClick={() => setCompare(!compare)}>
                <Icon name="compare" size={12} />
                对比
              </button>
              <button className="toolbar-text" onClick={() => void startRender(scale)}>
                渲染
              </button>
              <span className="v-hairline" style={{ height: 14, alignSelf: 'center' }} />
              <IconButton name="expand" label="适应窗口" onClick={resetView} />
              <Select
                borderless
                value={fitMode ? 'fit' : 'free'}
                options={zoomOptions}
                onChange={(value) => {
                  if (value === 'fit') {
                    resetView()
                    return
                  }
                  if (value === 'free') return
                  zoomTo(Number(value))
                }}
              />
            </div>
          </div>

          <div className="filmstrip" ref={filmstripRef}>
            {library.items.map((entry) => (
              <button
                key={entry.id}
                className={`film-thumb${entry.id === item.id ? ' active' : ''}`}
                onClick={() => void switchPhoto(entry)}
                title={entry.name}
              >
                <Thumb item={entry} className="film-thumb-media" />
                <span className="film-thumb-name">{entry.name}</span>
              </button>
            ))}
          </div>
        </section>

        <aside className="editor-inspector">
          <div className="inspector-head">
            <span className="meta">{photo?.is_raw ? 'RAW' : 'RGB'}</span>
            <Button kind="quiet" onClick={() => void resetAll()}>
              重置
            </Button>
          </div>
          <div className="inspector-tabs">
            <Tabs
              tabs={[
                { value: 'quick', label: '快速' },
                { value: 'pro', label: '专业' },
              ]}
              value={tab}
              onChange={setTab}
            />
          </div>
          <div className="inspector-body" ref={inspectorRef}>

            <Histogram src={mediaSrc} />
            {photo ? (
              <div className="analysis-line">
                <span className="truncate">
                  {photo.color_space}
                  {photo.cctf_decoding ? ' · CCTF' : ' · 线性'}
                </span>
                <span className="truncate">{photo.lens_summary || (photo.is_raw ? 'RAW 解码' : 'RGB 输入')}</span>
              </div>
            ) : null}

            {tab === 'quick' && quick ? (
              <QuickPanel
                layout={bootstrap.quick_layout}
                intents={quick.intents}
                disabled={quick.disabled}
                onChange={quickLocal}
                onCommit={(axis, value) => void quickCommit(axis, value)}
                borderOn={borderOn}
                onBorderChange={setBorderOn}
              />
            ) : null}

            {tab === 'pro' ? (
              <ProPanel
                state={state}
                bootstrap={bootstrap}
                onPath={updatePath}
                onSelectProfile={selectProfile}
                borderOn={borderOn}
                onBorderChange={setBorderOn}
              />
            ) : null}
          </div>
        </aside>
      </div>

      {exportOpen ? (
        <ExportDialog
          initial={bootstrap.export_settings}
          onClose={() => setExportOpen(false)}
          onConfirm={(settings) => void runExport(settings)}
        />
      ) : null}

      {exporting ? (
        <div className="toast">正在导出{progress ? ` · ${stageLabel(progress.label)}` : '…'}</div>
      ) : null}
    </div>
  )
}

function filmIndexHue(id: string): number {
  let hash = 0
  for (let index = 0; index < id.length; index += 1) {
    hash = (hash * 31 + id.charCodeAt(index)) % 360
  }
  return hash
}
