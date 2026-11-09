export type Level = {
  id: string
  label: string
  rank: number | null
  dimension: string
  supports_exact?: boolean
  supports_minimum?: boolean
}

export type Category = { id: string; key: string; label: string; count: number }

export type CatalogFilter = {
  id: string
  category_id: string
  label: string
  description: string
  subcategory?: string | null
  levels: Level[]
  aliases: string[]
}

export type Constraint = {
  filter_id: string
  mode: 'include' | 'exclude'
  requirement: 'mandatory' | 'preferred'
  level_id: string | null
  operator: 'exact' | 'minimum'
  source: string
}

export type Decision = {
  question_id: string
  filter_id: string
  filter_label: string
  question: string
  primitive: 'noul' | 'choice'
  kind: string
  status: string
  probability?: number | null
  confidence?: number | null
  probabilities?: Record<string, number> | null
  selected_value?: string | null
  provenance: string
  evidence?: string | null
  threshold?: number | null
}

export type Analysis = {
  id: string
  state_text: string
  client_revision: number
  provider: string
  model: string | null
  policy_version: string
  catalog_version: string
  status: string
  created_at: string
  duration_ms: number
  filters: Constraint[]
  decisions: Decision[]
  provider_response: Record<string, unknown>
  usage: Record<string, unknown>
}

export type Competency = { filter_id: string; level_id?: string | null; present?: boolean }

export type Profile = {
  id: string
  display_name: string
  title: string
  summary: string
  experience_years: number | null
  competencies: Competency[]
  languages: Competency[]
}

export type ProfileMatch = {
  profile: Profile
  score: number
  matched: string[]
  unmet: string[]
  unknown: string[]
  eligible: boolean
}

export type Page<T> = { items: T[]; total: number; page: number; page_size: number }

export type SavedSearch = {
  id: string
  label: string
  query: string
  filters: Constraint[]
  grouping: 'and' | 'or'
  category_grouping?: Record<string, 'and' | 'or'>
  created_at: string
  updated_at?: string
}

export type Config = {
  provider: 'mock' | 'jev'
  model: string | null
  supported_locales: string[]
  max_state_length: number
}

export type Health = {
  status: 'ok' | 'degraded'
  database: { ready: boolean; reachable: boolean; migrated: boolean }
  provider: { name: 'mock' | 'jev'; ready: boolean; live_verified: boolean | null }
}
