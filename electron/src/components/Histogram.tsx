import { useEffect, useRef } from 'react'

const BINS = 64

export function Histogram({ src }: { src: string | null }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!src) return
    let active = true
    const image = new Image()
    image.crossOrigin = 'anonymous'
    image.onload = () => {
      if (!active) return
      try {
        drawHistogram(image, canvasRef.current)
      } catch (error) {
        window.spektra?.logError(`[histogram] ${String(error)}`)
      }
    }
    image.src = src
    return () => {
      active = false
    }
  }, [src])

  return (
    <div className="histogram">
      <canvas ref={canvasRef} />
    </div>
  )
}

function drawHistogram(image: HTMLImageElement, canvas: HTMLCanvasElement | null): void {
  if (!canvas) return
  const sample = document.createElement('canvas')
  sample.width = 200
  sample.height = Math.max(1, Math.round((image.height / image.width) * 200))
  const sampleCtx = sample.getContext('2d')
  if (!sampleCtx) return
  sampleCtx.drawImage(image, 0, 0, sample.width, sample.height)
  const { data } = sampleCtx.getImageData(0, 0, sample.width, sample.height)

  const red = new Array<number>(BINS).fill(0)
  const green = new Array<number>(BINS).fill(0)
  const blue = new Array<number>(BINS).fill(0)
  for (let index = 0; index < data.length; index += 4) {
    red[Math.min(BINS - 1, Math.floor((data[index] / 256) * BINS))] += 1
    green[Math.min(BINS - 1, Math.floor((data[index + 1] / 256) * BINS))] += 1
    blue[Math.min(BINS - 1, Math.floor((data[index + 2] / 256) * BINS))] += 1
  }

  const peak = Math.max(...red, ...green, ...blue, 1)
  const dpr = window.devicePixelRatio || 1
  const width = canvas.clientWidth
  const height = canvas.clientHeight
  canvas.width = Math.round(width * dpr)
  canvas.height = Math.round(height * dpr)
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.scale(dpr, dpr)

  const channels: Array<[number[], string]> = [
    [red, 'rgba(192, 112, 94, 0.55)'],
    [green, 'rgba(126, 155, 119, 0.5)'],
    [blue, 'rgba(109, 139, 167, 0.55)'],
  ]
  for (const [bins, color] of channels) {
    ctx.beginPath()
    ctx.moveTo(0, height)
    for (let index = 0; index < BINS; index += 1) {
      const x = (index / (BINS - 1)) * width
      const y = height - Math.min(1, bins[index] / peak) * (height - 4)
      ctx.lineTo(x, y)
    }
    ctx.lineTo(width, height)
    ctx.closePath()
    ctx.fillStyle = color
    ctx.fill()
  }
}
