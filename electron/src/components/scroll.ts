import { useEffect, useRef, useState, type RefObject } from 'react'

/* 阻尼系数：每帧吃掉剩余距离的一部分，形成非线性缓出 */
const DAMPING = 0.18

/**
 * 给滚动容器加上阻尼感滚轮：接管 wheel 事件，把 scrollTop/scrollLeft
 * 缓动到目标值，形成非线性滑动。滚动条本身全局隐藏。
 */
export function useSmoothScroll<T extends HTMLElement>(axis: 'y' | 'x' | 'auto' = 'y') {
  const ref = useRef<T | null>(null)

  useEffect(() => {
    const element = ref.current
    if (!element) return

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let targetX = element.scrollLeft
    let targetY = element.scrollTop
    let raf = 0
    let running = false

    const maxY = () => Math.max(0, element.scrollHeight - element.clientHeight)
    const maxX = () => Math.max(0, element.scrollWidth - element.clientWidth)
    const clamp = (value: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, value))

    const tick = () => {
      const dx = targetX - element.scrollLeft
      const dy = targetY - element.scrollTop
      if (Math.abs(dx) < 0.4 && Math.abs(dy) < 0.4) {
        element.scrollLeft = Math.round(targetX)
        element.scrollTop = Math.round(targetY)
        running = false
        return
      }
      element.scrollLeft += dx * DAMPING
      element.scrollTop += dy * DAMPING
      raf = window.requestAnimationFrame(tick)
    }

    const onWheel = (event: WheelEvent) => {
      if (event.ctrlKey) return
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? element.clientHeight : 1
      const dx = event.deltaX * unit
      const dy = event.deltaY * unit
      const limitY = maxY()
      const limitX = maxX()
      const horizontalIntent = axis === 'x' || (axis === 'auto' && Math.abs(dx) > Math.abs(dy))

      if (horizontalIntent && limitX > 1) {
        targetX = clamp(targetX + (Math.abs(dx) > Math.abs(dy) ? dx : dy), 0, limitX)
      } else if (limitY > 1) {
        targetY = clamp(targetY + dy, 0, limitY)
        if (Math.abs(dx) > 0.5 && limitX > 1) targetX = clamp(targetX + dx, 0, limitX)
      } else if (limitX > 1) {
        targetX = clamp(targetX + dy, 0, limitX)
      } else {
        return
      }

      event.preventDefault()

      if (reduce) {
        element.scrollLeft = targetX
        element.scrollTop = targetY
        return
      }
      if (!running) {
        running = true
        raf = window.requestAnimationFrame(tick)
      }
    }

    element.addEventListener('wheel', onWheel, { passive: false })
    return () => {
      element.removeEventListener('wheel', onWheel)
      window.cancelAnimationFrame(raf)
    }
  }, [axis])

  return ref
}

/** 容器尺寸变化监听（缩放匹配、画布自适应都靠它） */
export function useElementSize<T extends HTMLElement>(ref: RefObject<T | null>) {
  const [size, setSize] = useState({ width: 0, height: 0 })

  useEffect(() => {
    const element = ref.current
    if (!element) return
    const observer = new ResizeObserver(() => {
      setSize({ width: element.clientWidth, height: element.clientHeight })
    })
    observer.observe(element)
    setSize({ width: element.clientWidth, height: element.clientHeight })
    return () => observer.disconnect()
  }, [ref])

  return size
}