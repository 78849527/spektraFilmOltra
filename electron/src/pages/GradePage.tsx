import { useCallback, useEffect, useRef, useState } from 'react'
import { errorMessage, mediaUrl, pickLut, request, waitForJob } from '../api'
import { Button, Disclosure, FieldRow, Tabs, ValueRow } from '../components/Controls'
import { ExportDialog } from '../components/ExportDialog'
import { Histogram } from '../components/Histogram'
import { Icon } from '../components/Icons'
import type { Bootstrap, ExportSettings, ItemRecord, PresetEntry, Recipe } from '../types'
import './pages.css'

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
  onBack,
  onNotify,
}: {
  bootstrap: Bootstrap
  item: ItemRecord
  handoff: string
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
  const [railTab, setRailTab] = useState<'lut' | 'preset'>('lut')
  const [saveOpen, setSaveOpen] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [exportOpen, setExportOpen] = useState(false)
  const [folds, setFolds] = useState({ curve: false, transparency: false, quality: false, optics: false })

  const recipeRef = useRef(recipe)
  recipeRef.current = recipe

  const renderPreview = useCallback(
    async (nextRecipe: Recipe) => {
      setBusy(true)
      try {
        const { job_id } = await request<{ job_id: string }>('POST', '/v1/grade/preview', {
          handoff,
          recipe: nextRecipe,
          edge: 1600,
        })
        const job = await waitForJob(job_id)
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
        const message = errorMessage(error)
        if (!message.includes('取消')) onNotify(message, true)
      } finally {
        setBusy(false)
      }
    },
    [handoff, onNotify],
  )

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void renderPreview(recipeRef.current)
    }, 120)
    return () => window.clearTimeout(timer)
  }, [recipe, handoff, renderPreview])

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
      const { job_id } = await request<{ job_id: string }>('POST', '/v1/grade/export', {
        handoff,
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

  return (
    <div className="grade-page">
      <header className="editor-topbar">
        <Button icon="chevronLeft" kind="secondary" height={28} onClick={onBack}>
          显影台
        </Button>

        <div className="editor-title grow">
          <span className="editor-title-main truncate">{item.name}</span>
          <span className="editor-title-sub truncate">
            交接图 · 16-bit ProPhoto 线性
            {preview ? ` · ${preview.width} × ${preview.height}` : ''}
          </span>
        </div>

        <span className="badge badge-accent">调色台</span>

        <Button icon="upload" kind="primary" height={28} onClick={() => setExportOpen(true)}>
          导出
        </Button>
      </header>

      <div className="grade-body">
        <aside className="grade-rail">
          <div style={{ padding: '10px 12px 4px' }}>
            <Tabs
              tabs={[
                { value: 'lut', label: 'LUT' },
                { value: 'preset', label: '预设' },
              ]}
              value={railTab}
              onChange={setRailTab}
            />
          </div>

          <div style={{ flex: 1, overflow: 'auto', padding: '8px 8px 14px' }}>
            {railTab === 'lut' ? (
              <>
                <button
                  className={`lut-row${(recipe.lut?.path ?? '') === '' ? ' active' : ''}`}
                  onClick={() => update('lut.path', '')}
                >
                  无 LUT
                </button>
                {luts.map((lut) => (
                  <button
                    key={lut.path}
                    className={`lut-row${recipe.lut?.path === lut.path ? ' active' : ''}`}
                    onClick={() => update('lut.path', lut.path)}
                  >
                    <Icon name="sliders" size={12} />
                    <span className="truncate">{lut.name}</span>
                  </button>
                ))}
                <div style={{ padding: '10px 10px 0' }}>
                  {slider('lut.strength', 'LUT 强度', 0, 100, 1, 0, '%')}
                  <Button icon="plus" kind="secondary" onClick={() => void importLut()}>
                    导入 LUT
                  </Button>
                </div>
              </>
            ) : (
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
            )}
          </div>
        </aside>

        <section className="grade-canvas">
          {mediaSrc ? (
            <img
              src={mediaSrc}
              alt={item.name}
              style={{
                maxWidth: 'calc(100% - 110px)',
                maxHeight: 'calc(100% - 100px)',
                objectFit: 'contain',
                boxShadow: '0 18px 46px rgba(0, 0, 0, 0.5)',
              }}
              draggable={false}
            />
          ) : (
            <div className="caption">{busy ? '正在生成调色预览…' : '暂无预览'}</div>
          )}
          {busy ? <div className="canvas-progress">渲染中…</div> : null}
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
          <div className="inspector-body">
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
                  {slider('light.curve_highlights', '高光点', -100, 100, 1)}
                  {slider('light.curve_lights', '亮部点', -100, 100, 1)}
                  {slider('light.curve_darks', '暗部点', -100, 100, 1)}
                  {slider('light.curve_shadows', '阴影点', -100, 100, 1)}
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
                  style={{ width: '100%' }}
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
