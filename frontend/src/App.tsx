import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertCircle, ArrowRight, ArrowUpRight, Bookmark, Boxes, Check, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, Clock3, Database, Filter, LayoutDashboard, ListFilter, LoaderCircle, Menu, Plus, RefreshCw, Search, Settings2, ShieldCheck, SlidersHorizontal, Sparkles, Trash2, Users, X } from 'lucide-react'
import { api, post } from './api/client'
import type { Analysis, CatalogFilter, Category, Config, Constraint, Health, Page, ProfileMatch, SavedSearch } from './api/types'
import { Modal } from './components/Modal'
import { ResponsePanel } from './components/ResponsePanel'
import { FilterRow } from './components/FilterRow'

type Dialog = 'guide' | 'saved' | 'history' | 'catalog' | 'settings' | 'save' | null
const message = (error: unknown) => error instanceof Error ? error.message : 'Something went wrong. Please retry.'
const stamp = (value: string) => new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
const emptyPage = <T,>(): Page<T> => ({ items: [], total: 0, page: 1, page_size: 20 })

export default function App() {
  const [config, setConfig] = useState<Config | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [categories, setCategories] = useState<Category[]>([])
  const [catalog, setCatalog] = useState<Page<CatalogFilter>>(emptyPage)
  const [catalogCache, setCatalogCache] = useState<Record<string, CatalogFilter>>({})
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogError, setCatalogError] = useState('')
  const [connectionError, setConnectionError] = useState('')
  const [reload, setReload] = useState(0)
  const [stateText, setStateText] = useState('')
  const [locale, setLocale] = useState('en')
  const [constraints, setConstraints] = useState<Constraint[]>([])
  const [grouping, setGrouping] = useState<'and' | 'or'>('and')
  const [categoryGrouping, setCategoryGrouping] = useState<Record<string, 'and' | 'or'>>({})
  const [filterQuery, setFilterQuery] = useState('')
  const [category, setCategory] = useState('all')
  const [catalogPage, setCatalogPage] = useState(1)
  const [onlySelected, setOnlySelected] = useState(false)
  const [revision, setRevision] = useState(0)
  const revisionRef = useRef(0)
  const analysisSequence = useRef(0)
  const pendingRequest = useRef<{ revision: number; id: string } | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisError, setAnalysisError] = useState('')
  const [results, setResults] = useState<Page<ProfileMatch>>(emptyPage)
  const [resultsLoading, setResultsLoading] = useState(true)
  const [resultsError, setResultsError] = useState('')
  const [resultPage, setResultPage] = useState(1)
  const [profile, setProfile] = useState<ProfileMatch | null>(null)
  const [dialog, setDialog] = useState<Dialog>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [saved, setSaved] = useState<Page<SavedSearch>>(emptyPage)
  const [history, setHistory] = useState<Page<Analysis>>(emptyPage)
  const [drawerLoading, setDrawerLoading] = useState(false)
  const [drawerError, setDrawerError] = useState('')
  const [drawerPage, setDrawerPage] = useState(1)
  const [saveName, setSaveName] = useState('')
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState('')
  const markEdit = useCallback(() => { revisionRef.current += 1; setRevision(revisionRef.current) }, [])

  useEffect(() => {
    const controller = new AbortController()
    Promise.allSettled([
      api<Config>('/api/v1/config', { signal: controller.signal }),
      api<Health>('/health', { signal: controller.signal }),
      api<Category[]>('/api/v1/categories', { signal: controller.signal }),
    ]).then(([configuration, status, taxonomy]) => {
      if (controller.signal.aborted) return
      if (configuration.status === 'fulfilled') setConfig(configuration.value)
      if (status.status === 'fulfilled') setHealth(status.value); else setHealth(null)
      if (taxonomy.status === 'fulfilled') { setCategories(taxonomy.value); setConnectionError('') }
      else setConnectionError(message(taxonomy.reason))
    })
    return () => controller.abort()
  }, [reload])

  useEffect(() => {
    const controller = new AbortController()
    setCatalogLoading(true)
    const timer = setTimeout(() => {
      const params = new URLSearchParams({ page: String(catalogPage), page_size: '30' })
      if (filterQuery.trim()) params.set('q', filterQuery.trim())
      if (category !== 'all') params.set('category_id', category)
      api<Page<CatalogFilter>>(`/api/v1/filters?${params}`, { signal: controller.signal }).then(data => {
        if (controller.signal.aborted) return
        setCatalog(data); setCatalogError('')
        setCatalogCache(cache => ({ ...cache, ...Object.fromEntries(data.items.map(f => [f.id, f])) }))
      }).catch(error => { if (!controller.signal.aborted) setCatalogError(message(error)) }).finally(() => { if (!controller.signal.aborted) setCatalogLoading(false) })
    }, 200)
    return () => { clearTimeout(timer); controller.abort() }
  }, [filterQuery, category, catalogPage, reload])

  useEffect(() => {
    const missing = constraints.map(c => c.filter_id).filter(id => !catalogCache[id])
    if (!missing.length) return
    const controller = new AbortController()
    const batches = Array.from({ length: Math.ceil(missing.length / 100) }, (_, i) => missing.slice(i * 100, i * 100 + 100))
    Promise.all(batches.map(ids => api<Page<CatalogFilter>>(`/api/v1/filters?${new URLSearchParams({ ids: ids.join(','), page_size: '100' })}`, { signal: controller.signal }))).then(pages => {
      if (!controller.signal.aborted) setCatalogCache(cache => ({ ...cache, ...Object.fromEntries(pages.flatMap(p => p.items).map(f => [f.id, f])) }))
    }).catch(error => { if (!controller.signal.aborted) setCatalogError(message(error)) })
    return () => controller.abort()
  }, [constraints, catalogCache, reload])

  useEffect(() => {
    const controller = new AbortController()
    setResultsLoading(true)
    const timer = setTimeout(() => post<Page<ProfileMatch>>('/api/v1/profiles/search', { filters: constraints, grouping, category_grouping: categoryGrouping, page: resultPage, page_size: 12 }, controller.signal).then(data => {
      if (controller.signal.aborted) return
      setResults(data); setResultsError('')
    }).catch(error => { if (!controller.signal.aborted) setResultsError(message(error)) }).finally(() => { if (!controller.signal.aborted) setResultsLoading(false) }), 250)
    return () => { clearTimeout(timer); controller.abort() }
  }, [constraints, grouping, categoryGrouping, resultPage, reload])

  useEffect(() => {
    if (dialog !== 'saved' && dialog !== 'history') return
    const controller = new AbortController()
    setDrawerLoading(true); setDrawerError('')
    const task = dialog === 'saved' ? api<Page<SavedSearch>>(`/api/v1/saved-searches?page=${drawerPage}&page_size=20`, { signal: controller.signal }).then(setSaved) : api<Page<Analysis>>(`/api/v1/analyses?page=${drawerPage}&page_size=20`, { signal: controller.signal }).then(setHistory)
    task.catch(error => { if (!controller.signal.aborted) setDrawerError(message(error)) }).finally(() => { if (!controller.signal.aborted) setDrawerLoading(false) })
    return () => controller.abort()
  }, [dialog, drawerPage, reload])

  const openDialog = (value: Dialog) => { setDialog(value); setDrawerPage(1); setDrawerError(''); setSidebarOpen(false) }
  const reset = () => { markEdit(); analysisSequence.current += 1; setAnalyzing(false); setConstraints([]); setStateText(''); setAnalysis(null); setAnalysisError(''); setGrouping('and'); setCategoryGrouping({}); setResultPage(1); setSidebarOpen(false) }
  const updateConstraint = (id: string, update: Partial<Constraint> | null) => {
    markEdit(); setResultPage(1)
    setConstraints(current => update === null ? current.filter(c => c.filter_id !== id) : current.some(c => c.filter_id === id) ? current.map(c => c.filter_id === id ? { ...c, ...update, source: 'manual' } : c) : [...current, { filter_id: id, mode: 'include', requirement: 'mandatory', level_id: null, operator: 'exact', ...update, source: 'manual' }])
  }
  const submit = async () => {
    if (!stateText.trim() || analyzing) return
    const submittedRevision = revisionRef.current
    if (pendingRequest.current?.revision !== submittedRevision) pendingRequest.current = { revision: submittedRevision, id: crypto.randomUUID() }
    const requestId = pendingRequest.current!.id
    const sequence = ++analysisSequence.current
    setAnalyzing(true); setAnalysisError('')
    try {
      const data = await post<Analysis>('/api/v1/analyses', { state_text: stateText, current_filters: constraints, client_revision: submittedRevision, locale, request_id: requestId })
      if (sequence !== analysisSequence.current) return
      pendingRequest.current = null
      setAnalysis(data)
      if (submittedRevision === revisionRef.current) { setConstraints(data.filters); setResultPage(1); setToast('Analysis complete. Filters and candidate results updated.') }
      else setToast('Analysis received. Your newer edits were preserved; submit again to apply an update.')
    } catch (error) { if (sequence === analysisSequence.current) setAnalysisError(message(error)) }
    finally { if (sequence === analysisSequence.current) setAnalyzing(false) }
  }
  const restore = (item: SavedSearch | Analysis) => {
    markEdit(); analysisSequence.current += 1; setAnalyzing(false)
    setStateText('query' in item ? item.query : item.state_text); setConstraints(item.filters); setResultPage(1)
    if ('query' in item) { setGrouping(item.grouping); setCategoryGrouping(item.category_grouping || {}); setAnalysis(null) }
    else { setGrouping('and'); setCategoryGrouping({}); setAnalysis({ ...item, client_revision: revisionRef.current }) }
    setAnalysisError(''); setDialog(null); setToast('Search restored. Candidate results are refreshing.')
  }
  const saveSearch = async () => {
    if (!saveName.trim()) return
    setSaving(true); setDrawerError('')
    try { await post('/api/v1/saved-searches', { label: saveName.trim(), query: stateText, filters: constraints, grouping, category_grouping: categoryGrouping }); setDialog(null); setSaveName(''); setToast('Search saved. Find it in Saved searches.') }
    catch (error) { setDrawerError(message(error)) } finally { setSaving(false) }
  }
  const removeSaved = async (id: string) => {
    try { await api(`/api/v1/saved-searches/${encodeURIComponent(id)}`, { method: 'DELETE' }); setReload(v => v + 1); setToast('Saved search deleted.') } catch (error) { setDrawerError(message(error)) }
  }
  const isLive = config?.provider === 'jev'
  const shownFilters = onlySelected ? Object.values(catalogCache).filter(f => constraints.some(c => c.filter_id === f.id) && (category === 'all' || f.category_id === category) && `${f.label} ${f.description}`.toLocaleLowerCase().includes(filterQuery.toLocaleLowerCase())) : catalog.items
  const totalCatalog = categories.reduce((sum, c) => sum + (c.count || 0), 0)
  const selectedCount = constraints.length
  const stale = !!analysis && analysis.client_revision !== revision
  const retry = () => setReload(value => value + 1)
  const pagination = (page: number, total: number, size: number, update: (page: number) => void) => total > size && <div className="pagination"><span>{(page - 1) * size + 1}–{Math.min(page * size, total)} of {total}</span><div><button className="icon-button" disabled={page <= 1} onClick={() => update(page - 1)} aria-label="Previous page"><ChevronLeft size={17} /></button><span>Page {page}</span><button className="icon-button" disabled={page * size >= total} onClick={() => update(page + 1)} aria-label="Next page"><ChevronRight size={17} /></button></div></div>

  return <div className="app-shell">
    {sidebarOpen && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} />}
    <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
      <a href="#main" className="brand" aria-label="Jev Smart Filter Selector"><span className="brand-icon"><Filter size={23} strokeWidth={2.6} /></span><span>jev<span className="brand-dot">.</span></span><span className="brand-label">SELECTOR</span></a>
      <div className="workspace-switch"><span className="workspace-avatar">E</span><div><strong>Engineering workspace</strong><small>Smart Filter Selector</small></div><ChevronDown size={14} /></div>
      <div className="nav-label">WORKSPACE</div>
      <nav aria-label="Main navigation"><button className="nav-item active" onClick={() => { setDialog(null); setSidebarOpen(false); document.getElementById('main')?.focus() }}><LayoutDashboard size={18} /> Filter dashboard<span className="active-dot" /></button><button className="nav-item" onClick={() => openDialog('saved')}><Bookmark size={18} /> Saved searches</button><button className="nav-item" onClick={() => openDialog('history')}><Clock3 size={18} /> Analysis history</button><button className="nav-item" onClick={() => openDialog('catalog')}><Boxes size={18} /> Filter catalog<span className="nav-count">{totalCatalog}</span></button></nav>
      <div className="sidebar-help"><span className="help-spark"><Sparkles size={19} /></span><h3>From intent to expertise.</h3><p>Let Jev handle the filters.<br />Keep control of the search.</p><button onClick={() => openDialog('guide')}>Explore the workflow <ArrowUpRight size={14} /></button></div>
      <div className="sidebar-bottom"><button className="nav-item" onClick={() => openDialog('guide')}><CircleHelp size={18} /> Getting started</button><button className="nav-item" onClick={() => openDialog('settings')}><Settings2 size={18} /> Connection settings</button><div className="workspace-footer"><span className="footer-avatar">EW</span><div><strong>Engineering workspace</strong><small>Local environment</small></div><span className="online-dot" /></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setSidebarOpen(true)}><Menu size={21} /></button><span>Workspace</span><ChevronRight size={14} /><strong>Filter dashboard</strong></div><div className="topbar-right"><span className={`connection-status ${connectionError ? 'disconnected' : ''}`}><span />{connectionError ? 'Service unavailable' : health ? 'Connected' : 'Connecting'}</span><span className="topbar-divider" /><button className="icon-button" onClick={() => openDialog('guide')} aria-label="Help"><CircleHelp size={19} /></button><span className="user-avatar">EW</span></div></header>
    <main id="main" tabIndex={-1}>
      <div className="page-heading"><div className="eyebrow"><span /> YOUR NEXT EXPERT STARTS HERE</div><div className="heading-row"><div><h1>Find the right expertise<span>.</span></h1><p>Describe what you need. Refine the filters. Discover the people who fit.</p></div><button className="button secondary new-search" onClick={reset}><Plus size={17} /> New search</button></div></div>
      <div className="workflow" aria-label="Search workflow"><div><span className="step-number current">01</span><span><strong>Describe your requirement</strong><small>Start with a state for Jev</small></span></div><ArrowRight size={17} /><div><span className="step-number">02</span><span><strong>Make the filters yours</strong><small>Review, adjust, and set levels</small></span></div><ArrowRight size={17} /><div><span className="step-number">03</span><span><strong>Explore matching candidates</strong><small>See the evidence behind each fit</small></span></div></div>
      {connectionError && <div className="notice error connection-notice" role="alert"><AlertCircle size={18} /><span>{connectionError}</span><button className="text-button" onClick={retry}><RefreshCw size={14} /> Retry connection</button></div>}
      <section className="panel state-panel" aria-labelledby="state-title"><div className="section-heading"><div className="section-title"><span className="section-icon teal"><Sparkles size={19} /></span><div><h2 id="state-title">Start with your requirement</h2><p>A little context goes a long way. Be specific about skills, levels, and exclusions.</p></div></div><span className={`mode-badge ${isLive ? 'live' : ''}`}><span />{config ? isLive ? 'Live Jev' : 'Demo mode' : 'Checking mode'}</span></div>
        <label className="input-label" htmlFor="state-input">State for Jev</label><div className="state-input-wrap"><textarea id="state-input" placeholder="Describe the expertise, tools, and proficiency your project needs…" value={stateText} maxLength={10000} onChange={e => { setStateText(e.target.value); markEdit() }} onKeyDown={e => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); void submit() } }} /><div className="input-meta"><span>Natural language. Structured decisions.</span><span>{stateText.length.toLocaleString()} / 10,000</span></div></div>
        {analysisError && <div className="notice error" role="alert"><AlertCircle size={17} /><span>{analysisError}</span><button className="text-button" disabled={analyzing || !stateText.trim()} onClick={() => void submit()}>Retry</button></div>}
        <div className="state-footer"><div className="state-hint"><ShieldCheck size={16} /><span>You stay in control. Every filter is editable.</span></div><div className="state-actions"><label className="locale-select"><span className="sr-only">State language</span><select value={locale} onChange={e => { setLocale(e.target.value); markEdit() }}><option value="en">English</option><option value="fr">Français</option><option value="es">Español</option></select></label><button className="button primary" disabled={analyzing || !stateText.trim()} onClick={() => void submit()}>{analyzing ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}{analyzing ? 'Updating filters…' : 'Update filters with Jev'}{!analyzing && <span className="shortcut">⌘ ↵</span>}</button></div></div>
      </section>

      <section className="panel filters-panel" aria-labelledby="filter-title"><div className="section-heading"><div className="section-title"><span className="section-icon lavender"><SlidersHorizontal size={19} /></span><div><h2 id="filter-title">Your search filters <span className="count">{selectedCount} active</span></h2><p>Browse the catalog, select requirements, and fine-tune applicable levels.</p></div></div><div className="filter-heading-actions"><button className="text-button muted" disabled={!selectedCount} onClick={() => { markEdit(); setConstraints([]); setResultPage(1) }}>Clear all</button><button className="button secondary small" onClick={() => openDialog('save')} disabled={!stateText.trim() && !selectedCount}><Bookmark size={15} /> Save search</button></div></div>
        <div className="filter-toolbar"><label className="search-input"><Search size={17} /><input placeholder="Search filters, tools, or skills…" aria-label="Search catalog filters" value={filterQuery} onChange={e => { setFilterQuery(e.target.value); setCatalogPage(1) }} />{filterQuery && <button className="icon-button" onClick={() => { setFilterQuery(''); setCatalogPage(1) }} aria-label="Clear catalog search"><X size={14} /></button>}</label><label className="selected-toggle"><input type="checkbox" checked={onlySelected} onChange={e => setOnlySelected(e.target.checked)} />Selected only</label><label className="grouping-select"><ListFilter size={16} /><span className="sr-only">Match grouping</span><select aria-label="Match grouping" value={grouping} onChange={e => { markEdit(); setGrouping(e.target.value as 'and' | 'or'); setResultPage(1) }}><option value="and">Match all requirements</option><option value="or">Match any requirement</option></select></label></div>
        <div className="category-tabs" role="tablist" aria-label="Filter categories"><button role="tab" aria-selected={category === 'all'} onClick={() => { setCategory('all'); setCatalogPage(1) }}>All filters <span>{totalCatalog}</span></button>{categories.map(c => <button key={c.id} role="tab" aria-selected={category === c.id} onClick={() => { setCategory(c.id); setCatalogPage(1) }}>{c.label}<span>{c.count}</span></button>)}</div>
        {category !== 'all' && <div className="category-policy"><label>Within {categories.find(c => c.id === category)?.label || 'this category'}<select value={categoryGrouping[category] || ''} onChange={e => { const value = e.target.value; markEdit(); setResultPage(1); setCategoryGrouping(current => { const next = { ...current }; if (value) next[category] = value as 'and' | 'or'; else delete next[category]; return next }) }}><option value="">Use global grouping</option><option value="and">Require all selected</option><option value="or">Require any selected</option></select></label><span>Exclusions always apply.</span></div>}
        {selectedCount > 0 && <div className="active-filters">{constraints.map(c => <span className={`filter-chip ${c.mode === 'exclude' ? 'excluded' : ''}`} key={c.filter_id}>{c.mode === 'exclude' && 'Exclude: '}{catalogCache[c.filter_id]?.label || c.filter_id}{c.level_id && <span>{c.operator === 'minimum' ? '≥ ' : '= '}{catalogCache[c.filter_id]?.levels.find(l => l.id === c.level_id)?.label || c.level_id}</span>}<button aria-label={`Remove ${catalogCache[c.filter_id]?.label || c.filter_id}`} onClick={() => updateConstraint(c.filter_id, null)}><X size={12} /></button></span>)}</div>}
        {catalogLoading ? <div className="loading-state" role="status"><LoaderCircle size={23} className="spin" />Loading your filter catalog…</div> : catalogError ? <div className="empty-state compact"><span className="empty-icon"><Database size={25} /></span><h3>Let’s connect your catalog</h3><p>{catalogError}</p><div className="empty-actions"><button className="button secondary small" onClick={retry}><RefreshCw size={15} /> Retry</button><button className="text-button" onClick={() => openDialog('guide')}>Setup guide <ArrowUpRight size={14} /></button></div></div> : !shownFilters.length ? <div className="empty-state compact"><span className="catalog-illustration"><span /><span /><span /><Filter size={23} /></span><h3>{filterQuery || onlySelected ? 'No filters to show' : 'A clear starting point'}</h3><p>{filterQuery ? 'Try a different term or browse another category.' : onlySelected ? 'Select filters from the catalog to see them here.' : 'Your catalog is ready for your data. Import reviewed filters to start building a precise search.'}</p>{filterQuery || onlySelected ? <button className="text-button" onClick={() => { setFilterQuery(''); setOnlySelected(false); setCategory('all'); setCatalogPage(1) }}>Show all filters <ArrowRight size={14} /></button> : <button className="text-button" onClick={() => openDialog('guide')}>View data setup <ArrowRight size={14} /></button>}</div> : <div className="filter-list">{shownFilters.map(f => {
          const active = constraints.find(c => c.filter_id === f.id)
          return <FilterRow key={f.id} filter={f} active={active} update={updateConstraint} />
        })}</div>}
        {!onlySelected && pagination(catalogPage, catalog.total, catalog.page_size, setCatalogPage)}<div className="panel-footnote"><span><Check size={14} /> Manual edits refresh candidates automatically</span><span>Levels apply to individual filters</span></div>
      </section>

      <ResponsePanel analysis={analysis} stale={stale} />

      {analysis && !stale && analysis.decisions.some(d => d.status === 'uncertain') && <section className="notice warning uncertainty"><AlertCircle size={19} /><div><strong>A few decisions need your review</strong><p>Uncertain suggestions have not been applied. Inspect them in the response panel and add any relevant filters manually.</p></div></section>}

      <section className="candidates-section" aria-labelledby="candidates-title"><div className="candidates-heading"><div><div className="result-eyebrow">THE PEOPLE BEHIND THE CAPABILITIES</div><h2 id="candidates-title">Matching candidates <span className="count">{resultsError ? '—' : results.total}</span></h2><p>{selectedCount ? `Based on ${selectedCount} active ${selectedCount === 1 ? 'filter' : 'filters'} · ${grouping === 'and' ? 'All required inclusions' : 'Any required inclusion'} · Exclusions always apply` : 'Your candidate matches will appear here as your search takes shape.'}</p></div><button className="button secondary small" onClick={retry} disabled={resultsLoading} aria-label="Refresh candidates"><RefreshCw size={15} className={resultsLoading ? 'spin' : ''} /> Refresh</button></div>
        <div aria-live="polite" aria-busy={resultsLoading}>{resultsLoading ? <div className="panel loading-state"><LoaderCircle size={24} className="spin" />Finding matching candidates…</div> : resultsError ? <div className="panel empty-state"><span className="empty-icon"><Users size={29} /></span><h3>Candidate search is waiting for a connection</h3><p>{resultsError}</p><button className="button secondary small" onClick={retry}><RefreshCw size={14} /> Retry search</button></div> : !results.items.length ? <div className="panel empty-state candidate-empty"><div className="people-illustration" aria-hidden="true"><span className="person small-person"><Users size={20} /></span><span className="person main-person"><Users size={32} /></span><span className="person small-person"><Search size={20} /></span></div><h3>{selectedCount ? 'No candidates match this search yet' : 'The right people, once your data is here'}</h3><p>{selectedCount ? 'Try fewer required filters or adjust the levels. Missing profile information stays unknown rather than being treated as a match.' : 'Import your candidate profiles to bring this workspace to life. Jev will help connect your requirements to the expertise in your catalog.'}</p><button className="button secondary small" onClick={() => selectedCount ? (markEdit(), setConstraints([]), setResultPage(1)) : openDialog('guide')}>{selectedCount ? <><RefreshCw size={15} /> Reset filters</> : <><Database size={15} /> Set up candidate data <ArrowUpRight size={14} /></>}</button><span className="empty-caption"><ShieldCheck size={13} /> Transparent matching. Every requirement accounted for.</span></div> : <div className="candidate-grid">{results.items.map(item => <button className="panel candidate-card" key={item.profile.id} onClick={() => setProfile(item)}><div className="candidate-card-top"><span className="candidate-avatar">{item.profile.display_name.split(' ').map(s => s[0]).slice(0, 2).join('')}</span><span className="match-score">{Number.isInteger(item.score) ? item.score : item.score.toFixed(1)}<small>match score</small></span></div><h3>{item.profile.display_name}</h3><strong className="candidate-title">{item.profile.title}</strong><p>{item.profile.summary}</p><div className="candidate-evidence"><span><Check size={13} /> {item.matched.length} matched</span><span>{item.unmet.length} unmet</span><span>{item.unknown.length} unknown</span></div><div className="candidate-card-bottom"><span>{item.profile.experience_years == null ? 'Experience not provided' : `${item.profile.experience_years} years of experience`}</span><ArrowUpRight size={16} /></div></button>)}</div>}</div>{pagination(resultPage, results.total, results.page_size, setResultPage)}
      </section>
      <footer className="page-footer"><div><span className="mini-brand">jev.</span><span>A little intelligence. A lot more clarity.</span></div><span><span className="online-dot" />{isLive ? 'Powered by TypeSafe Jev' : 'Demo workspace · Your decisions, made visible'}</span></footer>
    </main></div>

    {toast && <div className="toast" role="status"><Check size={18} /><span>{toast}</span><button className="icon-button" onClick={() => setToast('')} aria-label="Dismiss notification"><X size={16} /></button></div>}
    {dialog && <Modal title={{ guide: 'A thoughtful search starts here', saved: 'Saved searches', history: 'Analysis history', catalog: 'Your filter catalog', settings: 'Connection settings', save: 'Save this search' }[dialog]} onClose={() => setDialog(null)} wide={dialog === 'history' || dialog === 'catalog'}>
      {dialog === 'guide' && <div className="guide"><span className="badge badge-green">LOCAL WORKSPACE</span><p className="modal-lead">Turn a requirement into a search you can understand and adjust.</p><ol><li><strong>Connect your data</strong><p>Start PostgreSQL and the API, then import a reviewed catalog and your candidate profiles. This workspace starts empty while your examples are being prepared.</p></li><li><strong>Describe the requirement</strong><p>Write the skills, languages, levels, and exclusions you need. Select a language and choose “Update filters with Jev”. Demo mode uses deterministic rules.</p></li><li><strong>Review and refine</strong><p>Browse filters and edit inclusions, exclusions, and required or preferred status. Choose exact levels or an explicit minimum where supported.</p></li><li><strong>Inspect the evidence</strong><p>Open the response panel to see all returned decisions and probabilities. Candidate details separate matched, unmet, and unknown requirements.</p></li></ol><div className="notice"><Database size={18} /><span>For startup and import commands, see <code>README.md</code> in the project. Candidate examples and demonstration data await your input.</span></div></div>}
      {dialog === 'settings' && <div><p className="modal-lead">Connections are configured in the project’s environment file.</p><dl className="settings-list"><div><dt>Decision mode</dt><dd>{config ? isLive ? 'Live Jev' : 'Demo · deterministic rules' : 'Unavailable'}</dd></div><div><dt>Model</dt><dd>{config?.model || 'Unavailable'}</dd></div><div><dt>API</dt><dd>{import.meta.env.VITE_API_URL || 'Same origin · Vite development proxy'}</dd></div><div><dt>Application health</dt><dd>{health?.status || 'Unavailable'}</dd></div><div><dt>PostgreSQL</dt><dd>{health ? JSON.stringify(health.database) : 'Unavailable'}</dd></div><div><dt>Provider readiness</dt><dd>{health ? JSON.stringify(health.provider) : 'Unavailable'}</dd></div></dl><div className="notice"><ShieldCheck size={18} /><span>TypeSafe credentials belong on the backend. The browser receives only public configuration.</span></div><button className="button secondary" onClick={retry}><RefreshCw size={16} /> Check connections again</button></div>}
      {dialog === 'catalog' && <div><p className="modal-lead">A closed catalog keeps every selection traceable.</p><div className="catalog-stats"><div><strong>{totalCatalog}</strong><span>reviewed filters</span></div><div><strong>{categories.length}</strong><span>categories</span></div><div><strong>{selectedCount}</strong><span>active selections</span></div></div>{categories.length ? <div className="catalog-categories">{categories.map(c => <button key={c.id} onClick={() => { setCategory(c.id); setCatalogPage(1); setDialog(null); document.getElementById('filter-title')?.scrollIntoView({ behavior: 'smooth' }) }}><Boxes size={18} /><span>{c.label}<small>{c.key}</small></span><span>{c.count} filters</span><ChevronRight size={17} /></button>)}</div> : <div className="notice"><Database size={18} /><span>No reviewed catalog has been imported. The legacy taxonomy can be converted for review with the project’s import tools.</span></div>}<p className="muted">Levels are attached to specific filters. Catalog relationships do not imply that a candidate possesses another competency.</p></div>}
      {dialog === 'save' && <form onSubmit={e => { e.preventDefault(); void saveSearch() }}><p className="modal-lead">Keep your requirement and all {selectedCount} active filters together.</p><label className="input-label" htmlFor="save-name">Search name</label><input id="save-name" className="text-input" value={saveName} onChange={e => setSaveName(e.target.value)} placeholder="Give this search a name" maxLength={160} autoFocus required /><p className="muted">Saved searches include filter levels, inclusions, exclusions, and match grouping.</p>{drawerError && <div className="notice error" role="alert">{drawerError}</div>}<div className="modal-actions"><button className="button secondary" type="button" onClick={() => setDialog(null)}>Cancel</button><button className="button primary" disabled={saving || !saveName.trim()}>{saving ? <LoaderCircle className="spin" size={16} /> : <Bookmark size={16} />}Save search</button></div></form>}
      {(dialog === 'saved' || dialog === 'history') && <div>{drawerLoading ? <div className="loading-state"><LoaderCircle className="spin" size={23} />Loading…</div> : drawerError ? <div className="notice error" role="alert">{drawerError}<button className="text-button" onClick={retry}>Retry</button></div> : dialog === 'saved' ? saved.items.length ? <div className="saved-list">{saved.items.map(item => <div className="saved-item" key={item.id}><button onClick={() => restore(item)}><Bookmark size={18} /><span><strong>{item.label}</strong><p>{item.query || 'Manual filter search'}</p><small>{item.filters.length} filters · {stamp(item.created_at)}</small></span><ArrowUpRight size={18} /></button><button className="icon-button" aria-label={`Delete ${item.label}`} onClick={() => void removeSaved(item.id)}><Trash2 size={17} /></button></div>)}</div> : <div className="empty-state"><span className="empty-icon"><Bookmark size={26} /></span><h3>Make a good search easy to find</h3><p>Save a requirement and its filters from the dashboard. They’ll be waiting here next time.</p></div> : history.items.length ? <div className="saved-list">{history.items.map(item => <div className="saved-item" key={item.id}><button onClick={() => restore(item)}><Clock3 size={18} /><span><strong>{item.state_text}</strong><small>{item.provider === 'mock' ? 'Demo' : 'Live Jev'} · {item.decisions.length} decisions · {stamp(item.created_at)}</small></span><ArrowUpRight size={18} /></button></div>)}</div> : <div className="empty-state"><span className="empty-icon"><Clock3 size={26} /></span><h3>Your search, with a paper trail</h3><p>Completed analyses will appear here with their original state, decisions, and provider response.</p></div>}{pagination(drawerPage, dialog === 'saved' ? saved.total : history.total, 20, setDrawerPage)}</div>}
    </Modal>}
    {profile && <Modal title={profile.profile.display_name} onClose={() => setProfile(null)}><p className="modal-lead">{profile.profile.title}</p><p>{profile.profile.summary}</p><div className="notice">Match score: <strong>{profile.score}</strong> · A ranking score based on your active requirements.</div>{(['matched', 'unmet', 'unknown'] as const).map(kind => <section className="evidence-section" key={kind}><h3>{kind[0].toUpperCase() + kind.slice(1)} requirements <span className="count">{profile[kind].length}</span></h3>{profile[kind].length ? <ul>{profile[kind].map((text, i) => <li key={i}>{text}</li>)}</ul> : <p className="muted">None recorded for this search.</p>}</section>)}</Modal>}
  </div>
}
