import { useState } from 'react'
import { ChevronDown, Code2, Download, Sparkles } from 'lucide-react'
import type { Analysis } from '../api/types'

const percent = (value: number | null | undefined) => value == null ? 'Unavailable' : `${(value * 100).toFixed(1)}%`
export function ResponsePanel({ analysis, stale }: { analysis: Analysis | null; stale: boolean }) {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<'decisions' | 'json'>('decisions')
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(analysis, null, 2)], { type: 'application/json' }))
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `jev-analysis-${analysis!.id}.json`; anchor.click(); URL.revokeObjectURL(url)
  }
  return <section className="panel response-panel">
    <button className="response-toggle" onClick={() => setOpen(v => !v)} aria-expanded={open} aria-controls="jev-response">
      <span className="response-title"><span className="small-icon"><Code2 size={18} /></span><span>Behind the filters <span className="muted response-subtitle">Jev response & decisions</span></span></span>
      <span className="response-end">{analysis && <span className={`badge ${stale ? 'badge-amber' : ''}`}>{stale ? 'Out of date' : `${analysis.decisions.length} decisions`}</span>}<span>{open ? 'Hide response' : 'Show response'}</span><ChevronDown size={16} className={open ? 'rotated' : ''} /></span>
    </button>
    {open && <div id="jev-response" className="response-content">{!analysis ? <div className="inline-empty"><Sparkles size={23} /><div><strong>No analysis yet</strong><p>Submit a state to inspect every decision and the full provider response here.</p></div></div> : <>
      {stale && <div className="notice warning">Your state or filters changed after this analysis. Submit again to update the response. Your current filters are preserved.</div>}
      {analysis.provider === 'mock' && <div className="notice">Demo decisions use deterministic rules. Heuristic values in the raw response are not Jev probabilities.</div>}
      <div className="analysis-meta"><span>Provider <strong>{analysis.provider === 'mock' ? 'Demo' : 'Live Jev'}</strong></span><span>Model <strong>{analysis.model || 'Unavailable'}</strong></span><span>Duration <strong>{analysis.duration_ms.toFixed(0)} ms</strong></span><span>Policy <strong>{analysis.policy_version}</strong></span><span>Catalog <strong>{analysis.catalog_version}</strong></span><span>Analysis <code>{analysis.id}</code></span><span>Usage <code>{Object.keys(analysis.usage || {}).length ? JSON.stringify(analysis.usage) : 'Unavailable'}</code></span></div>
      <div className="tab-bar"><div role="tablist" aria-label="Response format"><button role="tab" aria-selected={tab === 'decisions'} onClick={() => setTab('decisions')}>Decisions <span className="count">{analysis.decisions.length}</span></button><button role="tab" aria-selected={tab === 'json'} onClick={() => setTab('json')}>Raw JSON</button></div><button className="text-button" onClick={download}><Download size={15} /> Export</button></div>
      {tab === 'json' ? <pre className="json-view" role="tabpanel">{JSON.stringify(analysis.provider_response, null, 2)}</pre> : <div role="tabpanel">{!analysis.decisions.length ? <p className="muted padded">No catalog decisions were returned. Import a reviewed catalog to make filters available.</p> : <div className="table-scroll"><table className="decision-table"><thead><tr><th>Question / filter</th><th>Primitive</th><th>Result</th><th>Probability / distribution</th><th>Confidence</th><th>Policy</th></tr></thead><tbody>{analysis.decisions.map(d => <tr key={d.question_id}><td><strong>{d.filter_label}</strong><p>{d.question}</p><code>{d.question_id}</code>{d.evidence && <p>Evidence: “{d.evidence}”</p>}<small>{d.provenance}</small></td><td><span className="badge">{d.primitive}</span><small>{d.kind}</small></td><td>{d.selected_value || '—'}</td><td>{d.primitive === 'noul' ? percent(d.probability) : d.probabilities ? <div className="distribution">{Object.entries(d.probabilities).map(([name, value]) => <div key={name}><span>{name}</span><span>{percent(value)}</span><progress value={value} max={1} aria-label={`${name} probability`} /></div>)}</div> : 'Unavailable'}</td><td>{d.primitive === 'noul' ? 'Not applicable' : percent(d.confidence)}</td><td><span className={`badge ${d.status === 'uncertain' ? 'badge-amber' : d.status === 'selected' ? 'badge-green' : ''}`}>{d.status}</span><small>Threshold: {d.threshold == null ? 'Unavailable' : d.threshold}</small></td></tr>)}</tbody></table></div>}</div>}
    </>}</div>}
  </section>
}
