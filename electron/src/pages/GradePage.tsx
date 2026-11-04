import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { errorMessage, mediaUrl, pickLut, request, waitForJob } from '../api'
import { Button, Disclosure, FieldRow, SwitchRow, Tabs, ValueRow } from '../components/Controls'
import { ExportDialog } from '../components/ExportDialog'
import { CurveEditor, DEFAULT_CURVE_POINTS, type CurvePoint } from '../components/CurveEditor'
import { Histogram } from '../components/Histogram'
import { Icon } from '../components/Icons'
import { useElementSize, useSmoothScroll } from '../components/scroll'
import { BrandMark } from '../components/brands'
import { formatBytes, formatSize } from '../state'
import type { Bootstrap, ExportSettings, HandoffInfo, ItemRecord, OpenedPhoto, PresetEntry, Recipe } from '../types'
import './pages.css'

const PROXY_EDGE = 800
const FULL_EDGE = 1600

interface GradePreview {
  path: string
  width: number
  height: number
  analysis: {
    black_point: number
    white_point: number
    highlight_cast: string
    shadow_cast: string
    summary: string
  }
}

interface LutEntry {
  name: string
  path: string
}

type BorderStyle = 'black' | 'white'

const BORDER_COLORS: Record<BorderStyle, string> = {
  black: '#000000',
  white: '#f6f3ec',
}

const BORDER_LABELS: Record<BorderStyle, string> = {
  black: '黑框',
  white: '白框',
}

function read(root: unknown, path: string): number {
  let node: unknown = root
  for (const part of path.split('.')) {
    if (typeof node !== 'object' || node === null) return 0
    node = (node as Record<string, unknown>)[part]
  }
  return typeof node === 'number' ? node : 0
}

function write<T extends object>(root: T, path: string, value: unknown): T {
  const next = JSON.parse(JSON.stringify(root)) as Record<string, unknown>
  const parts = path.split('.')
  let node = next
  for (const part of parts.slice(0, -1)) {
    const child = node[part]
    if (typeof child !== 'object' || child === null) node[part] = {}
    node = node[part] as Record<string, unknown>
  }
  node[parts[parts.length - 1]] = value
  return next as T
}


export function GradePage({
  bootstrap,
  item,
  handoff,
  photo,
  onBack,
  onNotify,
}: {
  bootstrap: Bootstrap
  item: ItemRecord
  handoff: HandoffInfo
  photo: OpenedPhoto | null
  onBack: () => void
  onNotify: (message: string, error?: boolean) => void
}) {
  const [recipe, setRecipe] = useState<Recipe>(() => bootstrap.grade_recipe ?? ({} as Recipe))
  const [tab, setTab] = useState<'light' | 'color'>('light')
  const [preview, setPreview] = useState<GradePreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [presets, setPresets] = useState<PresetEntry[]>([])
  const [activePreset, setActivePreset] = useState('')
  const [luts, setLuts] = useState<LutEntry[]>([])
  const [railTab, setRailTab] = useState<'lut' | 'preset' | 'border'>('lut')
  const [saveOpen, setSaveOpen] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [exportOpen, setExportOpen] = useState(false)
  const [folds, setFolds] = useState({ curve: false, transparency: false, quality: false, optics: false })
  const [borderOn, setBorderOn] = useState(false)
  const [borderStyle, setBorderStyle] = useState<BorderStyle>('white')
  const [borderWidth, setBorderWidth] = useState(3)
  const [lutOpen, setLutOpen] = useState(false)

  const recipeRef = useRef(recipe)
  recipeRef.current = recipe

  /* 曲线控制点（0..1 归一化坐标），存入 recipe.light.curve，由后端按曲线重映射亮度 */
  const curvePoints = useMemo<CurvePoint[]>(() => {
    const raw = (recipe.light as { curve?: unknown } | undefined)?.curve
    if (Array.isArray(raw) && raw.length >= 2) return raw as CurvePoint[]
    return DEFAULT_CURVE_POINTS
  }, [recipe])

  /* 与显影台一致的照片信息派生值 */
  const exif = photo?.exif
  const cameraLabel = exif?.model || exif?.make || '未知机身'
  const lensLabel = exif?.lens || '未知镜头'
  const megapixels = Math.round((item.width * item.height) / 1e6)
  const metaParams = exif
    ? [
        exif.iso ? `ISO ` + exif.iso : '',
        exif.focal_length ? `` + exif.focal_length + ` mm` : '',
        exif.aperture ? `ƒ` + exif.aperture : '',
        exif.exposure ? `` + exif.exposure + ` s` : '',
      ].filter(Boolean)
    : []

  const canvasRef = useRef<HTMLDivElement>(null)
  const canvasSize = useElementSize(canvasRef)
  const railRef = useSmoothScroll<HTMLDivElement>('y')
  const panelRef = useSmoothScroll<HTMLDivElement>('y')

  const renderSeqRef = useRef(0)
  const renderChainRef = useRef<Promise<void>>(Promise.resolve())
  const renderInFlightRef = useRef(false)
  const cancelSentRef = useRef(false)
  const proxyTimerRef = useRef<number | null>(null)
  const settleTimerRef = useRef<number | null>(null)

  const submitPreview = useCallback(
    (edge: number, nextRecipe: Recipe) => {
      renderChainRef.current = renderChainRef.current.then(async () => {
        const seq = ++renderSeqRef.current
        renderInFlightRef.current = true
        cancelSentRef.current = false
        setBusy(true)
        try {
          const { job_id } = await request<{ job_id: string }>('POST', '/v1/grade/preview', {
            handoff: handoff.path,
            recipe: nextRecipe,
            edge,
          })
          void (async () => {
            try {
              const job = await waitForJob(job_id)
              if (seq !== renderSeqRef.current) return
              const result = job.result as unknown as {
                image_path: string
                width: number
                height: number
                analysis: GradePreview['analysis']
              }
              if (!result?.image_path) return
              setPreview({
                path: result.image_path,
                width: result.width,
                height: result.height,
                analysis: result.analysis,
              })
            } catch (error) {
              if (seq !== renderSeqRef.current) return
              const message = errorMessage(error)
              if (!message.includes('取消')) onNotify(message, true)
            } finally {
              if (seq === renderSeqRef.current) {
                renderInFlightRef.current = false
                setBusy(false)
              }
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
    [handoff.path, onNotify],
  )

  useEffect(() => {
    if (renderInFlightRef.current && !cancelSentRef.current) {
      cancelSentRef.current = true
      void request('POST', '/v1/grade/preview/cancel', {}).catch(() => undefined)
    }
    if (settleTimerRef.current) {
      window.clearTimeout(settleTimerRef.current)
      settleTimerRef.current = null
    }
    // 交互期用代理图：拖拽过程中每 120ms 最多提交一次，始终取最新配方。
    if (proxyTimerRef.current === null) {
      proxyTimerRef.current = window.setTimeout(() => {
        proxyTimerRef.current = null
        void submitPreview(PROXY_EDGE, recipeRef.current)
      }, 120)
    }
    settleTimerRef.current = window.setTimeout(() => {
      settleTimerRef.current = null
      void submitPreview(FULL_EDGE, recipeRef.current)
    }, 1100)
    return () => {
      if (settleTimerRef.current) {
        window.clearTimeout(settleTimerRef.current)
        settleTimerRef.current = null
      }
    }
  }, [recipe, handoff.path, submitPreview])

  useEffect(
    () => () => {
      if (proxyTimerRef.current) window.clearTimeout(proxyTimerRef.current)
      if (settleTimerRef.current) window.clearTimeout(settleTimerRef.current)
    },
    [],
  )

  useEffect(() => {
    ;(async () => {
      try {
        const [presetPayload, lutPayload] = await Promise.all([
          request<{ presets: PresetEntry[] }>('GET', '/v1/grade/presets'),
          request<{ luts: LutEntry[] }>('GET', '/v1/grade/luts'),
        ])
        setPresets(presetPayload.presets)
        setLuts(lutPayload.luts)
      } catch (error) {
        onNotify(errorMessage(error), true)
      }
    })()
  }, [onNotify])

  function update(path: string, value: unknown) {
    setRecipe((current) => write(current, path, value))
    setActivePreset('')
  }

  function applyPreset(preset: PresetEntry) {
    if (!preset.recipe) return
    setRecipe(preset.recipe)
    setActivePreset(preset.id)
  }

  async function importLut() {
    try {
      const path = await pickLut()
      if (!path) return
      const payload = await request<{ luts: LutEntry[]; path: string }>('POST', '/v1/grade/luts/import', {
        path,
      })
      setLuts(payload.luts)
      update('lut.path', payload.path)
      onNotify('LUT 已导入')
    } catch (error) {
      onNotify(errorMessage(error), true)
    }
  }

  async function savePreset() {
    try {
      const payload = await request<{ presets: PresetEntry[] }>('POST', '/v1/grade/presets', {
        name: saveName,
        recipe: recipeRef.current,
      })
      setPresets(payload.presets)
      setSaveOpen(false)
      setSaveName('')
      onNotify('预设已保存')
    } catch (error) {
      onNotify(errorMessage(error), true)
    }
  }

  async function deletePreset() {
    if (!activePreset) return
    try {
      const payload = await request<{ presets: PresetEntry[] }>('POST', '/v1/grade/presets/delete', {
        id: activePreset,
      })
      setPresets(payload.presets)
      setActivePreset('')
      onNotify('预设已删除')
    } catch (error) {
      onNotify(errorMessage(error), true)
    }
  }

  async function runExport(settings: ExportSettings) {
    setExportOpen(false)
    try {
      // 边框目前只在前端叠加预览；后端渲染接口预留：
      // POST /v1/grade/export 增加 border = { color, width_fraction } 即可烘进成片。
      const { job_id } = await request<{ job_id: string }>('POST', '/v1/grade/export', {
        handoff: handoff.path,
        recipe: recipeRef.current,
        settings,
        name: item.name,
      })
      const job = await waitForJob(job_id)
      const result = job.result as unknown as { path: string }
      onNotify(`已导出到 ${result.path}`)
    } catch (error) {
      onNotify(errorMessage(error), true)
    }
  }

  const slider = (
    path: string,
    label: string,
    min: number,
    max: number,
    step: number,
    decimals = 0,
    suffix = '',
  ) => (
    <ValueRow
      key={path}
      label={label}
      value={read(recipe, path)}
      min={min}
      max={max}
      step={step}
      decimals={decimals}
      suffix={suffix}
      onChange={(value) => update(path, value)}
      onReset={() => update(path, 0)}
    />
  )

  const activePresetEntry = presets.find((preset) => preset.id === activePreset)
  const mediaSrc = preview?.path ? `${mediaUrl(preview.path)}?v=${preview.path.slice(-12)}` : ''

  const fitScale = useMemo(() => {
    if (!preview || canvasSize.width === 0) return 1
    return Math.max(
      0.05,
      Math.min((canvasSize.width - 108) / preview.width, (canvasSize.height - 96) / preview.height),
    )
  }, [preview, canvasSize])

  const framePadding = preview && borderOn
    ? Math.round(Math.max(preview.width, preview.height) * fitScale * (borderWidth / 100))
    : 0
  return (
    <div className="grade-page">
      <header className="editor-topbar">
        <Button icon="chevronLeft" kind="secondary" height={28} onClick={onBack}>
          显影台
        </Button>

        <span className="grow" />


        <Button icon="upload" kind="primary" height={28} onClick={() => setExportOpen(true)}>
          导出
        </Button>
      </header>

      <div className="grade-body">
        <aside className="grade-rail">
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
              {metaParams.length > 0 ? (
                <div className="photo-meta-params">
                  {metaParams.map((value, index) => (
                    <span key={index}>{value}</span>
                  ))}
                </div>
              ) : null}
            </div>
          </div>

          <div className="grade-rail-tabs">
            <Tabs
              tabs={[
                { value: 'lut', label: 'LUT' },
                { value: 'preset', label: '预设' },
                { value: 'border', label: '边框' },
              ]}
              value={railTab}
              onChange={setRailTab}
            />
          </div>

          <div className="grade-rail-scroll" ref={railRef}>
            {railTab === 'lut' ? (
              <div className="lut-list">
                <div className={`lut-card${(recipe.lut?.path ?? '') === '' ? ' active' : ''}`}>
                  <button
                    className="lut-card-head"
                    onClick={() => {
                      update('lut.path', '')
                      setLutOpen(false)
                    }}
                  >
                    <span className="lut-card-glyph">
                      <Icon name="close" size={12} />
                    </span>
                    <span className="stack grow" style={{ minWidth: 0 }}>
                      <span className="lut-card-title">无 LUT</span>
                      <span className="lut-card-sub">不加载任何 LUT</span>
                    </span>
                  </button>
                </div>
                {luts.map((lut) => {
                  const active = recipe.lut?.path === lut.path
                  return (
                    <div
                      key={lut.path}
                      className={`lut-card${active ? ' active' : ''}${active && lutOpen ? ' open' : ''}`}
                    >
                      <button
                        className="lut-card-head"
                        onClick={() => {
                          if (active) {
                            setLutOpen(!lutOpen)
                          } else {
                            update('lut.path', lut.path)
                            setLutOpen(true)
                          }
                        }}
                      >
                        <span className="lut-card-glyph">
                          <Icon name="sliders" size={13} />
                        </span>
                        <span className="stack grow" style={{ minWidth: 0 }}>
                          <span className="lut-card-title truncate">{lut.name}</span>
                          <span className="lut-card-sub">3D LUT</span>
                        </span>
                      </button>
                      <div className="lut-card-body">
                        {slider('lut.strength', 'LUT 强度', 0, 100, 1, 0, '%')}
                      </div>
                    </div>
                  )
                })}
                <div className="lut-card lut-card-import">
                  <button className="lut-card-head" onClick={() => void importLut()}>
                    <span className="lut-card-glyph">
                      <Icon name="importArrow" size={13} />
                    </span>
                    <span className="stack grow" style={{ minWidth: 0 }}>
                      <span className="lut-card-title">导入 LUT</span>
                      <span className="lut-card-sub">从磁盘选择文件</span>
                    </span>
                  </button>
                </div>
              </div>
            ) : null}

            {railTab === 'preset' ? (
              <>
                {presets.map((preset) => (
                  <button
                    key={preset.id}
                    className={`preset-mini${activePreset === preset.id ? ' active' : ''}`}
                    onClick={() => applyPreset(preset)}
                    style={{ width: '100%', marginBottom: 2 }}
                  >
                    <div className="preset-name truncate">{preset.name}</div>
                    <div className="preset-meta">{preset.builtin ? '内置' : '用户'}</div>
                  </button>
                ))}
                <div style={{ display: 'flex', gap: 6, padding: '10px 2px' }}>
                  <Button kind="secondary" onClick={() => setSaveOpen(true)}>
                    保存当前
                  </Button>
                  {activePresetEntry && !activePresetEntry.builtin ? (
                    <Button kind="quiet" onClick={() => void deletePreset()}>
                      删除
                    </Button>
                  ) : null}
                </div>
              </>
            ) : null}

            {railTab === 'border' ? (
              <>
                <div className="rail-group-title">边框样式</div>
                <button
                  className={`border-row${!borderOn ? ' active' : ''}`}
                  onClick={() => setBorderOn(false)}
                >
                  <span className="border-chip">
                    <span
                      className="border-chip-swatch"
                      style={{ border: '1px dashed var(--text-4)', background: 'transparent' }}
                    />
                  </span>
                  <span className="stack grow" style={{ minWidth: 0 }}>
                    <span className="preset-name truncate">无边框</span>
                    <span className="preset-meta truncate">不添加任何边</span>
                  </span>
                </button>
                {(['white', 'black'] as BorderStyle[]).map((style) => (
                  <button
                    key={style}
                    className={`border-row${borderOn && borderStyle === style ? ' active' : ''}`}
                    onClick={() => {
                      setBorderStyle(style)
                      setBorderOn(true)
                    }}
                  >
                    <span className="border-chip">
                      <span className="border-chip-swatch" style={{ background: BORDER_COLORS[style] }} />
                    </span>
                    <span className="stack grow" style={{ minWidth: 0 }}>
                      <span className="preset-name truncate">{BORDER_LABELS[style]}</span>
                      <span className="preset-meta truncate">
                        {style === 'white' ? '相纸白' : '深黑'} · 宽度在右侧调
                      </span>
                    </span>
                  </button>
                ))}
                <div className="micro" style={{ marginTop: 10, lineHeight: 1.6 }}>
                  边框先在预览里叠加，导出接口已预留，后续接后端即可烘进成片。
                </div>
              </>
            ) : null}
          </div>
        </aside>

        <section className="grade-canvas" ref={canvasRef}>
          {mediaSrc && preview ? (
            <div
              className="grade-stage"
              style={{
                padding: `${framePadding}px`,
                background: borderOn ? BORDER_COLORS[borderStyle] : 'transparent',
                boxShadow: borderOn ? '0 18px 46px rgba(0, 0, 0, 0.5)' : 'none',
              }}
            >
              <img
                key={mediaSrc}
                className="grade-image"
                src={mediaSrc}
                alt={item.name}
                draggable={false}
                style={{ width: preview.width * fitScale, height: preview.height * fitScale }}
              />
            </div>
          ) : (
            <div className="caption">{busy ? '正在生成调色预览…' : '暂无预览'}</div>
          )}
          {busy ? <div className="canvas-progress">渲染调色</div> : null}
        </section>

        <aside className="grade-panel">
          <div className="inspector-tabs">
            <Tabs
              tabs={[
                { value: 'light', label: '光影' },
                { value: 'color', label: '色彩' },
              ]}
              value={tab}
              onChange={setTab}
            />
          </div>
          <div className="inspector-body" ref={panelRef}>
            <Histogram src={mediaSrc} />
            {preview?.analysis ? (
              <div className="analysis-line">
                <span className="truncate">黑场 {preview.analysis.black_point.toFixed(2)}</span>
                <span className="truncate">白场 {preview.analysis.white_point.toFixed(2)}</span>
                <span className="truncate">
                  {preview.analysis.highlight_cast} / {preview.analysis.shadow_cast}
                </span>
              </div>
            ) : null}

            {tab === 'light' ? (
              <>
                {slider('light.exposure', '曝光', -5, 5, 0.05, 2, ' EV')}
                {slider('light.contrast', '对比度', -100, 100, 1)}
                {slider('light.highlights', '高光', -100, 100, 1)}
                {slider('light.shadows', '阴影', -100, 100, 1)}
                {slider('light.whites', '白色', -100, 100, 1)}
                {slider('light.blacks', '黑色', -100, 100, 1)}
                {slider('light.midtones', '中间调', -100, 100, 1)}
                {slider('light.highlight_rolloff', '高光柔和', 0, 100, 1)}
                <Disclosure
                  title="曲线"
                  open={folds.curve}
                  onToggle={() => setFolds((current) => ({ ...current, curve: !current.curve }))}
                >
                  {/* 曲线点写入 recipe.light.curve，由后端渲染时应用 */}
                  <CurveEditor
                    points={curvePoints}
                    onChange={(points) => update('light.curve', points)}
                  />
                </Disclosure>
              </>
            ) : (
              <>
                {slider('color.temperature', '色温', -100, 100, 1)}
                {slider('color.tint', '色调', -100, 100, 1)}
                {slider('color.vibrance', '自然饱和度', -100, 100, 1)}
                {slider('color.saturation', '饱和度', -100, 100, 1)}
                {slider('color.hue_shift', '色相偏移', -180, 180, 1, 0, '°')}
                {slider('color.color_density', '色彩密度', 0, 100, 1)}
              </>
            )}

            <div style={{ marginTop: 14 }}>
              <Disclosure
                title="通透"
                open={folds.transparency}
                onToggle={() => setFolds((current) => ({ ...current, transparency: !current.transparency }))}
              >
                {slider('transparency.tonal', '明暗通透', 0, 100, 1)}
                {slider('transparency.color', '颜色通透', 0, 100, 1)}
              </Disclosure>
              <Disclosure
                title="画质"
                open={folds.quality}
                onToggle={() => setFolds((current) => ({ ...current, quality: !current.quality }))}
              >
                {slider('quality.clarity', '清晰度', -100, 100, 1)}
                {slider('quality.texture', '纹理', -100, 100, 1)}
                {slider('quality.dehaze', '去雾', -100, 100, 1)}
                {slider('quality.sharpen_amount', '锐化', 0, 100, 1)}
                {slider('quality.sharpen_radius', '锐化半径', 0.5, 3, 0.01, 2)}
                {slider('quality.sharpen_threshold', '锐化阈值', 0, 100, 1)}
                {slider('quality.noise_luminance', '明度降噪', 0, 100, 1)}
                {slider('quality.noise_color', '色彩降噪', 0, 100, 1)}
              </Disclosure>
              <Disclosure
                title="光学"
                open={folds.optics}
                onToggle={() => setFolds((current) => ({ ...current, optics: !current.optics }))}
              >
                {slider('optics.vignette_amount', '暗角', -100, 100, 1)}
                {slider('optics.vignette_midpoint', '暗角中心', 0, 100, 1)}
                {slider('optics.vignette_roundness', '暗角圆度', -100, 100, 1)}
                {slider('optics.vignette_feather', '暗角羽化', 0, 100, 1)}
                {slider('optics.grain_amount', '颗粒强度', 0, 100, 1)}
                {slider('optics.grain_size', '颗粒大小', 0, 100, 1)}
                {slider('optics.grain_roughness', '颗粒粗糙度', 0, 100, 1)}
                {slider('optics.chromatic_aberration', '色差', -100, 100, 1)}
              </Disclosure>
              <Disclosure
                title="边框"
                open
                onToggle={() => {
                  // 边框常驻展开，样式在左侧栏选
                }}
              >
                <SwitchRow
                  label="启用边框"
                  checked={borderOn}
                  onChange={setBorderOn}
                  hint="渲染边框：先叠在预览上，导出接口已预留"
                />
                <ValueRow
                  label="边框宽度"
                  value={borderWidth}
                  min={0}
                  max={12}
                  step={0.5}
                  decimals={1}
                  suffix="%"
                  disabled={!borderOn}
                  onChange={setBorderWidth}
                  onReset={() => setBorderWidth(0)}
                />
              </Disclosure>
            </div>
          </div>
        </aside>
      </div>

      {saveOpen ? (
        <div className="modal-scrim" onMouseDown={() => setSaveOpen(false)}>
          <div className="modal" style={{ width: 360 }} onMouseDown={(event) => event.stopPropagation()}>
            <div className="modal-head">
              <div className="modal-title">保存调色预设</div>
            </div>
            <div className="modal-body">
              <FieldRow label="名称">
                <input
                  className="input"
                  value={saveName}
                  autoFocus
                  onChange={(event) => setSaveName(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') void savePreset()
                  }}
                />
              </FieldRow>
            </div>
            <div className="modal-foot">
              <Button kind="secondary" onClick={() => setSaveOpen(false)}>
                取消
              </Button>
              <Button kind="primary" onClick={() => void savePreset()}>
                保存
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {exportOpen ? (
        <ExportDialog
          initial={bootstrap.export_settings}
          onClose={() => setExportOpen(false)}
          onConfirm={(settings) => void runExport(settings)}
        />
      ) : null}
    </div>
  )
}
