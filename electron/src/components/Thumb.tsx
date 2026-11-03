import { useEffect, useState } from 'react'
import { mediaUrl, request } from '../api'
import type { ItemRecord } from '../types'

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

  if (!url) {
    return <div className={`thumb-placeholder ${className ?? ''}`} />
  }
  return <img className={className} src={url} alt={item.name} draggable={false} />
}
