import type { SVGProps } from 'react'

const paths: Record<string, string[]> = {
  chevronLeft: ['M9.5 3.5 4.5 8l5 4.5'],
  chevronDown: ['M3.5 6.5 7 10l3.5-3.5'],
  chevronRight: ['M6.5 3.5 11.5 8l-5 4.5'],
  star: ['m8 2.6 1.65 3.35 3.7.54-2.68 2.6.63 3.68L8 11.03l-3.3 1.74.63-3.68-2.68-2.6 3.7-.54z'],
  starFill: ['m8 2.6 1.65 3.35 3.7.54-2.68 2.6.63 3.68L8 11.03l-3.3 1.74.63-3.68-2.68-2.6 3.7-.54z', 'fill'],
  sliders: ['M3 5h4M9 5h4M3 11h7M12 11h1', 'M7 3v4M10 9v4'],
  search: ['M7.2 2.8a4.4 4.4 0 1 0 0 8.8 4.4 4.4 0 0 0 0-8.8z', 'M10.5 10.5 13.5 13.5'],
  grid: ['M2.5 2.5h4v4h-4zM9.5 2.5h4v4h-4zM2.5 9.5h4v4h-4zM9.5 9.5h4v4h-4z'],
  list: ['M2.5 4h11M2.5 8h11M2.5 12h11'],
  folder: ['M2.5 4.5h4l1.3 1.6h5.7v7h-11z'],
  camera: ['M2.2 5.2h3.1l1-1.4h3.4l1 1.4h3.1v7.6H2.2z', 'M8 9.8a2.4 2.4 0 1 0 0-4.8 2.4 2.4 0 0 0 0 4.8z'],
  image: ['M2.5 3.5h11v9h-11z', 'M2.5 10.5 6 7.5l2.5 2.2 2.2-2 2.8 2.8', 'M10.6 6.2h.01'],
  rotateLeft: ['M3 8a5 5 0 1 0 1.6-3.7', 'M2.4 2.6 3 8l4.2-1.2'],
  rotateRight: ['M13 8a5 5 0 1 1-1.6-3.7', 'M13.6 2.6 13 8l-4.2-1.2'],
  expand: ['M2.5 6.5v-4h4M9.5 2.5h4v4M13.5 9.5v4h-4M6.5 13.5h-4v-4'],
  compare: ['M2.5 3.5h11v9h-11z', 'M8 3.5v9', 'M5.5 6.5h1M5.5 9.5h1M9.5 6.5h1M9.5 9.5h1'],
  upload: ['M8 11V3.5', 'M5 6.5 8 3.5l3 3', 'M2.5 12.5h11'],
  plus: ['M8 3v10M3 8h10'],
  check: ['M3.5 8.5 6.5 11.5 12.5 4.5'],
  close: ['M4 4l8 8M12 4l-8 8'],
  caretDown: ['M4.5 6.5 8 10l3.5-3.5'],
  importArrow: ['M8 3.5v8', 'M5 6 8 3.5l3 3.5', 'M2.5 12.5h11'],
  dot: ['M8 8h.01'],
  border: ['M2.5 2.5h11v11h-11z', 'M5.2 5.2h5.6v5.6h-5.6z'],
  frame: ['M2.5 2.5h11v11h-11z', 'M5 5h6v6h-6z', 'M2.5 5h11M2.5 11h11M5 2.5v11M11 2.5v11'],
}

interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'name'> {
  name: keyof typeof paths | string
  size?: number
}

export function Icon({ name, size = 16, ...rest }: IconProps) {
  const entries = paths[name] ?? paths.dot
  const filled = entries[1] === 'fill'
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke={filled ? 'none' : 'currentColor'}
      strokeWidth={1.4}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...rest}
    >
      {filled ? (
        <path d={entries[0]} fill="currentColor" />
      ) : (
        entries.map((d, index) => <path key={index} d={d} />)
      )}
    </svg>
  )
}

/* 胶片条：所有胶片共用同一几何，只换描边色来区分 */
export function FilmGlyph({
  size = 30,
  tint,
  ...rest
}: { size?: number; tint?: string } & Omit<SVGProps<SVGSVGElement>, 'color'>) {
  const holes = [1.9, 4.1, 6.3, 8.5, 10.7, 12.9]
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke={tint ?? 'currentColor'}
      strokeWidth={1}
      strokeLinejoin="round"
      {...rest}
    >
      <rect x="4.1" y="0.8" width="7.8" height="14.4" rx="1.3" />
      <rect x="6.3" y="1.9" width="3.4" height="12.2" rx="0.4" opacity="0.5" />
      {holes.map((y) => (
        <g key={y}>
          <rect x="4.9" y={y} width="1" height="1.2" rx="0.3" />
          <rect x="10.1" y={y} width="1" height="1.2" rx="0.3" />
        </g>
      ))}
    </svg>
  )
}

/* 相纸：同样的方框、同样的线宽，用中性色调区分 */
export function PaperGlyph({
  size = 30,
  tint,
  ...rest
}: { size?: number; tint?: string } & Omit<SVGProps<SVGSVGElement>, 'color'>) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke={tint ?? 'currentColor'}
      strokeWidth={1}
      strokeLinejoin="round"
      {...rest}
    >
      <path d="M4 1.2h5.2L13 4.9v9.1a0.8 0.8 0 0 1-0.8 0.8H4a0.8 0.8 0 0 1-0.8-0.8V2a0.8 0.8 0 0 1 0.8-0.8z" />
      <path d="M9.2 1.2v3.7h3.8" opacity="0.7" />
      <path d="M5.6 8.6h4.8M5.6 10.8h4.8" opacity="0.45" />
    </svg>
  )
}
