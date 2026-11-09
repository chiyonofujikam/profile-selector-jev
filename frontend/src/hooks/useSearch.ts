import { useRef, useState } from 'react'
import { post } from '../api/client'
import type { Analysis, Constraint, SavedSearch } from '../api/types'

export const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : 'Something went wrong. Please retry.'

/** Owns editable search state. Only an explicit submit calls Jev. */
export function useSearch() {
  const [text, setText] = useState('')
  const [locale, setLocale] = useState('en')
  const [filters, setFilters] = useState<Constraint[]>([])
  const [grouping, setGrouping] = useState<'and' | 'or'>('and')
  const [categoryGrouping, setCategoryGrouping] = useState<Record<string, 'and' | 'or'>>({})
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [revision, setRevision] = useState(0)
  const revisionRef = useRef(0)
  const sequence = useRef(0)
  const pending = useRef<{ revision: number; id: string } | null>(null)

  function markEdit() {
    revisionRef.current += 1
    setRevision(revisionRef.current)
  }

  function updateFilter(id: string, update: Partial<Constraint> | null) {
    markEdit()
    setFilters(current => {
      if (update === null) return current.filter(filter => filter.filter_id !== id)
      if (current.some(filter => filter.filter_id === id)) {
        return current.map(filter => filter.filter_id === id
          ? { ...filter, ...update, source: 'manual' } : filter)
      }
      return [...current, {
        filter_id: id, mode: 'include', requirement: 'mandatory',
        level_id: null, operator: 'exact', ...update, source: 'manual',
      }]
    })
  }

  async function submit() {
    if (!text.trim() || analyzing) return
    const submittedRevision = revisionRef.current
    // A retry of the same input reuses its ID to avoid duplicate provider calls.
    if (pending.current?.revision !== submittedRevision) {
      pending.current = { revision: submittedRevision, id: crypto.randomUUID() }
    }
    const requestId = pending.current!.id
    const requestSequence = ++sequence.current
    setAnalyzing(true)
    setError('')
    setNotice('')
    try {
      const result = await post<Analysis>('/api/v1/analyses', {
        state_text: text, current_filters: filters, locale,
        client_revision: submittedRevision, request_id: requestId,
      })
      if (requestSequence !== sequence.current) return
      pending.current = null
      setAnalysis(result)
      // Text and manual filter edits made during the request take precedence.
      if (submittedRevision === revisionRef.current) {
        setFilters(result.filters)
        setNotice('Filters updated.')
      } else {
        setNotice('Your newer edits were preserved. Submit again to update the filters.')
      }
    } catch (error) {
      if (requestSequence === sequence.current) setError(errorMessage(error))
    } finally {
      if (requestSequence === sequence.current) setAnalyzing(false)
    }
  }

  function reset() {
    markEdit()
    sequence.current += 1
    pending.current = null
    setText('')
    setFilters([])
    setGrouping('and')
    setCategoryGrouping({})
    setAnalysis(null)
    setAnalyzing(false)
    setError('')
    setNotice('')
  }

  function restore(item: SavedSearch | Analysis) {
    reset()
    setText('query' in item ? item.query : item.state_text)
    setFilters(item.filters)
    if ('query' in item) {
      setGrouping(item.grouping)
      setCategoryGrouping(item.category_grouping || {})
    } else {
      setAnalysis({ ...item, client_revision: revisionRef.current })
    }
  }

  return {
    text, locale, filters, grouping, categoryGrouping, analysis, analyzing, error, notice,
    stale: !!analysis && analysis.client_revision !== revision,
    setText: (value: string) => { markEdit(); setText(value) },
    setLocale: (value: string) => { markEdit(); setLocale(value) },
    setGrouping: (value: 'and' | 'or') => { markEdit(); setGrouping(value) },
    setCategoryGrouping: (value: Record<string, 'and' | 'or'>) => { markEdit(); setCategoryGrouping(value) },
    clearFilters: () => { markEdit(); setFilters([]) },
    updateFilter, submit, reset, restore,
  }
}

export type SearchState = ReturnType<typeof useSearch>
