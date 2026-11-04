import type { CatalogFilter, Constraint } from '../api/types'

export function FilterRow({ filter, active, update }: { filter: CatalogFilter; active?: Constraint; update: (id: string, value: Partial<Constraint> | null) => void }) {
  const level = filter.levels.find(l => l.id === active?.level_id)
  const exact = level?.supports_exact !== false
  const minimum = level?.rank != null && level.supports_minimum !== false
  return <div className={`filter-row ${active ? 'filter-row-active' : ''}`}>
    <label className="filter-check">
      <input type="checkbox" checked={!!active} onChange={e => update(filter.id, e.target.checked ? {} : null)} />
      <span className="filter-description"><span className="filter-label">{filter.label}{active && <span className={`source-label ${active.source === 'manual' ? '' : 'source-jev'}`}>{active.source === 'manual' ? 'Manual' : active.source === 'jev' ? 'Jev update' : active.source === 'demo_logic' ? 'Demo update' : 'Rule update'}</span>}</span><span>{filter.description}</span>{filter.subcategory && <small>{filter.subcategory}</small>}</span>
    </label>
    <div className="filter-controls">
      <label><span className="sr-only">{filter.label} inclusion</span><select disabled={!active} value={active?.mode || 'include'} onChange={e => update(filter.id, { mode: e.target.value as Constraint['mode'] })}><option value="include">Include</option><option value="exclude">Exclude</option></select></label>
      <label><span className="sr-only">{filter.label} requirement</span><select disabled={!active || active.mode === 'exclude'} value={active?.requirement || 'mandatory'} onChange={e => update(filter.id, { requirement: e.target.value as Constraint['requirement'] })}><option value="mandatory">Required</option><option value="preferred">Preferred</option></select></label>
      {filter.levels.length > 0 && <><label><span className="sr-only">{filter.label} level</span><select disabled={!active} value={active?.level_id || ''} onChange={e => {
        const next = filter.levels.find(l => l.id === e.target.value)
        const canMin = next?.rank != null && next.supports_minimum !== false
        update(filter.id, { level_id: e.target.value || null, operator: next?.supports_exact === false && canMin ? 'minimum' : active?.operator === 'minimum' && canMin ? 'minimum' : 'exact' })
      }}><option value="">Any level</option>{filter.levels.map(l => <option key={l.id} value={l.id}>{l.label}</option>)}</select></label>
      {active?.level_id && <label><span className="sr-only">{filter.label} level operator</span><select value={active.operator} onChange={e => update(filter.id, { operator: e.target.value as Constraint['operator'] })}><option value="exact" disabled={!exact}>Exactly</option><option value="minimum" disabled={!minimum}>Or higher</option></select></label>}</>}
    </div>
  </div>
}
