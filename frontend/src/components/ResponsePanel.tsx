import { useState } from 'react'
import type { Analysis, Decision } from '../api/types'
import { modelText } from '../modelText'

const percent = (value: number | null | undefined) =>
  value == null ? 'Unavailable' : `${(value * 100).toFixed(1)}%`

function DecisionRow({ decision }: { decision: Decision }) {
  return <tr>
    <td><strong>{decision.filter_label}</strong><small>{decision.kind} · {decision.primitive}</small>
      <details><summary>Question</summary><p>{decision.question}</p><code>{decision.question_id}</code></details>
      {decision.evidence && <p>Evidence: “{decision.evidence}”</p>}
    </td>
    <td>{decision.selected_value || '—'}<small>{decision.status}</small></td>
    <td>{decision.primitive === 'noul' ? percent(decision.probability)
      : decision.probabilities ? <div className="distribution">
        {Object.entries(decision.probabilities).map(([name, value]) => <div key={name}>
          <span>{name}</span><span>{percent(value)}</span>
          <progress value={value} max={1} aria-label={`${name} probability`} />
        </div>)}
      </div> : 'Unavailable'}
    </td>
    <td>{decision.primitive === 'noul' ? 'Not applicable' : percent(decision.confidence)}</td>
    <td>{decision.threshold ?? 'Unavailable'}<small>{modelText(decision.provenance)}</small></td>
  </tr>
}

export function ResponsePanel({ analysis, stale }: { analysis: Analysis | null; stale: boolean }) {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<'decisions' | 'json'>('decisions')

  function download() {
    if (!analysis) return
    const url = URL.createObjectURL(new Blob([JSON.stringify(analysis, null, 2)], { type: 'application/json' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `descion-model-analysis-${analysis.id}.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return <section className="panel response-panel">
    <button className="response-toggle" onClick={() => setOpen(value => !value)} aria-expanded={open} aria-controls="model-response">
      <strong>Decision model response</strong>
      <span className="response-end">
        {analysis && <span className={`badge ${stale ? 'badge-amber' : ''}`}>
          {stale ? 'Out of date' : `${analysis.decisions.length} decisions`}
        </span>}
        <span>{open ? 'Hide response' : 'Show response'}</span>
      </span>
    </button>
    {open && <div id="model-response" className="response-content">
      {!analysis ? <p className="empty-state">No analysis yet</p> : <>
        {stale && <p className="notice warning">Your requirement or filters changed. Submit again to update the response.</p>}
        {analysis.provider === 'mock' && <p className="notice">Demo decisions use local rules. Their values are not Decision model probabilities.</p>}
        <div className="analysis-meta">
          <span>{analysis.provider === 'mock' ? 'Demo' : 'Live Decision model'}</span>
          <span>{analysis.model ? modelText(analysis.model) : 'Model unavailable'}</span><span>{analysis.duration_ms.toFixed(0)} ms</span>
        </div>
        <div className="tab-bar">
          <div role="tablist" aria-label="Response format">
            <button role="tab" aria-selected={tab === 'decisions'} onClick={() => setTab('decisions')}>Decisions</button>
            <button role="tab" aria-selected={tab === 'json'} onClick={() => setTab('json')}>Raw JSON</button>
          </div>
          <button onClick={download}>Export analysis</button>
        </div>
        {tab === 'json' ? <pre className="json-view" role="tabpanel">{JSON.stringify(analysis.provider_response, null, 2)}</pre>
          : <div role="tabpanel">{!analysis.decisions.length ? <p>No catalog decisions were returned.</p>
            : <div className="table-scroll"><table className="decision-table" aria-label="Model decisions">
              <thead><tr><th>Filter / question</th><th>Result</th><th>Probability / distribution</th><th>Confidence</th><th>Threshold / source</th></tr></thead>
              <tbody>{analysis.decisions.map(decision => <DecisionRow key={decision.question_id} decision={decision} />)}</tbody>
            </table></div>}
          </div>}
      </>}
    </div>}
  </section>
}
