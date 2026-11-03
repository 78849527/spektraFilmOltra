import { useMemo, useState } from 'react'
import { errorMessage, pickFolder, pickImages, request } from '../api'
import { Button, Chip, IconButton, SearchField } from '../components/Controls'
import { Icon } from '../components/Icons'
import { Thumb } from '../components/Thumb'
import { formatSize, photoAspect } from '../state'
import type { Bootstrap, ItemRecord, LibrarySnapshot } from '../types'
import './pages.css'

type Filter = 'all' | 'raw' | 'adjusted' | 'favorite' | 'red' | 'yellow' | 'green' | 'blue'
type SortKey = 'name' | 'date' | 'size'
type ViewMode = 'grid' | 'list'

const FILTERS: Array<{ value: Filter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'raw', label: 'RAW' },
  { value: 'adjusted', label: '已调整' },
  { value: 'favorite', label: '收藏' },
  { value: 'red', label: '红' },
  { value: 'yellow', label: '黄' },
  { value: 'green', label: '绿' },
  { value: 'blue', label: '蓝' },
]

const COLOR_VALUES: Record<string, string> = {
  red: 'var(--label-red)',
  yellow: 'var(--label-yellow)',
  green: 'var(--label-green)',
  blue: 'var(--label-blue)',
}

function matchesFilter(item: ItemRecord, filter: Filter): boolean {
  if (filter === 'all') return true
  if (filter === 'raw') return item.is_raw
  if (filter === 'adjusted') return item.adjusted
  if (filter === 'favorite') return item.favorite
  return item.color === filter
}

export function LibraryPage({
  library,
  onRefresh,
  onNotify,
  onOpen,
}: {
  bootstrap: Bootstrap
  library: LibrarySnapshot
  onRefresh: () => Promise<LibrarySnapshot>
  onNotify: (message: string, error?: boolean) => void
  onOpen: (item: ItemRecord) => void
}) {
  const [filter, setFilter] = useState<Filter>('all')
  const [folderId, setFolderId] = useState<string>('all')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<SortKey>('name')
  const [view, setView] = useState<ViewMode>('grid')

  const folders = library.folders.filter((folder) => folder.id !== library.inbox_id)

  const items = useMemo(() => {
    const filtered = library.items.filter((item) => {
      if (folderId !== 'all' && item.folder_id !== folderId) return false
      if (!matchesFilter(item, filter)) return false
      if (search.trim() && !item.name.toLowerCase().includes(search.trim().toLowerCase())) return false
      return true
    })
    filtered.sort((left, right) => {
      if (sort === 'date') return right.added_at - left.added_at
      if (sort === 'size') return right.file_size - left.file_size
      return left.name.localeCompare(right.name, 'zh-Hans-CN')
    })
    return filtered
  }, [library.items, filter, folderId, search, sort])

  async function importFolder() {
    try {
      const path = await pickFolder()
      if (!path) return
      await request('POST', '/v1/library/scan', { path })
      await onRefresh()
      onNotify('文件夹已导入')
    } catch (error) {
      onNotify(errorMessage(error), true)
    }
  }

  async function importPhotos() {
    try {
      const paths = await pickImages()
      if (!paths.length) return
      await request('POST', '/v1/library/photos', { paths })
      await onRefresh()
      onNotify(`已导入 ${paths.length} 张照片`)
    } catch (error) {
      onNotify(errorMessage(error), true)
    }
  }

  return (
    <div className="page library-page">
      <header className="library-header">
        <div className="stack">
          <h1 className="page-title">照片库</h1>
          <span className="caption">
            {library.item_count} 张照片 · {folders.length} 个文件夹
          </span>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <Button icon="folder" kind="secondary" onClick={importFolder}>
            导入文件夹
          </Button>
          <Button icon="importArrow" kind="primary" onClick={importPhotos}>
            导入照片
          </Button>
        </div>
      </header>

      <div className="library-toolbar">
        <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
          {FILTERS.map((entry) => (
            <Chip key={entry.value} active={filter === entry.value} onClick={() => setFilter(entry.value)}>
              {entry.value === 'red' || entry.value === 'yellow' || entry.value === 'green' || entry.value === 'blue' ? (
                <span className="color-dot" style={{ background: COLOR_VALUES[entry.value] }} />
              ) : null}
              {entry.label}
            </Chip>
          ))}
        </div>
        <span className="grow" />
        <SearchField value={search} onChange={setSearch} placeholder="搜索文件名" />
        <select className="select" value={sort} onChange={(event) => setSort(event.target.value as SortKey)}>
          <option value="name">按名称</option>
          <option value="date">按导入时间</option>
          <option value="size">按文件大小</option>
        </select>
        <div className="view-toggle">
          <IconButton name="grid" label="网格" active={view === 'grid'} onClick={() => setView('grid')} />
          <IconButton name="list" label="列表" active={view === 'list'} onClick={() => setView('list')} />
        </div>
      </div>

      {folders.length > 0 ? (
        <div className="folder-row">
          <button
            className={`folder-chip${folderId === 'all' ? ' active' : ''}`}
            onClick={() => setFolderId('all')}
          >
            全部文件夹
          </button>
          {folders.map((folder) => (
            <button
              key={folder.id}
              className={`folder-chip${folderId === folder.id ? ' active' : ''}`}
              onClick={() => setFolderId(folder.id)}
            >
              <Icon name="folder" size={12} />
              {folder.name}
            </button>
          ))}
        </div>
      ) : null}

      {items.length === 0 ? (
        <div className="empty-state">
          <Icon name="image" size={28} />
          <div className="section-title">还没有照片</div>
          <div className="caption">导入一个文件夹，或直接选择 RAW 文件。</div>
          <Button icon="folder" kind="secondary" onClick={importFolder}>
            导入文件夹
          </Button>
        </div>
      ) : (
        <div className={`library-content ${view}`}>
          {view === 'grid' ? (
            <div className="photo-grid">
              {items.map((item) => (
                <button key={item.id} className="photo-card" onClick={() => onOpen(item)}>
                  <div className="photo-card-media" style={{ aspectRatio: photoAspect(item.width, item.height) }}>
                    <Thumb item={item} className="photo-card-image" />
                    <div className="photo-card-top">
                      {item.is_raw ? <span className="badge">RAW</span> : null}
                      {item.adjusted ? <span className="badge badge-accent">已调整</span> : null}
                      {item.color ? (
                        <span className="color-dot" style={{ background: COLOR_VALUES[item.color] }} />
                      ) : null}
                    </div>
                    {item.favorite ? (
                      <div className="photo-card-favorite">
                        <Icon name="starFill" size={12} />
                      </div>
                    ) : null}
                  </div>
                  <div className="photo-card-body">
                    <div className="photo-card-name truncate">{item.name}</div>
                    <div className="meta truncate">
                      {formatSize(item.width, item.height)}
                      {item.film_stock ? ` · ${item.film_stock}` : ''}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="photo-list">
              {items.map((item) => (
                <button key={item.id} className="photo-row" onClick={() => onOpen(item)}>
                  <Thumb item={item} className="photo-row-image" />
                  <div className="grow stack" style={{ minWidth: 0 }}>
                    <div className="row" style={{ gap: 6 }}>
                      <span className="photo-card-name truncate">{item.name}</span>
                      {item.is_raw ? <span className="badge">RAW</span> : null}
                      {item.adjusted ? <span className="badge badge-accent">已调整</span> : null}
                    </div>
                    <div className="meta truncate">
                      {formatSize(item.width, item.height)}
                      {item.film_stock ? ` · ${item.film_stock}` : ''}
                      {item.print_paper ? ` · ${item.print_paper}` : ''}
                    </div>
                  </div>
                  {item.color ? <span className="color-dot" style={{ background: COLOR_VALUES[item.color] }} /> : null}
                  {item.favorite ? <Icon name="starFill" size={12} style={{ color: 'var(--accent)' }} /> : null}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
