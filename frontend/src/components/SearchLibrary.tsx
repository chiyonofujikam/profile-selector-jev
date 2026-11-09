import { useEffect, useState } from 'react'
import { api, post } from '../api'
import type { Analysis, Page, SavedSearch } from '../types'
import { errorMessage } from '../messages'
import type { SearchState } from '../useSearch'
import { Modal } from './Modal'
import { Pagination } from './Pagination'

export type LibraryView = 'save' | 'saved' | 'history'

export function SearchLibrary({ view, search, onClose }: {
  view: LibraryView; search: SearchState; onClose: () => void
}) {
  const [name, setName] = useState('')
  const [items, setItems] = useState<(SavedSearch | Analysis)[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(view !== 'save')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  const title = { save: 'Save search', saved: 'Saved searches', history: 'Analysis history' }[view]

  useEffect(() => {
    if (view === 'save') return
    const controller = new AbortController()
    setLoading(true)
    setError('')
    const path = view === 'saved' ? 'saved-searches' : 'analyses'
    api<Page<SavedSearch | Analysis>>(`/api/v1/${path}?page=${page}&page_size=20`, { signal: controller.signal })
      .then(data => {
        if (!controller.signal.aborted) { setItems(data.items); setTotal(data.total) }
      })
      .catch(error => { if (!controller.signal.aborted) setError(errorMessage(error)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [view, page, reload])

  async function save() {
    setSaving(true)
    setError('')
    try {
      await post('/api/v1/saved-searches', {
        label: name.trim(), query: search.text, filters: search.filters,
        grouping: search.grouping, category_grouping: search.categoryGrouping,
      })
      onClose()
    } catch (error) { setError(errorMessage(error)) }
    finally { setSaving(false) }
  }

  async function remove(id: string) {
    setError('')
    try {
      await api(`/api/v1/saved-searches/${encodeURIComponent(id)}`, { method: 'DELETE' })
      if (items.length === 1 && page > 1) setPage(page - 1)
      else setReload(value => value + 1)
    } catch (error) { setError(errorMessage(error)) }
  }

  return <Modal title={title} onClose={onClose}>
    {error && <div className="notice error" role="alert">{error}
      {view !== 'save' && <button onClick={() => setReload(value => value + 1)}>Retry</button>}
    </div>}
    {view === 'save' ? <form onSubmit={event => { event.preventDefault(); void save() }}>
      <label className="field" htmlFor="search-name">Search name</label>
      <input id="search-name" value={name} onChange={event => setName(event.target.value)} maxLength={240} required autoFocus />
      <p className="muted footnote">Saves your requirement, filters, levels, and match settings.</p>
      <div className="modal-actions"><button type="button" onClick={onClose}>Cancel</button>
        <button className="primary" disabled={saving || !name.trim()}>{saving ? 'Saving…' : 'Save search'}</button></div>
    </form> : loading ? <p role="status">Loading…</p> : <>
      {!items.length && !error && <p className="empty-state">{view === 'saved' ? 'No saved searches yet.' : 'No analyses yet.'}</p>}
      <div>{items.map(item => <div className="saved-item" key={item.id}>
        <button onClick={() => { search.restore(item); onClose() }}>
          <strong>{'label' in item ? item.label : item.state_text}</strong>
          <small>{item.filters.length} filters · {new Date(item.created_at).toLocaleString()}</small>
        </button>
        {'label' in item && <button aria-label={`Delete ${item.label}`} onClick={() => void remove(item.id)}>Delete</button>}
      </div>)}</div>
      <Pagination page={page} total={total} size={20} onChange={setPage} />
    </>}
  </Modal>
}
