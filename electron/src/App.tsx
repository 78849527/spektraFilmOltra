import { useCallback, useEffect, useState } from 'react'
import { errorMessage, request } from './api'
import type { Bootstrap, HandoffInfo, ItemRecord, LibrarySnapshot } from './types'
import { LibraryPage } from './pages/LibraryPage'
import { EditorPage } from './pages/EditorPage'
import { GradePage } from './pages/GradePage'

type Route =
  | { kind: 'library' }
  | { kind: 'editor'; item: ItemRecord }
  | { kind: 'grade'; item: ItemRecord; handoff: HandoffInfo }

interface ToastState {
  message: string
  error: boolean
}

export default function App() {
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null)
  const [library, setLibrary] = useState<LibrarySnapshot | null>(null)
  const [route, setRoute] = useState<Route>({ kind: 'library' })
  const [toast, setToast] = useState<ToastState | null>(null)
  const [bootError, setBootError] = useState<string | null>(null)

  const notify = useCallback((message: string, error = false) => {
    setToast({ message, error })
  }, [])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 3000)
    return () => window.clearTimeout(timer)
  }, [toast])

  const refreshLibrary = useCallback(async () => {
    const snapshot = await request<LibrarySnapshot>('GET', '/v1/library')
    setLibrary(snapshot)
    return snapshot
  }, [])

  useEffect(() => {
    let cancelled = false
    async function boot() {
      try {
        const [bootPayload, libraryPayload] = await Promise.all([
          request<Bootstrap>('GET', '/v1/bootstrap'),
          request<LibrarySnapshot>('GET', '/v1/library'),
        ])
        if (cancelled) return
        setBootstrap(bootPayload)
        setLibrary(libraryPayload)
      } catch (error) {
        if (!cancelled) setBootError(errorMessage(error))
      }
    }
    void boot()
    return () => {
      cancelled = true
    }
  }, [])

  if (!bootstrap || !library) {
    return (
      <div className="app-shell">
        <div className="boot">
          <div className="boot-mark" />
          <div className="boot-text">SPEKTRAFILM</div>
          {bootError ? (
            <div className="caption" style={{ maxWidth: 520, textAlign: 'center', color: 'var(--danger)' }}>
              {bootError}
            </div>
          ) : null}
        </div>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <div className="titlebar">
        <span className="titlebar-mark">Spektrafilm</span>
      </div>

      {route.kind === 'library' ? (
        <LibraryPage
          bootstrap={bootstrap}
          library={library}
          onRefresh={refreshLibrary}
          onNotify={notify}
          onOpen={(item) => setRoute({ kind: 'editor', item })}
        />
      ) : null}

      {route.kind === 'editor' ? (
        <EditorPage
          key={route.item.id}
          bootstrap={bootstrap}
          library={library}
          item={route.item}
          onBack={() => {
            setRoute({ kind: 'library' })
            void refreshLibrary()
          }}
          onGrade={(handoff) => setRoute({ kind: 'grade', item: route.item, handoff })}
          onSwitchItem={(item) => setRoute({ kind: 'editor', item })}
          onNotify={notify}
        />
      ) : null}

      {route.kind === 'grade' ? (
        <GradePage
          key={`${route.item.id}-grade`}
          bootstrap={bootstrap}
          item={route.item}
          handoff={route.handoff}
          onBack={async () => {
            const snapshot = await refreshLibrary()
            const fresh = snapshot.items.find((entry) => entry.id === route.item.id) ?? route.item
            setRoute({ kind: 'editor', item: fresh })
          }}
          onNotify={notify}
        />
      ) : null}

      {toast ? <div className={`toast${toast.error ? ' error' : ''}`}>{toast.message}</div> : null}
    </div>
  )
}
