import type { StateTree } from './types'

export function cloneTree<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

export function readPath(root: unknown, path: string): unknown {
  let node: unknown = root
  for (const part of path.split('.')) {
    if (typeof node !== 'object' || node === null) return undefined
    node = (node as Record<string, unknown>)[part]
  }
  return node
}

export function writePath(root: StateTree, path: string, value: unknown): StateTree {
  const next = cloneTree(root)
  const parts = path.split('.')
  let node: Record<string, unknown> = next
  for (const part of parts.slice(0, -1)) {
    const child = node[part]
    if (typeof child !== 'object' || child === null) {
      node[part] = {}
    }
    node = node[part] as Record<string, unknown>
  }
  node[parts[parts.length - 1]] = value
  return next
}

export function setNumber(root: StateTree, path: string, value: number): StateTree {
  return writePath(root, path, value)
}

export function setBoolean(root: StateTree, path: string, value: boolean): StateTree {
  return writePath(root, path, value)
}

export function setString(root: StateTree, path: string, value: string): StateTree {
  return writePath(root, path, value)
}

export function selectionOf(state: StateTree): { film: string; paper: string } {
  const simulation = state.simulation as Record<string, unknown> | undefined
  return {
    film: String(simulation?.film_stock ?? ''),
    paper: String(simulation?.print_paper ?? ''),
  }
}

export function photoAspect(width: number, height: number): number {
  if (!width || !height) return 4 / 3
  return width / height
}

export function formatSize(width: number, height: number): string {
  if (!width || !height) return '—'
  return `${width} × ${height}`
}

export function formatBytes(bytes: number): string {
  if (!bytes) return '—'
  if (bytes > 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${Math.round(bytes / 1024)} KB`
}
