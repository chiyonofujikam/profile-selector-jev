import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { CatalogFilter, Category, Page } from '../api/types'
import { errorMessage } from '../hooks/useSearch'
import type { SearchState } from '../hooks/useSearch'
import { FilterRow } from './FilterRow'
import { Pagination } from './Pagination'

export function FiltersPanel({ search }: { search: SearchState }) {
  const [open, setOpen] = useState(false)
  const [categories, setCategories] = useState<Category[]>([])
  const [catalog, setCatalog] = useState<Page<CatalogFilter> | null>(null)
  const [cache, setCache] = useState<Record<string, CatalogFilter | null>>({})
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [page, setPage] = useState(1)
  const [selectedOnly, setSelectedOnly] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)

  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    api<Category[]>('/api/v1/categories', { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setCategories(data) })
      .catch(error => { if (!controller.signal.aborted) setError(errorMessage(error)) })
    return () => controller.abort()
  }, [open, reload])

  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    setLoading(true)
    const timer = setTimeout(async () => {
      const params = new URLSearchParams({ page: String(page), page_size: '30' })
      if (query.trim()) params.set('q', query.trim())
      if (category) params.set('category_id', category)
      try {
        const data = await api<Page<CatalogFilter>>(`/api/v1/filters?${params}`, { signal: controller.signal })
        if (controller.signal.aborted) return
        setCatalog(data)
        setCache(current => ({ ...current, ...Object.fromEntries(data.items.map(item => [item.id, item])) }))
        setError('')
      } catch (error) {
        if (!controller.signal.aborted) setError(errorMessage(error))
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }, 200)
    return () => { clearTimeout(timer); controller.abort() }
  }, [open, query, category, page, reload])

  // Jev and restored searches can select filters outside the current catalog page.
  useEffect(() => {
    if (!open) return
    const missing = search.filters.map(filter => filter.filter_id).filter(id => !(id in cache))
    if (!missing.length) return
    const controller = new AbortController()
    async function loadSelected() {
      try {
        const items: CatalogFilter[] = []
        for (let index = 0; index < missing.length; index += 100) {
          const params = new URLSearchParams({ ids: missing.slice(index, index + 100).join(','), page_size: '100' })
          const data = await api<Page<CatalogFilter>>(`/api/v1/filters?${params}`, { signal: controller.signal })
          items.push(...data.items)
        }
        if (!controller.signal.aborted) {
          // Remember unavailable IDs too, so old saved filters cannot cause a fetch loop.
          setCache(current => ({
            ...Object.fromEntries(missing.map(id => [id, null])), ...current,
            ...Object.fromEntries(items.map(item => [item.id, item])),
          }))
        }
      } catch (error) {
        if (!controller.signal.aborted) setError(errorMessage(error))
      }
    }
    void loadSelected()
    return () => controller.abort()
  }, [open, search.filters, cache, reload])

  const shown = selectedOnly ? Object.values(cache).filter((item): item is CatalogFilter => item !== null).filter(item =>
    search.filters.some(filter => filter.filter_id === item.id)
    && (!category || item.category_id === category)
    && [item.label, item.description, ...item.aliases].join(' ').toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
  ) : catalog?.items || []

  return <section className="panel" aria-labelledby="filters-title">
    <div className="section-heading filter-heading">
      <h2 id="filters-title">2. Review filters <span className="count">{search.filters.length} active</span></h2>
      <button aria-expanded={open} aria-controls="filter-content" onClick={() => setOpen(value => !value)}>
        {open ? 'Hide filters' : 'Show filters'}
      </button>
    </div>
    {open && <div id="filter-content" className="filter-content">
    <div className="filter-toolbar">
      <input aria-label="Search catalog filters" placeholder="Search skills or tools" maxLength={240}
        value={query} onChange={event => { setQuery(event.target.value); setPage(1) }} />
      <select aria-label="Filter category" value={category} onChange={event => { setCategory(event.target.value); setPage(1) }}>
        <option value="">All categories</option>
        {categories.map(item => <option key={item.id} value={item.id}>{item.label} ({item.count})</option>)}
      </select>
      <label><input type="checkbox" checked={selectedOnly} onChange={event => setSelectedOnly(event.target.checked)} /> Selected only</label>
      <button disabled={!search.filters.length} onClick={search.clearFilters}>Clear all</button>
    </div>
    <div className="filter-toolbar">
      <label>Required filters
        <select aria-label="Match grouping" value={search.grouping} onChange={event => search.setGrouping(event.target.value as 'and' | 'or')}>
          <option value="and">Match all</option><option value="or">Match any</option>
        </select>
      </label>
      {category && <label>Within this category
        <select value={search.categoryGrouping[category] || ''} onChange={event => {
          const next = { ...search.categoryGrouping }
          if (event.target.value) next[category] = event.target.value as 'and' | 'or'
          else delete next[category]
          search.setCategoryGrouping(next)
        }}>
          <option value="">Use overall setting</option><option value="and">Match all</option><option value="or">Match any</option>
        </select>
      </label>}
      <small>Exclusions always apply. Preferred filters affect ranking.</small>
    </div>
    {search.filters.some(filter => cache[filter.filter_id] === null) && <div className="notice warning">
      <p>Some selected filters are no longer available. Remove them below to continue searching.</p>
      {search.filters.filter(filter => cache[filter.filter_id] === null).map(filter => <button className="filter-chip" key={filter.filter_id}
        aria-label={`Remove ${cache[filter.filter_id]?.label || filter.filter_id}`}
        onClick={() => search.updateFilter(filter.filter_id, null)}>
        {filter.mode === 'exclude' && 'Exclude: '}{cache[filter.filter_id]?.label || filter.filter_id} ×
      </button>)}
    </div>}
    {loading ? <p className="empty-state" role="status">Loading filters…</p>
      : error ? <div className="notice error" role="alert">{error} <button onClick={() => setReload(value => value + 1)}>Retry catalog</button></div>
      : shown.length ? <div className="filters-table-scroll" role="region" aria-label="Scrollable search filters" tabIndex={0}>
        <table className="filters-table" aria-label="Search filters">
          <thead><tr><th scope="col">Selected</th><th scope="col">Filter</th><th scope="col">Mode</th>
            <th scope="col">Requirement</th><th scope="col">Level</th><th scope="col">Comparison</th></tr></thead>
          <tbody>{shown.map(item => <FilterRow key={item.id} filter={item}
            active={search.filters.find(filter => filter.filter_id === item.id)} update={search.updateFilter} />)}</tbody>
        </table>
      </div>
      : <div className="empty-state"><h3>{selectedOnly && !search.filters.length ? 'No selected filters' : query || category || selectedOnly ? 'No filters found' : 'No filters yet'}</h3>
        <p>{selectedOnly && !search.filters.length ? 'Submit a requirement or browse the catalog to select filters.' : query || category || selectedOnly ? 'Try another search or browse the catalog.' : 'Import a reviewed catalog to start. See the data setup instructions in README.md.'}</p>
        {(query || category || selectedOnly) && <button onClick={() => { setQuery(''); setCategory(''); setSelectedOnly(false); setPage(1) }}>Browse catalog</button>}
      </div>}
    {!selectedOnly && catalog && <Pagination page={page} total={catalog.total} size={catalog.page_size} onChange={setPage} />}
    <p className="muted footnote">Manual edits refresh matches automatically. Levels apply to each filter individually.</p>
    </div>}
  </section>
}
