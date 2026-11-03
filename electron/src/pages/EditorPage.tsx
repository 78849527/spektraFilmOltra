import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { errorMessage, mediaUrl, request, waitForJob } from '../api'
import { Button, IconButton, Tabs } from '../components/Controls'
import { ExportDialog } from '../components/ExportDialog'
import { Histogram } from '../components/Histogram'
import { Icon } from '../components/Icons'
import { ProPanel } from '../components/ProPanel'
import { QuickPanel } from '../components/QuickPanel'
import { Thumb } from '../components/Thumb'
import { formatSize, readPath, selectionOf, setString } from '../state'
import type {
  Bootstrap,
  ExportSettings,
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

function pickQuick(payload: QuickPayload): QuickPayload {
  return { intents: payload.intents, axes: payload.axes, disabled: payload.disabled }
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
  onGrade: (handoff: string) => void
  onSwitchItem: (item: ItemRecord) => void
  onNotify: (message: string, error?: boolean) => void
}) {
  const [state, setState] = useState<StateTree>(() => item.state ?? bootstrap.state)
  const [quick, setQuick] = useState<QuickPayload | null>(null)
  const [photo, setPhoto] = useState<OpenedPhoto | null>(null)
  const [preview, setPreview] = useState<PreviewState | null>(null)
  const [tab, setTab] = useState<'quick' | 'pro'>('quick')
  const [scale, setScale] = useState(0.5)
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState<ProgressState | null>(null)
  const [compare, setCompare] = useState(false)
  const [compareAt, setCompareAt] = useState(50)
  const [zoomMode, setZoomMode] = useState<'fit' | '1' | '2' | '4'>('fit')
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [favorite, setFavorite] = useState(item.favorite)
  const [exportOpen, setExportOpen] = useState(false)
  const [exporting, setExporting] = useState(false)

  const stateRef = useRef(state)
  const scaleRef = useRef(scale)
  const readyRef = useRef(false)
  const submittedKeyRef = useRef('')
  const renderSeqRef = useRef(0)
  const renderChainRef = useRef<Promise<void>>(Promise.resolve())
  const refineTimerRef = useRef<number | null>(null)
  const photoRef = useRef<OpenedPhoto | null>(null)
  const commitChainRef = useRef<Promise<void>>(Promise.resolve())
  const canvasRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null)
  const quickTimerRef = useRef<number | null>(null)

  stateRef.current = state
  scaleRef.current = scale
  photoRef.current = photo

  const selection = selectionOf(state)

  const scheduleRefineRef = useRef<() => void>(() => undefined)

  const submitPreview = useCallback(
    (scaleValue: number, refineAfter = false) => {
      renderChainRef.current = renderChainRef.current.then(async () => {
        const seq = ++renderSeqRef.current
        setBusy(true)
        setProgress(null)
        try {
          const { job_id } = await request<{ job_id: string }>('POST', '/v1/preview', {
            scale: scaleValue,
          })
          void (async () => {
            try {
              const job = await waitForJob(job_id, (status) => {
                if (seq === renderSeqRef.current) setProgress(status.progress)
              })
              if (seq !== renderSeqRef.current) return
              const result = job.result as unknown as { image_path: string; width: number; height: number }
              setPreview({ path: result.image_path, width: result.width, height: result.height })
              setProgress(null)
              if (refineAfter && scaleValue < scaleRef.current - 1e-6) {
                scheduleRefineRef.current()
              }
            } catch (error) {
              if (seq !== renderSeqRef.current) return
              const message = errorMessage(error)
              if (!message.includes('取消')) onNotify(message, true)
            } finally {
              if (seq === renderSeqRef.current) setBusy(false)
            }
          })()
        } catch (error) {
          if (seq === renderSeqRef.current) {
            setBusy(false)
            onNotify(errorMessage(error), true)
          }
        }
      })
      return renderChainRef.current
    },
    [onNotify],
  )

  const scheduleRefine = useCallback(() => {
    if (refineTimerRef.current) window.clearTimeout(refineTimerRef.current)
    refineTimerRef.current = window.setTimeout(() => {
      refineTimerRef.current = null
      void submitPreview(scaleRef.current)
    }, 1200)
  }, [submitPreview])

  scheduleRefineRef.current = scheduleRefine

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
        void submitPreview(scaleRef.current)
      } catch (error) {
        if (active) onNotify(errorMessage(error), true)
      }
    })()
    return () => {
      active = false
      if (refineTimerRef.current) window.clearTimeout(refineTimerRef.current)
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
            // 交互期先出 640px 的快图，快图完成且停手后再补全分辨率。
            const longEdge = photoRef.current
              ? Math.max(photoRef.current.width, photoRef.current.height)
              : 0
            const fastScale =
              longEdge > 0 ? Math.min(scaleRef.current, 640 / longEdge) : scaleRef.current
            void submitPreview(fastScale, true)
          }
        } catch (error) {
          onNotify(errorMessage(error), true)
        }
      }
      commitChainRef.current = commitChainRef.current.then(run, run)
      return commitChainRef.current
    },
    [onNotify, saveItem, scheduleRefine, submitPreview],
  )

  useEffect(() => {
    if (!readyRef.current) return
    const snapshot = state
    const timer = window.setTimeout(() => {
      void commitAndRender(snapshot)
    }, 320)
    return () => window.clearTimeout(timer)
  }, [state, commitAndRender])

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
    setOffset({ x: 0, y: 0 })
    if (refineTimerRef.current) window.clearTimeout(refineTimerRef.current)
    void submitPreview(next)
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
      if (refineTimerRef.current) window.clearTimeout(refineTimerRef.current)
      await commitChainRef.current
      await request('POST', '/v1/state', { state: stateRef.current })
      await saveItem(stateRef.current)
      const { job_id } = await request<{ job_id: string }>('POST', '/v1/handoff', {})
      const job = await waitForJob(job_id, (status) => setProgress(status.progress))
      setProgress(null)
      const result = job.result as unknown as { path: string }
      onGrade(result.path)
    } catch (error) {
      onNotify(errorMessage(error), true)
      setProgress(null)
    }
  }

  async function runExport(settings: ExportSettings) {
    setExportOpen(false)
    setExporting(true)
    try {
      if (refineTimerRef.current) window.clearTimeout(refineTimerRef.current)
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
      if (refineTimerRef.current) window.clearTimeout(refineTimerRef.current)
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
      if (refineTimerRef.current) window.clearTimeout(refineTimerRef.current)
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

  const mediaSrc = preview?.path ? `${mediaUrl(preview.path)}?v=${preview.path.slice(-12)}` : ''
  const originalSrc = photo ? `${mediaUrl(photo.original_preview)}?v=compare` : ''

  const aspect = photo ? photo.width / photo.height : 4 / 3
  const fitScale = useMemo(() => {
    const element = canvasRef.current
    if (!element || !preview) return 1
    const availableWidth = element.clientWidth - 90
    const availableHeight = element.clientHeight - 80
    return Math.max(0.05, Math.min(availableWidth / preview.width, availableHeight / preview.height))
  }, [preview, canvasRef.current])

  const effectiveScale =
    zoomMode === 'fit' ? fitScale : Number(zoomMode)
  const zoomed = effectiveScale > fitScale * 1.01

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.code === 'Space' && !event.repeat) {
        event.preventDefault()
        setZoomMode('fit')
        setOffset({ x: 0, y: 0 })
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="editor-page">
      <header className="editor-topbar">
        <Button icon="chevronLeft" kind="secondary" height={28} onClick={() => void leaveToLibrary()}>
          照片库
        </Button>

        <div className="editor-title grow">
          <span className="editor-title-main truncate">{item.name}</span>
          <span className="editor-title-sub truncate">
            {photo ? formatSize(photo.width, photo.height) : '—'} · {selection.film || '未选择胶片'} ·{' '}
            {selection.paper || '未选择相纸'}
          </span>
        </div>

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
          <div className="rail-scroll">
            {filmsByKind.map(([kind, entries]) => (
              <div key={kind}>
                <div className="rail-group-title">{kind}</div>
                {entries.map((film) => (
                  <button
                    key={film.id}
                    className={`preset-card${selection.film === film.id ? ' active' : ''}`}
                    onClick={() => selectProfile('film', film.id)}
                  >
                    <span
                      className="preset-swatch"
                      style={{
                        background: `linear-gradient(150deg, hsl(${filmIndexHue(film.id)} 30% 46% / 0.75), hsl(${filmIndexHue(film.id) + 26} 24% 26% / 0.9))`,
                      }}
                    />
                    <span className="stack grow" style={{ minWidth: 0 }}>
                      <span className="preset-name truncate">{film.display_name}</span>
                      <span className="preset-meta truncate">
                        {film.type === 'reversal' ? '正片' : film.kind === 'cinema' ? '电影' : '负片'} · {film.name}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            ))}

            <div className="rail-group-title" style={{ marginTop: 16 }}>
              相纸
            </div>
            {bootstrap.papers.map((paper) => (
              <button
                key={paper.id}
                className={`preset-card${selection.paper === paper.id ? ' active' : ''}`}
                onClick={() => selectProfile('paper', paper.id)}
              >
                <span
                  className="preset-swatch"
                  style={{
                    background: `linear-gradient(150deg, hsl(${filmIndexHue(paper.id)} 16% 64% / 0.7), hsl(${filmIndexHue(paper.id) + 20} 12% 38% / 0.9))`,
                  }}
                />
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
              if (!event.ctrlKey || !preview) return
              event.preventDefault()
              const current = effectiveScale
              const next = Math.max(0.1, Math.min(8, current * (event.deltaY < 0 ? 1.15 : 0.87)))
              const nearest = [1, 2, 4].find((value) => Math.abs(value - next) / value < 0.12)
              if (nearest) {
                setZoomMode(String(nearest) as '1' | '2' | '4')
              } else {
                setZoomMode('fit')
              }
              if (next > fitScale) setOffset({ x: 0, y: 0 })
            }}
            onPointerDown={(event) => {
              if (!zoomed || event.button !== 0) return
              dragRef.current = { x: event.clientX, y: event.clientY, ox: offset.x, oy: offset.y }
              event.currentTarget.setPointerCapture(event.pointerId)
            }}
            onPointerMove={(event) => {
              const drag = dragRef.current
              if (!drag) return
              setOffset({ x: drag.ox + event.clientX - drag.x, y: drag.oy + event.clientY - drag.y })
            }}
            onPointerUp={() => {
              dragRef.current = null
            }}
          >
            <div className="canvas-glow" />

            <div
              className="canvas-frame"
              style={{
                transform: `translate(${offset.x}px, ${offset.y}px)`,
                transition: dragRef.current ? 'none' : undefined,
              }}
            >
              <div className="canvas-mat" style={{ padding: Math.max(8, Math.min(22, 22 * fitScale)) }}>
                {preview ? (
                  <div style={{ position: 'relative', width: preview.width * effectiveScale, height: preview.height * effectiveScale }}>
                    <img
                      className="canvas-image"
                      style={{ width: '100%', height: '100%' }}
                      src={mediaSrc}
                      alt={item.name}
                      draggable={false}
                    />
                    {compare && originalSrc ? (
                      <img
                        className="canvas-image original"
                        style={{ width: '100%', height: '100%', clipPath: `inset(0 ${100 - compareAt}% 0 0)` }}
                        src={originalSrc}
                        alt="原片"
                        draggable={false}
                      />
                    ) : null}
                    {compare ? (
                      <>
                        <div
                          className="compare-handle"
                          style={{ left: `${compareAt}%` }}
                          onPointerDown={(event) => {
                            event.stopPropagation()
                            event.currentTarget.setPointerCapture(event.pointerId)
                          }}
                          onPointerMove={(event) => {
                            if (event.buttons !== 1) return
                            const host = canvasRef.current
                            if (!host) return
                            const rect = host.getBoundingClientRect()
                            const percent = ((event.clientX - rect.left) / rect.width) * 100
                            setCompareAt(Math.max(2, Math.min(98, percent)))
                          }}
                        />
                      </>
                    ) : null}
                  </div>
                ) : (
                  <div
                    style={{
                      width: Math.min(520, 520 * fitScale * 1.6),
                      aspectRatio: String(aspect),
                      background: 'var(--surface-2)',
                    }}
                  />
                )}
              </div>
            </div>

            <div className="canvas-label">照片</div>
            <div className="canvas-meta">
              {item.name}
              {preview ? ` · ${preview.width} × ${preview.height}` : ''} · {selection.film}
            </div>

            {progress ? (
              <div className="canvas-progress">
                <span>{progress.label}</span>
                <div className={`progress-track${progress.index === 0 ? ' indeterminate' : ''}`}>
                  <div
                    className="progress-fill"
                    style={{
                      width: progress.index === 0
                        ? '38%'
                        : `${progress.total ? (progress.index / progress.total) * 100 : 0}%`,
                    }}
                  />
                </div>
                <span className="num">
                  {progress.index === 0 ? '…' : `${progress.index}/${progress.total}`}
                </span>
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
              <button
                className="toolbar-text"
                onClick={() => {
                  if (refineTimerRef.current) window.clearTimeout(refineTimerRef.current)
                  void submitPreview(scale)
                }}
              >
                渲染
              </button>
              <span className="v-hairline" style={{ height: 14, alignSelf: 'center' }} />
              <IconButton
                name="expand"
                label="适应窗口"
                onClick={() => {
                  setZoomMode('fit')
                  setOffset({ x: 0, y: 0 })
                }}
              />
              <select
                className="select"
                style={{ height: 24, fontSize: 10.5 }}
                value={zoomMode}
                onChange={(event) => {
                  const value = event.target.value as typeof zoomMode
                  setZoomMode(value)
                  if (value === 'fit') setOffset({ x: 0, y: 0 })
                }}
              >
                <option value="fit">适应</option>
                <option value="1">100%</option>
                <option value="2">200%</option>
                <option value="4">400%</option>
              </select>
            </div>
          </div>

          <div className="filmstrip">
            {library.items.map((entry) => (
              <button
                key={entry.id}
                className={`film-thumb${entry.id === item.id ? ' active' : ''}`}
                onClick={() => void switchPhoto(entry)}
                title={entry.name}
              >
                <Thumb item={entry} />
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
          <div className="inspector-body">
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
              />
            ) : null}

            {tab === 'pro' ? (
              <ProPanel
                state={state}
                bootstrap={bootstrap}
                onPath={updatePath}
                onSelectProfile={selectProfile}
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
        <div className="toast">
          正在导出{progress ? ` · ${progress.label}` : '…'}
        </div>
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
