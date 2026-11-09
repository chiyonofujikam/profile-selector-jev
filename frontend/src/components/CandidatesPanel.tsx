import { useEffect, useState } from 'react'
import { post } from '../api/client'
import type { Page, ProfileMatch } from '../api/types'
import { errorMessage } from '../hooks/useSearch'
import type { SearchState } from '../hooks/useSearch'
import { Modal } from './Modal'
import { Pagination } from './Pagination'

export function CandidatesPanel({ search }: { search: SearchState }) {
  const [results, setResults] = useState<Page<ProfileMatch> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  const [page, setPage] = useState(1)
  const [profile, setProfile] = useState<ProfileMatch | null>(null)
  const { filters, grouping, categoryGrouping } = search
  // A changed search starts at the first page and closes old profile evidence.
  useEffect(() => {
    setPage(1)
    setProfile(null)
  }, [filters, grouping, categoryGrouping])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    const timer = setTimeout(async () => {
      try {
        const data = await post<Page<ProfileMatch>>('/api/v1/profiles/search', {
          filters, grouping, category_grouping: categoryGrouping, page, page_size: 12,
        }, controller.signal)
        if (!controller.signal.aborted) { setResults(data); setError('') }
      } catch (error) {
        if (!controller.signal.aborted) setError(errorMessage(error))
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }, 250)
    return () => { clearTimeout(timer); controller.abort() }
  }, [filters, grouping, categoryGrouping, page, reload])

  return <section className="panel" aria-labelledby="candidates-title">
    <div className="section-heading">
      <h2 id="candidates-title">3. View matches <span className="count">{error ? '—' : results?.total ?? 0}</span></h2>
      <button disabled={loading} onClick={() => setReload(value => value + 1)}>Refresh candidates</button>
    </div>
    <div aria-live="polite" aria-busy={loading}>
      {loading ? <p className="empty-state">Finding matches…</p>
        : error ? <div className="notice error" role="alert">{error} <button onClick={() => setReload(value => value + 1)}>Retry search</button></div>
        : !results?.items.length ? <div className="empty-state">
          <h3>{filters.length ? 'No matching profiles' : 'No profiles yet'}</h3>
          <p>{filters.length ? 'Try fewer required filters or a different level. Missing profile data stays unknown.' : 'Import candidate profiles using the data setup instructions in README.md.'}</p>
        </div> : <div className="candidate-list">{results.items.map(item => <button className="candidate" key={item.profile.id} onClick={() => setProfile(item)}>
          <div><h3>{item.profile.display_name}</h3><p>{item.profile.title}</p>
            <small>{item.matched.length} matched · {item.unmet.length} unmet · {item.unknown.length} unknown</small></div>
          <span className="match-score">{filters.length ? `${item.score}%` : '—'}<small>match score</small></span>
        </button>)}</div>}
    </div>
    {results && <Pagination page={page} total={results.total} size={results.page_size} onChange={setPage} />}
    {profile && <Modal title={profile.profile.display_name} onClose={() => setProfile(null)}>
      <p>{profile.profile.title}</p><p className="muted">{profile.profile.summary}</p>
      <p className="notice">Match score: {profile.score}% — based on the active filters.</p>
      {(['matched', 'unmet', 'unknown'] as const).map(kind => <section className="evidence-section" key={kind}>
        <h3>{kind[0].toUpperCase() + kind.slice(1)} ({profile[kind].length})</h3>
        {profile[kind].length ? <ul>{profile[kind].map((text, index) => <li key={index}>{text}</li>)}</ul> : <p className="muted">None.</p>}
      </section>)}
    </Modal>}
  </section>
}
