import { useEffect, useState } from 'react'
import { mediaUrl, request } from '../api'
import type { ItemRecord } from '../types'

/** 缩略图统一输出的长宽比：4:3 */
export const THUMB_RATIO = 4 / 3

/**
 * 统一 4:3 缩略图的两种填充策略：
 * - 横屏（比 4:3 更宽）→ 直接裁切，保住画面主体
 * - 竖屏（比 4:3 更窄）→ 主图按高度完整显示，左右两侧用同图模糊铺满
 */
export function thumbMode(width: number, height: number): 'crop' | 'blur' {
  if (!width || !height) return 'crop'
  return width / height >= THUMB_RATIO ? 'crop' : 'blur'
}

export function Thumb({ item, className }: { item: ItemRecord; className?: string }) {
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    request<{ path: string }>('POST', '/v1/library/thumb', { id: item.id })
      .then((payload) => {
        if (active) setUrl(mediaUrl(payload.path))
      })
      .catch(() => undefined)
    return () => {
      active = false
    }
  }, [item.id, item.mtime])

  const mode = thumbMode(item.width, item.height)

  return (
    <div className={`thumb${className ? ` ${className}` : ''}`}>
      {mode === 'blur' && url ? (
        <div className="thumb-fill" style={{ backgroundImage: `url("${url}")` }} />
      ) : null}
      {url ? (
        <img
          className={`thumb-image${mode === 'blur' ? ' contain' : ''}`}
          src={url}
          alt={item.name}
          draggable={false}
        />
      ) : null}
    </div>
  )
}