import { useEffect, useState } from 'react'
import { api } from './api'
import type { Config, Health } from './types'
import { CandidatesPanel } from './components/CandidatesPanel'
import { FiltersPanel } from './components/FiltersPanel'
import { ResponsePanel } from './components/ResponsePanel'
import { SearchLibrary } from './components/SearchLibrary'
import type { LibraryView } from './components/SearchLibrary'
import { useSearch } from './useSearch'
import { errorMessage } from './messages'

export default function App() {
  const search = useSearch()
  const [config, setConfig] = useState<Config | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [connectionError, setConnectionError] = useState('')
  const [reload, setReload] = useState(0)
  const [library, setLibrary] = useState<LibraryView | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      api<Config>('/api/v1/config', { signal: controller.signal }),
      api<Health>('/health', { signal: controller.signal }),
    ]).then(([configuration, status]) => {
      if (controller.signal.aborted) return
      setConfig(configuration)
      setHealth(status)
      setConnectionError('')
    }).catch(error => {
      if (!controller.signal.aborted) setConnectionError(errorMessage(error))
    })
    return () => controller.abort()
  }, [reload])

  const maxLength = config?.max_state_length || 12000
  return <div>
    <header className="app-header">
      <a className="brand" href="#main">Profile Selector<span> / Decision model</span></a>
      <nav aria-label="Search tools">
        <button onClick={() => setLibrary('saved')}>Saved searches</button>
        <button onClick={() => setLibrary('history')}>Analysis history</button>
        <button onClick={search.reset}>New search</button>
      </nav>
    </header>
    <main id="main">
      <div className="page-heading"><h1>Find the right expertise</h1>
        <p>Describe what you need, review the filters, and explore matching profiles.</p></div>
      {connectionError && <div className="notice error" role="alert">{connectionError}
        <button onClick={() => setReload(value => value + 1)}>Retry connection</button></div>}
      {health?.status === 'degraded' && <div className="notice warning" role="status">
        {!health.database.ready ? 'Database is not ready. Start PostgreSQL and apply migrations.' : 'The Decision model is not configured. Check the backend TypeSafe API key.'}
        <button onClick={() => setReload(value => value + 1)}>Check again</button>
      </div>}
      <section className="panel" aria-labelledby="requirement-title">
        <div className="section-heading"><h2 id="requirement-title">1. Describe your requirement</h2>
          <span className="badge">{config ? config.provider === 'jev' ? 'Live Decision model' : 'Demo mode' : 'Connecting…'}</span></div>
        <label className="field" htmlFor="state-input">State</label>
        <textarea id="state-input" placeholder="Which skills, languages, and levels do you need? What should be excluded?"
          maxLength={maxLength} value={search.text} onChange={event => search.setText(event.target.value)}
          onKeyDown={event => {
            if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
              event.preventDefault()
              void search.submit()
            }
          }} />
        <div className="state-actions">
          <small>{search.text.length.toLocaleString()} / {maxLength.toLocaleString()}</small>
          <label><span className="sr-only">State language</span>
            <select value={search.locale} onChange={event => search.setLocale(event.target.value)}>
              <option value="en">English</option><option value="fr">Français</option><option value="es">Español</option>
            </select>
          </label>
          <button className="primary" disabled={search.analyzing || !search.text.trim()} onClick={() => void search.submit()}>
            {search.analyzing ? 'Updating filters…' : 'Update filters'}
          </button>
        </div>
        {config?.provider === 'mock' && <p className="muted footnote">Demo mode matches catalog names and aliases using local rules.</p>}
        {search.error && <div className="notice error" role="alert">{search.error}
          <button disabled={search.analyzing} onClick={() => void search.submit()}>Retry</button></div>}
        {search.notice && <p className="notice" role="status">{search.notice}</p>}
      </section>
      <FiltersPanel search={search} />
      <div className="search-actions"><button disabled={!search.text.trim() && !search.filters.length} onClick={() => setLibrary('save')}>Save search</button></div>
      <ResponsePanel analysis={search.analysis} stale={search.stale} />
      {search.analysis && !search.stale && search.analysis.decisions.some(decision => decision.status === 'uncertain') &&
        <p className="notice warning">Some decisions need review. Uncertain suggestions were not applied; inspect the response and adjust filters manually.</p>}
      <CandidatesPanel search={search} />
      <footer>The Decision model suggests filters. You control the search.</footer>
    </main>
    {library && <SearchLibrary key={library} view={library} search={search} onClose={() => setLibrary(null)} />}
  </div>
}
