import type { CatalogFilter, Constraint } from '../api/types'

type Props = {
  filter: CatalogFilter
  active?: Constraint
  update: (id: string, value: Partial<Constraint> | null) => void
}

export function FilterRow({ filter, active, update }: Props) {
  const level = filter.levels.find(item => item.id === active?.level_id)
  const exact = level?.supports_exact !== false
  const minimum = level?.rank != null && level.supports_minimum !== false

  function changeLevel(id: string) {
    const next = filter.levels.find(item => item.id === id)
    const canMinimum = next?.rank != null && next.supports_minimum !== false
    const useMinimum = canMinimum && (next?.supports_exact === false || active?.operator === 'minimum')
    update(filter.id, { level_id: id || null, operator: useMinimum ? 'minimum' : 'exact' })
  }

  return <div className="filter-row">
    <label className="filter-check">
      <input type="checkbox" checked={!!active} onChange={event => update(filter.id, event.target.checked ? {} : null)} />
      <span className="filter-description">
        <span className="filter-label">{filter.label}
          {active && <span className="source-label">{active.source === 'jev' ? 'Decision model' : active.source === 'manual' ? 'Manual' : 'Demo'}</span>}
        </span>
        <span>{filter.description}</span>
        {filter.subcategory && <small>{filter.subcategory}</small>}
      </span>
    </label>
    {active && <div className="filter-controls">
      <select aria-label={`${filter.label} inclusion`} value={active.mode}
        onChange={event => update(filter.id, { mode: event.target.value as Constraint['mode'] })}>
        <option value="include">Include</option><option value="exclude">Exclude</option>
      </select>
      <select aria-label={`${filter.label} requirement`} value={active.requirement} disabled={active.mode === 'exclude'}
        onChange={event => update(filter.id, { requirement: event.target.value as Constraint['requirement'] })}>
        <option value="mandatory">Required</option><option value="preferred">Preferred</option>
      </select>
      {filter.levels.length > 0 && <select aria-label={`${filter.label} level`} value={active.level_id || ''}
        onChange={event => changeLevel(event.target.value)}>
        <option value="">Any level</option>
        {filter.levels.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
      </select>}
      {active.level_id && <select aria-label={`${filter.label} level operator`} value={active.operator}
        onChange={event => update(filter.id, { operator: event.target.value as Constraint['operator'] })}>
        <option value="exact" disabled={!exact}>Exactly</option><option value="minimum" disabled={!minimum}>Or higher</option>
      </select>}
    </div>}
  </div>
}
