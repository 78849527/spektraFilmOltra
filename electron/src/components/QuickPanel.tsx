import { useRef } from 'react'
import type { QuickAxisSpec, QuickGroup, QuickItem } from '../types'
import { SwitchRow, ValueRow } from './Controls'

function formatAxis(axis: QuickAxisSpec, value: number): string {
  const text = axis.decimals > 0 ? value.toFixed(axis.decimals) : String(Math.round(value))
  const signed = axis.lo < 0 && value > 0 ? `+${text}` : text
  return `${signed}${axis.suffix}`
}

function PadControl({
  item,
  intents,
  disabled,
  onChange,
  onCommit,
}: {
  item: Extract<QuickItem, { kind: 'pad' }>
  intents: Record<string, number>
  disabled: boolean
  onChange: (axis: string, value: number) => void
  onCommit: (axis: string, value: number) => void
}) {
  const areaRef = useRef<HTMLDivElement>(null)
  const [horizontal, vertical] = item.axes
  const xValue = intents[horizontal.id] ?? 0
  const yValue = intents[vertical.id] ?? 0

  function applyFromEvent(clientX: number, clientY: number, commit: boolean) {
    const area = areaRef.current
    if (!area) return
    const rect = area.getBoundingClientRect()
    const nx = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    const ny = Math.max(0, Math.min(1, (clientY - rect.top) / rect.height))
    const qx = horizontal.lo + nx * (horizontal.hi - horizontal.lo)
    const qy = vertical.hi - ny * (vertical.hi - vertical.lo)
    onChange(horizontal.id, Math.round(qx / horizontal.step) * horizontal.step)
    onChange(vertical.id, Math.round(qy / vertical.step) * vertical.step)
    if (commit) {
      onCommit(horizontal.id, Math.round(qx / horizontal.step) * horizontal.step)
      onCommit(vertical.id, Math.round(qy / vertical.step) * vertical.step)
    }
  }

  const px = horizontal.hi > horizontal.lo ? ((xValue - horizontal.lo) / (horizontal.hi - horizontal.lo)) * 100 : 50
  const py = vertical.hi > vertical.lo ? ((vertical.hi - yValue) / (vertical.hi - vertical.lo)) * 100 : 50

  return (
    <div className={`pad${disabled ? ' disabled' : ''}`} style={disabled ? { opacity: 0.4, pointerEvents: 'none' } : undefined}>
      <div className="pad-title">
        <span>{item.title}</span>
        <span className="meta">
          {formatAxis(horizontal, xValue)} / {formatAxis(vertical, yValue)}
        </span>
      </div>
      <div
        ref={areaRef}
        className="pad-area"
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId)
          applyFromEvent(event.clientX, event.clientY, false)
        }}
        onPointerMove={(event) => {
          if (event.buttons !== 1) return
          applyFromEvent(event.clientX, event.clientY, false)
        }}
        onPointerUp={(event) => {
          applyFromEvent(event.clientX, event.clientY, true)
        }}
      >
        <span className="pad-axis-label" style={{ top: 4, left: '50%', transform: 'translateX(-50%)' }}>
          品红
        </span>
        <span className="pad-axis-label" style={{ bottom: 4, left: '50%', transform: 'translateX(-50%)' }}>
          绿
        </span>
        <span className="pad-axis-label" style={{ left: 5, top: '50%', transform: 'translateY(-50%)' }}>
          暖
        </span>
        <span className="pad-axis-label" style={{ right: 5, top: '50%', transform: 'translateY(-50%)' }}>
          冷
        </span>
        <span className="pad-dot" style={{ left: `${px}%`, top: `${py}%` }} />
      </div>
    </div>
  )
}

export function QuickPanel({
  layout,
  intents,
  disabled,
  onChange,
  onCommit,
  borderOn,
  onBorderChange,
}: {
  layout: QuickGroup[]
  intents: Record<string, number>
  disabled: string[]
  onChange: (axis: string, value: number) => void
  onCommit: (axis: string, value: number) => void
  borderOn: boolean
  onBorderChange: (value: boolean) => void
}) {
  const isDisabled = (id: string) => disabled.includes(id)

  return (
    <div>
      {layout.map((group) => (
        <div className="quick-group" key={group.title}>
          <div className="quick-group-title">{group.title}</div>
          {group.items.map((item, index) => {
            if (item.kind === 'pad') {
              const anyDisabled = item.axes.some((axis) => isDisabled(axis.id))
              return (
                <PadControl
                  key={`pad-${index}`}
                  item={item}
                  intents={intents}
                  disabled={anyDisabled}
                  onChange={onChange}
                  onCommit={onCommit}
                />
              )
            }
            const axis = item.axis
            return (
              <ValueRow
                key={axis.id}
                label={axis.label}
                value={intents[axis.id] ?? 0}
                min={axis.lo}
                max={axis.hi}
                step={axis.step}
                decimals={axis.decimals}
                suffix={axis.suffix}
                disabled={isDisabled(axis.id)}
                tooltip={isDisabled(axis.id) ? '正片扫描模式：管线跳过印相阶段，本项不参与成像' : axis.tooltip}
                onChange={(value) => onChange(axis.id, value)}
                onReset={() => onCommit(axis.id, 0)}
              />
            )
          })}
        </div>
      ))}

      <div className="quick-group">
        <div className="quick-group-title">边框</div>
        <SwitchRow
          label="预览边框"
          checked={borderOn}
          onChange={onBorderChange}
          hint="只影响显影台预览白边，不写入成片；宽度由专业页的白边比例控制"
        />
      </div>
    </div>
  )
}