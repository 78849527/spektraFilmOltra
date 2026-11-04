import { useMemo, useRef } from 'react'

export interface CurvePoint {
  x: number
  y: number
}

export const DEFAULT_CURVE_POINTS: CurvePoint[] = [
  { x: 0, y: 0 },
  { x: 0.25, y: 0.25 },
  { x: 0.5, y: 0.5 },
  { x: 0.75, y: 0.75 },
  { x: 1, y: 1 },
]

const W = 260
const H = 210
const PAD = 14
const PLOT_W = W - PAD * 2
const PLOT_H = H - PAD * 2
const MIN_GAP = 0.04

function clamp(value: number, low: number, high: number): number {
  return Math.max(low, Math.min(high, value))
}

function px(x: number): number {
  return PAD + x * PLOT_W
}

function py(y: number): number {
  return PAD + (1 - y) * PLOT_H
}

function sortPoints(points: CurvePoint[]): CurvePoint[] {
  return [...points].sort((a, b) => a.x - b.x)
}

/* Catmull-Rom 样条：控制点之间平滑过渡，端点复制补位防翘曲 */
function samplePath(points: CurvePoint[]): string {
  const sorted = sortPoints(points)
  if (sorted.length < 2) return ''
  const ring = [sorted[0], ...sorted, sorted[sorted.length - 1]]
  const cmds: string[] = []
  for (let i = 0; i < sorted.length - 1; i += 1) {
    const p0 = ring[i]
    const p1 = ring[i + 1]
    const p2 = ring[i + 2]
    const p3 = ring[i + 3]
    const steps = 14
    for (let s = 0; s < steps; s += 1) {
      const t = s / steps
      const t2 = t * t
      const t3 = t2 * t
      const x = 0.5 * (2 * p1.x + (-p0.x + p2.x) * t + (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * t2 + (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * t3)
      const y = 0.5 * (2 * p1.y + (-p0.y + p2.y) * t + (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * t2 + (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * t3)
      const cx = clamp(px(x), PAD, PAD + PLOT_W)
      const cy = clamp(py(y), PAD, PAD + PLOT_H)
      cmds.push(`${cmds.length === 0 ? 'M' : 'L'}${cx.toFixed(2)},${cy.toFixed(2)}`)
    }
  }
  const last = sorted[sorted.length - 1]
  cmds.push(`L${px(last.x).toFixed(2)},${py(last.y).toFixed(2)}`)
  return cmds.join(' ')
}

export function CurveEditor({
  points,
  onChange,
}: {
  points: CurvePoint[]
  onChange: (points: CurvePoint[]) => void
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const dragRef = useRef<number | null>(null)
  const workRef = useRef<CurvePoint[] | null>(null)
  const sorted = useMemo(() => sortPoints(points), [points])
  const path = useMemo(() => samplePath(points), [points])

  function toPlot(clientX: number, clientY: number): CurvePoint | null {
    const svg = svgRef.current
    if (!svg) return null
    const rect = svg.getBoundingClientRect()
    if (rect.width <= 0) return null
    const scale = rect.width / W
    const x = clamp(((clientX - rect.left) / scale - PAD) / PLOT_W, 0, 1)
    const y = clamp(1 - ((clientY - rect.top) / scale - PAD) / PLOT_H, 0, 1)
    return { x, y }
  }

  /* 拖拽约束：端点 x 固定只动 y；中间点 x 夹在相邻点之间 */
  function dragTo(base: CurvePoint[], index: number, point: CurvePoint): CurvePoint[] {
    const next = [...base]
    const isEnd = index === 0 || index === base.length - 1
    const lo = index === 0 ? 0 : base[index - 1].x + MIN_GAP
    const hi = index === base.length - 1 ? 1 : base[index + 1].x - MIN_GAP
    next[index] = {
      x: isEnd ? base[index].x : clamp(point.x, lo, hi),
      y: clamp(point.y, 0, 1),
    }
    return next
  }

  function insertPoint(point: CurvePoint): { points: CurvePoint[]; index: number } {
    const next = sortPoints(points)
    if (next.some((p) => Math.abs(p.x - point.x) < MIN_GAP / 2 && Math.abs(p.y - point.y) < 0.06)) {
      return { points: next, index: -1 }
    }
    let index = next.findIndex((p) => p.x > point.x)
    if (index < 0) index = next.length
    next.splice(index, 0, point)
    return { points: next, index }
  }

  function onPointerDown(event: React.PointerEvent<SVGSVGElement>) {
    const point = toPlot(event.clientX, event.clientY)
    if (!point) return
    const target = event.target as Element
    const raw = target.getAttribute?.('data-index')
    event.currentTarget.setPointerCapture(event.pointerId)
    if (raw !== null && raw !== undefined && raw !== '') {
      workRef.current = sortPoints(points)
      dragRef.current = Number(raw)
      return
    }
    /* 点击曲线区空白：新增控制点并立即进入拖拽 */
    const inserted = insertPoint(point)
    workRef.current = inserted.points
    dragRef.current = inserted.index >= 0 ? inserted.index : null
    if (inserted.index >= 0) onChange(inserted.points)
  }

  function onPointerMove(event: React.PointerEvent<SVGSVGElement>) {
    const index = dragRef.current
    const base = workRef.current
    if (index === null || !base) return
    const point = toPlot(event.clientX, event.clientY)
    if (!point) return
    const next = dragTo(base, index, point)
    workRef.current = next
    onChange(next)
  }

  function onPointerUp(event: React.PointerEvent<SVGSVGElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    dragRef.current = null
    workRef.current = null
  }

  function removePoint(index: number) {
    const base = sortPoints(points)
    /* 端点不可删，至少保留两个点 */
    if (base.length <= 2 || index === 0 || index === base.length - 1) return
    onChange(base.filter((_, i) => i !== index))
  }

  const gridLines = [0.25, 0.5, 0.75]

  return (
    <div className="curve-editor">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="曲线"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <rect className="curve-plot" x={PAD} y={PAD} width={PLOT_W} height={PLOT_H} rx={4} />
        {gridLines.map((g) => (
          <line key={`h${g}`} className="curve-grid" x1={PAD} y1={py(g)} x2={PAD + PLOT_W} y2={py(g)} />
        ))}
        {gridLines.map((g) => (
          <line key={`v${g}`} className="curve-grid" x1={px(g)} y1={PAD} x2={px(g)} y2={PAD + PLOT_H} />
        ))}
        <line className="curve-grid" x1={px(0)} y1={py(0)} x2={px(1)} y2={py(1)} />
        <path className="curve-line" d={path} />
        {sorted.map((point, index) => (
          <circle
            key={index}
            className="curve-handle"
            data-index={index}
            cx={px(point.x)}
            cy={py(point.y)}
            r={5}
            onDoubleClick={() => removePoint(index)}
          />
        ))}
      </svg>
      <div className="curve-foot">
        <span className="curve-hint">单击曲线加点 · 双击控制点删除</span>
        <button type="button" className="curve-reset" onClick={() => onChange(DEFAULT_CURVE_POINTS)}>
          复位
        </button>
      </div>
    </div>
  )
}
