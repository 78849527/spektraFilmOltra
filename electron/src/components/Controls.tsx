import type { ReactNode } from 'react'
import { Icon } from './Icons'
import './controls.css'

type ButtonKind = 'primary' | 'secondary' | 'quiet'

export function Button({
  children,
  kind = 'secondary',
  icon,
  disabled,
  onClick,
  height,
}: {
  children?: ReactNode
  kind?: ButtonKind
  icon?: string
  disabled?: boolean
  onClick?: () => void
  height?: number
}) {
  return (
    <button
      className={`button button-${kind}`}
      disabled={disabled}
      onClick={onClick}
      style={height ? { height } : undefined}
    >
      {icon ? <Icon name={icon} size={13} /> : null}
      {children}
    </button>
  )
}

export function IconButton({
  name,
  label,
  active,
  onClick,
  size = 14,
}: {
  name: string
  label: string
  active?: boolean
  onClick?: () => void
  size?: number
}) {
  return (
    <button className={`icon-button${active ? ' active' : ''}`} title={label} onClick={onClick}>
      <Icon name={name} size={size} />
    </button>
  )
}

export function Chip({
  children,
  active,
  onClick,
}: {
  children: ReactNode
  active?: boolean
  onClick?: () => void
}) {
  return (
    <button className={`chip${active ? ' active' : ''}`} onClick={onClick}>
      {children}
    </button>
  )
}

export function Toggle({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <button className={`toggle${checked ? ' on' : ''}`} onClick={() => onChange(!checked)}>
      <span className="toggle-knob" />
    </button>
  )
}

export function SwitchRow({
  label,
  checked,
  onChange,
  hint,
}: {
  label: string
  checked: boolean
  onChange: (value: boolean) => void
  hint?: string
}) {
  return (
    <div className="switch-row" title={hint}>
      <span className="switch-row-label">{label}</span>
      <span className="grow" />
      <Toggle checked={checked} onChange={onChange} />
    </div>
  )
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: Array<{ value: T; label: string }>
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div className="segmented">
      {options.map((option) => (
        <button
          key={option.value}
          className={`segmented-item${option.value === value ? ' active' : ''}`}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function SearchField({
  value,
  onChange,
  placeholder,
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
}) {
  return (
    <label className="search-field">
      <Icon name="search" size={13} />
      <input
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  )
}

export function Slider({
  value,
  min,
  max,
  step,
  onChange,
  onCommit,
}: {
  value: number
  min: number
  max: number
  step: number
  onChange: (value: number) => void
  onCommit?: () => void
}) {
  const ratio = max > min ? (value - min) / (max - min) : 0
  return (
    <input
      className="slider"
      type="range"
      min={min}
      max={max}
      step={step}
      value={value}
      style={{ ['--fill' as string]: `${Math.max(0, Math.min(1, ratio)) * 100}%` }}
      onChange={(event) => onChange(Number(event.target.value))}
      onMouseUp={onCommit}
      onKeyUp={onCommit}
    />
  )
}

export function ValueRow({
  label,
  value,
  min,
  max,
  step,
  decimals = 0,
  suffix = '',
  disabled,
  tooltip,
  onChange,
  onReset,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  decimals?: number
  suffix?: string
  disabled?: boolean
  tooltip?: string
  onChange: (value: number) => void
  onReset?: () => void
}) {
  const text = `${decimals > 0 ? value.toFixed(decimals) : Math.round(value)}${suffix}`
  return (
    <div className={`value-row${disabled ? ' disabled' : ''}`} title={tooltip}>
      <div className="value-row-head">
        <span className="value-row-label">{label}</span>
        <span className="value-row-readout num" onDoubleClick={onReset}>
          {text}
        </span>
      </div>
      <Slider value={value} min={min} max={max} step={step} onChange={onChange} />
    </div>
  )
}

export function FieldRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="field-row" title={label}>
      <span className="field-row-label">{label}</span>
      <div className="field-row-control">{children}</div>
    </div>
  )
}

export function Select({
  value,
  options,
  onChange,
  disabled,
  borderless,
}: {
  value: string
  options: Array<{ value: string; label: string }>
  onChange: (value: string) => void
  disabled?: boolean
  borderless?: boolean
}) {
  return (
    <select
      className={`select${borderless ? ' borderless' : ''}`}
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  )
}

export function Disclosure({
  title,
  open,
  onToggle,
  children,
  badge,
}: {
  title: string
  open: boolean
  onToggle: () => void
  children: ReactNode
  badge?: string
}) {
  return (
    <div className="disclosure">
      <button className="disclosure-head" onClick={onToggle}>
        <Icon name="chevronDown" size={12} className={open ? 'chevron open' : 'chevron'} />
        <span className="disclosure-title">{title}</span>
        {badge ? <span className="badge badge-accent">{badge}</span> : null}
        <span className="grow" />
      </button>
      <div className={`disclosure-body${open ? ' open' : ''}`}>
        <div className="disclosure-inner">
          <div>{children}</div>
        </div>
      </div>
    </div>
  )
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  variant = 'underline',
}: {
  tabs: Array<{ value: T; label: string }>
  value: T
  onChange: (value: T) => void
  variant?: 'underline' | 'segmented'
}) {
  if (variant === 'segmented') {
    return <Segmented options={tabs} value={value} onChange={onChange} />
  }
  return (
    <div className="tabs">
      {tabs.map((tab) => (
        <button
          key={tab.value}
          className={`tab${tab.value === value ? ' active' : ''}`}
          onClick={() => onChange(tab.value)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
