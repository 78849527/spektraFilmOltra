export interface ProfileEntry {
  id: string
  name: string
  display_name: string
  type: string
  support: string
  kind: string
  target_print: string | null
}

export interface QuickAxisSpec {
  id: string
  label: string
  lo: number
  hi: number
  step: number
  decimals: number
  suffix: string
  tooltip: string
}

export type QuickItem =
  | { kind: 'axis'; axis: QuickAxisSpec }
  | { kind: 'pad'; title: string; axes: [QuickAxisSpec, QuickAxisSpec]; full_scale: number }

export interface QuickGroup {
  title: string
  items: QuickItem[]
}

export interface QuickPayload {
  intents: Record<string, number>
  axes: Record<string, { lo: number; hi: number; step: number; decimals: number; suffix: string }>
  disabled: string[]
}

export interface Bootstrap {
  films: ProfileEntry[]
  papers: ProfileEntry[]
  quick_layout: QuickGroup[]
  options: {
    color_spaces: string[]
    rgb_to_raw_methods: string[]
    raw_white_balance: string[]
    auto_exposure_methods: string[]
    diffusion_families: string[]
    input_gamut_compress: string[]
    output_gamut_compress: string[]
    illuminants: string[]
  }
  state: StateTree
  export_settings: ExportSettings
  grade_recipe: Recipe
}

export type StateTree = Record<string, unknown>

export interface FolderRecord {
  id: string
  name: string
  path: string
  added_at: number
}

export interface ItemRecord {
  id: string
  path: string
  name: string
  folder_id: string
  added_at: number
  favorite: boolean
  color: string
  adjusted: boolean
  film_stock: string
  print_paper: string
  width: number
  height: number
  is_raw: boolean
  file_size: number
  mtime: number
  state: StateTree | null
}

export interface LibrarySnapshot {
  folders: FolderRecord[]
  items: ItemRecord[]
  folder_count: number
  item_count: number
  inbox_id: string
}

export interface ExportSettings {
  format: string
  jpeg_quality: number
  png_compression: number
  tiff_compression: string
  exr_compression: string
  bit_depth: number
  long_edge: number
  directory: string
  filename_template: string
}

export interface JobStatus {
  id: string
  kind: string
  state: 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
  progress: { label: string; index: number; total: number }
  result: Record<string, unknown> | null
  error: string | null
}

export interface OpenedPhoto {
  photo_id: string
  path: string
  width: number
  height: number
  is_raw: boolean
  color_space: string
  cctf_decoding: boolean
  lens_summary: string
  original_preview: string
  display_preview: string
  state: StateTree
}

export interface Recipe {
  light: Record<string, number>
  color: {
    temperature: number
    tint: number
    vibrance: number
    saturation: number
    hue_shift: number
    color_density: number
    hsl: Array<{ hue: number; saturation: number; luminance: number }>
    grading: Record<string, unknown>
  }
  transparency: { tonal: number; color: number }
  quality: Record<string, number>
  optics: Record<string, number>
  lut: { path: string; strength: number }
}

export interface PresetEntry {
  id: string
  name: string
  recipe: Recipe
  builtin: boolean
}
