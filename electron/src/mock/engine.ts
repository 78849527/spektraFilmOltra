// Dev-only in-browser mock of the Python engine API.
// Mirrors src/spektrafilm_service/server.py routes so the UI can run in a
// plain browser without Electron preload or the real engine.
// Only loaded when import.meta.env.DEV and window.spektra is absent.
import fixtures from './fixtures.json'
import type {
  Bootstrap,
  FolderRecord,
  ItemRecord,
  JobStatus,
  LibrarySnapshot,
  OpenedPhoto,
  PresetEntry,
  QuickPayload,
  Recipe,
  StateTree,
} from '../types'

const bootstrap = fixtures.bootstrap as unknown as Bootstrap
const defaultState = clone(fixtures.state as unknown as StateTree)
const axisSpecs = (fixtures.quick as unknown as QuickPayload).axes

let state: StateTree = clone(defaultState)
let intents: Record<string, number> = {}
let currentPhotoPath = ''

interface JobRecord {
  id: string
  kind: string
  state: JobStatus['state']
  progress: { label: string; index: number; total: number }
  result: Record<string, unknown> | null
  error: string | null
  cancelled: boolean
}

const jobs = new Map<string, JobRecord>()
let jobSeq = 0

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function hashStr(value: string): string {
  let h = 2166136261
  for (let i = 0; i < value.length; i += 1) {
    h ^= value.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return (h >>> 0).toString(36)
}

const MOCK_CAMERAS = [
  { make: 'Canon', model: 'Canon EOS R5', lens: 'RF24-70mm F2.8 L IS USM', exposure: '1/250', aperture: '4', iso: '400', focal_length: '35', taken_at: '2026:10:18 16:42:11' },
  { make: 'NIKON CORPORATION', model: 'NIKON Z 7_2', lens: 'NIKKOR Z 24-70mm f/2.8 S', exposure: '1/500', aperture: '2.8', iso: '200', focal_length: '50', taken_at: '2026:10:18 15:10:02' },
  { make: 'SONY', model: 'ILCE-7RM4', lens: 'FE 35mm F1.4 GM', exposure: '1/125', aperture: '1.4', iso: '100', focal_length: '35', taken_at: '2026:10:17 09:21:30' },
  { make: 'FUJIFILM', model: 'X-T4', lens: 'XF23mmF1.4 R', exposure: '1/60', aperture: '2', iso: '800', focal_length: '23', taken_at: '2026:10:16 18:05:44' },
  { make: 'Apple', model: 'iPhone 15 Pro', lens: 'Main Camera 24mm f/1.78', exposure: '1/120', aperture: '1.78', iso: '64', focal_length: '24', taken_at: '2026:10:20 12:33:09' },
  { make: 'Xiaomi', model: 'Xiaomi 14 Ultra', lens: 'Leica Summilux 23mm', exposure: '1/200', aperture: '1.63', iso: '50', focal_length: '23', taken_at: '2026:10:19 08:14:52' },
]

function pickExif(path: string) {
  let seed = 0
  for (let index = 0; index < path.length; index += 1) seed = (seed + path.charCodeAt(index)) % 997
  return MOCK_CAMERAS[seed % MOCK_CAMERAS.length]
}

function quickPayload() {
  return { intents: { ...intents }, axes: axisSpecs, disabled: [] as string[] }
}

function submitJob(
  kind: string,
  steps: Array<{ label: string; index: number; total: number }>,
  makeResult: () => Record<string, unknown>,
  stepMs = 170,
): JobRecord {
  const id = `j_${(jobSeq += 1)}`
  const job: JobRecord = {
    id,
    kind,
    state: 'running',
    progress: { label: 'preparing', index: 0, total: 1 },
    result: null,
    error: null,
    cancelled: false,
  }
  jobs.set(id, job)
  let step = 0
  const timer = window.setInterval(() => {
    if (job.cancelled) {
      job.state = 'cancelled'
      window.clearInterval(timer)
      return
    }
    if (step < steps.length) {
      job.progress = steps[step]
      step += 1
    } else {
      job.state = 'done'
      job.result = makeResult()
      window.clearInterval(timer)
    }
  }, stepMs)
  return job
}

// ── fake library store ──────────────────────────────────────────────
let folders: FolderRecord[] = [
  { id: 'inbox', name: 'Inbox', path: '', added_at: 1730000000 },
  { id: 'fld_street', name: 'Street', path: 'C:/Users/DEV/Photos/Street', added_at: 1730100000 },
  { id: 'fld_portrait', name: 'Portrait', path: 'C:/Users/DEV/Photos/Portrait', added_at: 1730200000 },
]

interface Sample {
  name: string
  folder: string
  w: number
  h: number
  raw: boolean
  size: number
  favorite?: boolean
  color?: string
  film?: string
  paper?: string
}

const SAMPLES: Sample[] = [
  { name: 'IMG_0201.CR2', folder: 'fld_street', w: 6000, h: 4000, raw: true, size: 24500000, favorite: true, film: 'kodak_portra_400', paper: 'kodak_2383' },
  { name: 'IMG_0202.CR2', folder: 'fld_street', w: 6000, h: 4000, raw: true, size: 23900000, color: 'yellow' },
  { name: 'IMG_0205.CR2', folder: 'fld_street', w: 6000, h: 4000, raw: true, size: 25100000, film: 'kodak_ektar_100', paper: 'kodak_endura_premier' },
  { name: 'IMG_0208.CR2', folder: 'fld_street', w: 6000, h: 4000, raw: true, size: 24800000, color: 'red' },
  { name: 'IMG_0211.CR2', folder: 'fld_street', w: 6000, h: 4000, raw: true, size: 25300000, favorite: true },
  { name: 'DSC_0110.TIF', folder: 'fld_portrait', w: 5000, h: 7500, raw: false, size: 108000000, film: 'fujifilm_pro_400h', paper: 'kodak_ultra_endura' },
  { name: 'DSC_0113.TIF', folder: 'fld_portrait', w: 5000, h: 7500, raw: false, size: 106000000, color: 'green' },
  { name: 'DSC_0118.CR2', folder: 'fld_portrait', w: 6720, h: 4480, raw: true, size: 31200000, favorite: true, film: 'kodak_portra_800', paper: 'kodak_ektacolor_edge' },
  { name: 'DSC_0121.CR2', folder: 'fld_portrait', w: 6720, h: 4480, raw: true, size: 30800000 },
  { name: 'scan_0004.tif', folder: 'inbox', w: 4800, h: 3200, raw: false, size: 44000000 },
]

function folderPathOf(folderId: string): string {
  const folder = folders.find((entry) => entry.id === folderId)
  return folder && folder.path ? `${folder.path}/` : 'C:/Users/DEV/Photos/Inbox/'
}

let items: ItemRecord[] = SAMPLES.map((sample, index) => {
  const adjusted = Boolean(sample.film)
  return {
    id: `itm_${String(index + 1).padStart(3, '0')}`,
    path: `${folderPathOf(sample.folder)}${sample.name}`,
    name: sample.name,
    folder_id: sample.folder,
    added_at: 1730300000 + index * 3600,
    favorite: Boolean(sample.favorite),
    color: sample.color ?? '',
    adjusted,
    film_stock: sample.film ?? '',
    print_paper: sample.paper ?? '',
    width: sample.w,
    height: sample.h,
    is_raw: sample.raw,
    file_size: sample.size,
    mtime: 1730300000 + index * 3600,
    state: adjusted ? clone(defaultState) : null,
  }
})

function snapshot(): LibrarySnapshot {
  return {
    folders: clone(folders),
    items: clone(items),
    folder_count: folders.length,
    item_count: items.length,
    inbox_id: 'inbox',
  }
}

function makeItem(path: string, folderId: string, index: number): ItemRecord {
  const name = path.split(/[\\/]/).pop() ?? `photo_${index}.tif`
  const isRaw = /\.(cr2|cr3|nef|arw|dng|raf|orf|rw2|pef|srw)$/i.test(name)
  return {
    id: `itm_${hashStr(path)}`,
    path,
    name,
    folder_id: folderId,
    added_at: Math.floor(Date.now() / 1000),
    favorite: false,
    color: '',
    adjusted: false,
    film_stock: '',
    print_paper: '',
    width: 6000,
    height: 4000,
    is_raw: isRaw,
    file_size: isRaw ? 24000000 : 48000000,
    mtime: Math.floor(Date.now() / 1000),
    state: null,
  }
}

// ── grade presets / luts ────────────────────────────────────────────
function presetRecipe(mutate: (recipe: Recipe) => void): Recipe {
  const recipe = clone(bootstrap.grade_recipe) as Recipe
  mutate(recipe)
  return recipe
}

let presets: PresetEntry[] = [
  {
    id: 'ps_builtin_warm',
    name: 'Warm Print',
    builtin: true,
    recipe: presetRecipe((recipe) => {
      recipe.light.exposure = 0.2
      recipe.light.contrast = 8
      recipe.color.temperature = 18
      recipe.transparency.tonal = 30
    }),
  },
  {
    id: 'ps_builtin_cyan',
    name: 'Cyan Negative',
    builtin: true,
    recipe: presetRecipe((recipe) => {
      recipe.color.tint = -12
      recipe.color.color_density = 20
      recipe.light.shadows = -15
    }),
  },
  {
    id: 'ps_builtin_bw',
    name: 'High Contrast B&W',
    builtin: true,
    recipe: presetRecipe((recipe) => {
      recipe.light.contrast = 35
      recipe.color.saturation = -80
      recipe.quality.clarity = 25
    }),
  },
]

let luts = [
  { name: 'Cinematic Teal', path: 'C:/Users/DEV/AppData/Roaming/Spektrafilm/luts/cinematic_teal.cube' },
  { name: 'Kodak 2383 Print', path: 'C:/Users/DEV/AppData/Roaming/Spektrafilm/luts/kodak_2383.cube' },
]

// ── endpoint router ─────────────────────────────────────────────────
export function handle(method: string, endpoint: string, body?: Record<string, unknown>): unknown {
  const payload = body ?? {}

  if (method === 'GET' && endpoint === '/v1/health') return { ready: true }
  if (method === 'GET' && endpoint === '/v1/bootstrap') return clone(bootstrap)

  if (method === 'GET' && endpoint === '/v1/state') return { state: clone(state) }
  if (method === 'POST' && endpoint === '/v1/state') {
    if (payload.state) state = clone(payload.state as StateTree)
    return { state: clone(state), ...quickPayload() }
  }

  if (method === 'GET' && endpoint === '/v1/quick') return quickPayload()
  if (method === 'POST' && endpoint === '/v1/quick/axis') {
    intents[String(payload.axis ?? '')] = Number(payload.value ?? 0)
    return { state: clone(state), ...quickPayload() }
  }
  if (method === 'POST' && endpoint === '/v1/quick/reset') {
    intents = {}
    return { state: clone(state), ...quickPayload() }
  }
  if (method === 'POST' && endpoint === '/v1/reset') {
    state = clone(defaultState)
    intents = {}
    return { state: clone(state), ...quickPayload() }
  }

  if (method === 'GET' && endpoint === '/v1/photo') return { photo: null }
  if (method === 'POST' && endpoint === '/v1/photos/open') {
    const path = String(payload.path ?? '')
    currentPhotoPath = path
    const item = items.find((entry) => entry.path === path)
    const isRaw = Boolean(item?.is_raw ?? /\.cr2|\.cr3|\.nef|\.arw|\.dng$/i.test(path))
    const opened: OpenedPhoto = {
      photo_id: hashStr(path),
      path,
      width: item?.width ?? 6000,
      height: item?.height ?? 4000,
      is_raw: isRaw,
      color_space: isRaw ? 'ProPhoto RGB' : 'sRGB',
      cctf_decoding: !isRaw,
      lens_summary: isRaw ? 'RAW decode (mock)' : 'RGB input',
      original_preview: `${path}@original`,
      display_preview: `${path}@display`,
      state: clone(state),
      exif: pickExif(path),
    }
    return opened
  }

  if (method === 'POST' && endpoint === '/v1/preview') {
    const scale = Number(payload.scale ?? 0.5)
    const longEdge = scale >= 1 ? 1600 : 800
    const key = hashStr(`${currentPhotoPath}:${scale}:${JSON.stringify(state).length}`)
    const job = submitJob(
      'preview',
      [
        { label: 'preprocess', index: 1, total: 6 },
        { label: 'filming.expose', index: 2, total: 6 },
        { label: 'filming.develop', index: 3, total: 6 },
        { label: 'printing.expose', index: 4, total: 6 },
        { label: 'printing.develop', index: 5, total: 6 },
        { label: 'scanning.scan_print', index: 6, total: 6 },
      ],
      () => ({
        image_path: `${currentPhotoPath}@render@${scale}@${key}`,
        width: longEdge,
        height: Math.round((longEdge * 2) / 3),
        output_color_space: 'sRGB',
        elapsed_ms: 380,
        timings: {},
        status: '',
        fingerprint: key,
      }),
    )
    return { job_id: job.id }
  }

  if (method === 'POST' && endpoint === '/v1/export') {
    const job = submitJob(
      'export',
      [
        { label: 'preprocess', index: 2, total: 6 },
        { label: 'scanning.scan_print', index: 6, total: 6 },
      ],
      () => ({
        path: `C:/Users/DEV/Pictures/${currentPhotoPath.split(/[\\/]/).pop()?.split('.')[0] ?? 'export'}_spektrafilm.jpg`,
        color_space: 'sRGB',
        cctf_encoding: true,
      }),
      260,
    )
    return { job_id: job.id }
  }

  if (method === 'POST' && endpoint === '/v1/handoff') {
    const job = submitJob(
      'handoff',
      [
        { label: 'preprocess', index: 2, total: 6 },
        { label: 'scanning.scan_print', index: 6, total: 6 },
      ],
      () => ({
        path: `C:/Users/DEV/AppData/Roaming/Spektrafilm/handoff/${hashStr(currentPhotoPath)}.tif`,
        color_space: 'ProPhoto RGB',
        width: 6000,
        height: 4000,
        source_color_space: 'sRGB',
        bytes: 412000000,
      }),
      260,
    )
    return { job_id: job.id }
  }

  if (method === 'GET' && endpoint === '/v1/library') return snapshot()
  if (method === 'POST' && endpoint === '/v1/library/scan') {
    const path = String(payload.path ?? '')
    const name = path.split(/[\\/]/).pop() ?? 'Folder'
    const folder: FolderRecord = {
      id: `fld_${hashStr(path)}`,
      name,
      path,
      added_at: Math.floor(Date.now() / 1000),
    }
    folders = [...folders, folder]
    const added = [1, 2, 3].map((index) => makeItem(`${path}/IMG_${900 + index}.CR2`, folder.id, index))
    items = [...items, ...added]
    return { folder: clone(folder), added: clone(added), ...snapshot() }
  }
  if (method === 'POST' && endpoint === '/v1/library/photos') {
    const paths = (payload.paths as string[] | undefined) ?? []
    const added = paths.map((path, index) => makeItem(path, 'inbox', index))
    items = [...items, ...added]
    return { added: clone(added), ...snapshot() }
  }
  if (method === 'POST' && endpoint === '/v1/library/remove') {
    const ids = new Set(((payload.ids as string[] | undefined) ?? []))
    const removed = items.filter((item) => ids.has(item.id)).map((item) => item.id)
    items = items.filter((item) => !ids.has(item.id))
    return { removed, ...snapshot() }
  }
  if (method === 'POST' && endpoint === '/v1/library/mark') {
    const id = String(payload.id ?? '')
    items = items.map((item) =>
      item.id === id
        ? {
            ...item,
            favorite: payload.favorite === undefined ? item.favorite : Boolean(payload.favorite),
            color: payload.color === undefined ? item.color : String(payload.color),
          }
        : item,
    )
    const item = items.find((entry) => entry.id === id)
    return { item: item ? clone(item) : null }
  }
  if (method === 'POST' && endpoint === '/v1/library/thumb') {
    const item = items.find((entry) => entry.id === String(payload.id ?? ''))
    if (!item) throw new Error('photo not in library')
    const portrait = item.height > item.width
    return {
      path: `${item.path}@thumb${portrait ? '@portrait' : ''}`,
      width: item.width,
      height: item.height,
      cached: true,
    }
  }
  if (method === 'POST' && endpoint === '/v1/library/state') {
    const id = String(payload.id ?? '')
    items = items.map((item) =>
      item.id === id
        ? {
            ...item,
            state: clone((payload.state as StateTree | undefined) ?? item.state ?? defaultState),
            film_stock: String(payload.film_stock ?? item.film_stock),
            print_paper: String(payload.print_paper ?? item.print_paper),
            adjusted: true,
          }
        : item,
    )
    const item = items.find((entry) => entry.id === id)
    return { item: item ? clone(item) : null }
  }

  if (method === 'GET' && endpoint === '/v1/grade/presets') return { presets: clone(presets) }
  if (method === 'POST' && endpoint === '/v1/grade/presets') {
    const preset: PresetEntry = {
      id: `ps_user_${hashStr(String(payload.name ?? '') + Date.now())}`,
      name: String(payload.name ?? 'Untitled'),
      recipe: clone((payload.recipe as Recipe | undefined) ?? (bootstrap.grade_recipe as Recipe)),
      builtin: false,
    }
    presets = [...presets, preset]
    return { preset: clone(preset), presets: clone(presets) }
  }
  if (method === 'POST' && endpoint === '/v1/grade/presets/rename') {
    presets = presets.map((preset) =>
      preset.id === String(payload.id ?? '') ? { ...preset, name: String(payload.name ?? preset.name) } : preset,
    )
    return { presets: clone(presets) }
  }
  if (method === 'POST' && endpoint === '/v1/grade/presets/delete') {
    const id = String(payload.id ?? '')
    presets = presets.filter((preset) => preset.id !== id)
    return { deleted: id, presets: clone(presets) }
  }

  if (method === 'GET' && endpoint === '/v1/grade/luts') return { luts: clone(luts) }
  if (method === 'POST' && endpoint === '/v1/grade/luts/import') {
    const path = String(payload.path ?? '')
    const name = (path.split(/[\\/]/).pop() ?? 'lut.cube').replace(/\.cube$/i, '')
    const entry = { name, path: `C:/Users/DEV/AppData/Roaming/Spektrafilm/luts/${name}.cube` }
    luts = [...luts.filter((lut) => lut.path !== entry.path), entry]
    return { name: entry.name, path: entry.path, luts: clone(luts) }
  }
  if (method === 'POST' && endpoint === '/v1/grade/luts/remove') {
    const path = String(payload.path ?? '')
    luts = luts.filter((lut) => lut.path !== path)
    return { luts: clone(luts) }
  }

  if (method === 'POST' && endpoint === '/v1/grade/preview') {
    const handoff = String(payload.handoff ?? '')
    const key = hashStr(`${handoff}:${JSON.stringify(payload.recipe ?? {}).length}`)
    const job = submitJob(
      'grade_preview',
      [
        { label: 'load handoff', index: 0, total: 2 },
        { label: 'render grade', index: 1, total: 2 },
      ],
      () => ({
        image_path: `${handoff}@grade@${key}`,
        width: 1600,
        height: 1067,
        analysis: {
          black_point: 0.018,
          white_point: 0.986,
          highlight_cast: 'neutral',
          shadow_cast: 'warm',
          summary: 'mock analysis',
        },
      }),
    )
    return { job_id: job.id }
  }
  if (method === 'POST' && endpoint === '/v1/grade/export') {
    const job = submitJob(
      'grade_export',
      [
        { label: 'load handoff', index: 0, total: 2 },
        { label: 'render full', index: 1, total: 2 },
      ],
      () => ({
        path: `C:/Users/DEV/Pictures/${String(payload.name ?? 'graded')}_graded.jpg`,
        color_space: 'sRGB',
        cctf_encoding: true,
      }),
      260,
    )
    return { job_id: job.id }
  }

  const jobMatch = endpoint.match(/^\/v1\/jobs\/([^/]+)$/)
  if (method === 'GET' && jobMatch) {
    const job = jobs.get(jobMatch[1])
    if (!job) throw new Error('job not found')
    return clone({
      id: job.id,
      kind: job.kind,
      state: job.state,
      progress: job.progress,
      result: job.result,
      error: job.error,
    })
  }
  const cancelMatch = endpoint.match(/^\/v1\/jobs\/([^/]+)\/cancel$/)
  if (method === 'POST' && cancelMatch) {
    const job = jobs.get(cancelMatch[1])
    if (!job) throw new Error('job not found')
    job.cancelled = true
    return { ok: true }
  }

  throw new Error(`mock: unknown endpoint ${method} ${endpoint}`)
}

export function mediaUrl(filePath: string): string {
  return `/mock-media/${encodeURIComponent(filePath)}`
}

export async function pickFolder(): Promise<string | null> {
  return 'C:/Users/DEV/Photos/Mock Roll'
}

export async function pickImages(): Promise<string[]> {
  return [
    'C:/Users/DEV/Photos/Mock Roll/IMG_9001.CR2',
    'C:/Users/DEV/Photos/Mock Roll/IMG_9002.CR2',
    'C:/Users/DEV/Photos/Mock Roll/IMG_9003.CR2',
  ]
}

export async function pickLut(): Promise<string | null> {
  return 'C:/Users/DEV/Downloads/mock_lut.cube'
}

export async function pickJson(): Promise<string | null> {
  return 'C:/Users/DEV/Downloads/mock_preset.json'
}

export async function pickSavePath(defaultName: string, extension: string): Promise<string | null> {
  return `C:/Users/DEV/Downloads/${defaultName}.${extension}`
}

export async function reveal(_filePath: string): Promise<void> {
  // no-op in the browser mock
}
