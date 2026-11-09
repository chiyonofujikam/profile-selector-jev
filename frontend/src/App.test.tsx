import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { Analysis, CatalogFilter, Constraint, ProfileMatch } from './types'

// Deliberately isolated fixtures: these are never seeded into the application.
const { apiMock, postMock } = vi.hoisted(() => ({ apiMock: vi.fn(), postMock: vi.fn() }))
vi.mock('./api', () => ({ api: apiMock, post: postMock }))

const fixtureFilter: CatalogFilter = {
  id: 'fixture-skill', category_id: 'fixture-category', label: 'Fixture skill',
  description: 'Isolated workflow test filter.', aliases: [],
  levels: [{ id: 'fixture-level', label: 'Fixture level', rank: 1, dimension: 'tool-expertise' }],
}
const fixtureConstraint: Constraint = {
  filter_id: fixtureFilter.id, mode: 'include', requirement: 'mandatory',
  level_id: 'fixture-level', operator: 'exact', source: 'jev',
}
const fixtureMatch: ProfileMatch = {
  profile: { id: 'fixture-profile', display_name: 'Isolated candidate fixture', title: 'Test fixture only',
    summary: 'Not product demonstration data.', experience_years: null, competencies: [], languages: [] },
  score: 100, matched: ['Fixture skill'], unmet: [], unknown: [], eligible: true,
}

function resultFor(body: { state_text: string; client_revision: number }, filters = [fixtureConstraint]): Analysis {
  return {
    id: 'fixture-analysis', state_text: body.state_text, client_revision: body.client_revision,
    provider: 'jev', model: 'fixture-model', policy_version: 'fixture-policy', catalog_version: 'fixture-catalog',
    status: 'completed', created_at: '2026-01-01T00:00:00Z', duration_ms: 4, filters,
    decisions: [
      { question_id: 'fixture-relevance', filter_id: fixtureFilter.id, filter_label: fixtureFilter.label,
        question: 'Does the isolated fixture apply?', primitive: 'noul', kind: 'relevance', status: 'selected',
        probability: 0.99, provenance: 'jev', threshold: 0.7 },
      { question_id: 'fixture-level-question', filter_id: fixtureFilter.id, filter_label: fixtureFilter.label,
        question: 'Which stated fixture level applies?', primitive: 'choice', kind: 'level', status: 'selected',
        selected_value: 'fixture-level', confidence: 0.8,
        probabilities: { 'fixture-level': 0.8, unspecified: 0.15, unsupported: 0.05 }, provenance: 'jev', threshold: 0.7 },
      { question_id: 'fixture-exclusion', filter_id: fixtureFilter.id, filter_label: fixtureFilter.label,
        question: 'Is the fixture explicitly excluded?', primitive: 'noul', kind: 'exclusion', status: 'rejected',
        probability: 0.1, provenance: 'jev', threshold: 0.3 },
    ],
    provider_response: { answers: { 'fixture-level-question': { probabilities: { 'fixture-level': 0.8, unspecified: 0.15, unsupported: 0.05 } } } },
    usage: { input_tokens: 10, output_tokens: 5 },
  }
}

async function browseFilters(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Show filters' }))
  await user.click(screen.getByRole('checkbox', { name: 'Selected only' }))
}
const analysisCalls = () => postMock.mock.calls.filter(([path]) => path === '/api/v1/analyses')

beforeEach(() => {
  apiMock.mockReset()
  postMock.mockReset()
  apiMock.mockImplementation(async (path: string) => {
    if (path === '/api/v1/config') return { provider: 'jev', model: 'fixture-model', supported_locales: ['en', 'fr', 'es'] }
    if (path === '/health') return { status: 'ok', database: { ready: true }, provider: { ready: true } }
    if (path === '/api/v1/categories') return [{ id: 'fixture-category', key: 'fixture', label: 'Fixture category', count: 1 }]
    if (path.startsWith('/api/v1/filters?')) return { items: [fixtureFilter], total: 1, page: 1, page_size: 30 }
    throw new Error(`Unexpected test API path: ${path}`)
  })
  postMock.mockImplementation(async (path: string, body: { filters?: Constraint[]; state_text: string; client_revision: number }) => {
    if (path === '/api/v1/analyses') return resultFor(body)
    if (path === '/api/v1/profiles/search') return {
      items: body.filters?.length ? [fixtureMatch] : [], total: body.filters?.length ? 1 : 0, page: 1, page_size: 12,
    }
    throw new Error(`Unexpected test POST path: ${path}`)
  })
})

afterEach(() => cleanup())

describe('filter dashboard workflows', () => {
  it('keeps filters collapsed while the model runs and shows selected filters when expanded', async () => {
    const user = userEvent.setup()
    render(<App />)
    expect(screen.getByRole('button', { name: 'Show filters' }).getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('textbox', { name: 'Search catalog filters' })).toBeNull()
    await user.type(screen.getByLabelText('State'), 'Isolated requirement fixture')
    await user.click(screen.getByRole('button', { name: /Update filters/ }))
    await user.click(screen.getByRole('button', { name: 'Show candidates' }))
    await screen.findByText('Isolated candidate fixture')
    expect(screen.getByText('1 active')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Show filters' }))
    expect((screen.getByRole('checkbox', { name: 'Selected only' }) as HTMLInputElement).checked).toBe(true)
    const checkbox = await screen.findByRole<HTMLInputElement>('checkbox', { name: /Fixture skill/ })
    expect(checkbox.checked).toBe(true)
    expect(screen.getByRole('table', { name: 'Search filters' })).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Hide filters' }))
    expect(screen.queryByRole('table', { name: 'Search filters' })).toBeNull()
    expect(screen.getByText('Isolated candidate fixture')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Show filters' }))
    expect((await screen.findByRole<HTMLInputElement>('checkbox', { name: /Fixture skill/ })).checked).toBe(true)
    expect(analysisCalls()).toHaveLength(1)
  })

  it('applies an analysis, refreshes candidates, and inspects all values without another provider call', async () => {
    const user = userEvent.setup()
    render(<App />)
    await browseFilters(user)
    const checkbox = await screen.findByRole<HTMLInputElement>('checkbox', { name: /Fixture skill/ })
    expect(checkbox.checked).toBe(false)
    expect(screen.queryByRole('table', { name: 'Model decisions' })).toBeNull()
    await user.type(screen.getByLabelText('State'), 'Isolated requirement fixture')
    await user.click(screen.getByRole('button', { name: /Update filters/ }))
    await waitFor(() => expect(checkbox.checked).toBe(true))
    expect((screen.getByLabelText('Fixture skill level') as HTMLSelectElement).value).toBe('fixture-level')
    await user.click(screen.getByRole('button', { name: 'Show candidates' }))
    await screen.findByText('Isolated candidate fixture')
    expect(postMock.mock.calls.some(([path, body]) => path === '/api/v1/profiles/search' && body.filters?.[0]?.level_id === 'fixture-level')).toBe(true)
    expect(analysisCalls()).toHaveLength(1)
    expect(analysisCalls()[0][1]).toMatchObject({ state_text: 'Isolated requirement fixture', current_filters: [], locale: 'en' })

    await user.click(screen.getByRole('button', { name: /Show response/ }))
    expect(screen.getByRole('table', { name: 'Model decisions' })).toBeTruthy()
    expect(screen.getByText('fixture-exclusion')).toBeTruthy()
    expect(screen.getByText('10.0%')).toBeTruthy()
    expect(screen.getByText('15.0%')).toBeTruthy()
    expect(screen.getByText('5.0%')).toBeTruthy()
    await user.click(screen.getByRole('tab', { name: 'Raw JSON' }))
    expect(screen.getByRole('tabpanel').textContent).toContain('fixture-level-question')
    await user.click(screen.getByRole('button', { name: /Hide response/ }))
    expect(screen.queryByRole('tabpanel')).toBeNull()
    await user.click(screen.getByRole('button', { name: /Show response/ }))
    expect(screen.getByRole('tabpanel').textContent).toContain('fixture-level-question')
    expect(analysisCalls()).toHaveLength(1)
    expect(checkbox.checked).toBe(true)
  })

  it('preserves newer manual filter and level edits when a delayed analysis arrives', async () => {
    let release!: (value: Analysis) => void
    const pending = new Promise<Analysis>(resolve => { release = resolve })
    const defaultPost = postMock.getMockImplementation()!
    postMock.mockImplementation((path: string, body: unknown) => path === '/api/v1/analyses' ? pending : defaultPost(path, body))
    const user = userEvent.setup()
    render(<App />)
    await browseFilters(user)
    const checkbox = await screen.findByRole<HTMLInputElement>('checkbox', { name: /Fixture skill/ })
    await user.type(screen.getByLabelText('State'), 'Pending isolated requirement')
    await user.click(screen.getByRole('button', { name: /Update filters/ }))
    expect(analysisCalls()).toHaveLength(1)
    await user.click(checkbox)
    await user.selectOptions(screen.getByLabelText('Fixture skill level'), 'fixture-level')
    await user.selectOptions(screen.getByLabelText('Fixture skill inclusion'), 'exclude')
    const body = analysisCalls()[0][1]
    await act(async () => { release(resultFor(body, [])); await pending })
    await screen.findByText(/Your newer edits were preserved/)
    expect(checkbox.checked).toBe(true)
    expect((screen.getByLabelText('Fixture skill inclusion') as HTMLSelectElement).value).toBe('exclude')
    expect((screen.getByLabelText('Fixture skill level') as HTMLSelectElement).value).toBe('fixture-level')
    expect(screen.getByText('Out of date')).toBeTruthy()
    await waitFor(() => expect(postMock.mock.calls.some(([path, search]) => path === '/api/v1/profiles/search' && search.filters?.[0]?.mode === 'exclude')).toBe(true))
  })

  it('retains the requirement after failure and recovers through Retry', async () => {
    const defaultPost = postMock.getMockImplementation()!
    let failed = false
    postMock.mockImplementation((path: string, body: unknown) => {
      if (path === '/api/v1/analyses' && !failed) { failed = true; return Promise.reject(new Error('Provider request timed out. Please retry.')) }
      return defaultPost(path, body)
    })
    const user = userEvent.setup()
    render(<App />)
    await browseFilters(user)
    const checkbox = await screen.findByRole<HTMLInputElement>('checkbox', { name: /Fixture skill/ })
    const input = screen.getByLabelText<HTMLTextAreaElement>('State')
    await user.type(input, 'Recoverable isolated requirement')
    await user.click(screen.getByRole('button', { name: /Update filters/ }))
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Provider request timed out'))
    expect(input.value).toBe('Recoverable isolated requirement')
    expect(checkbox.checked).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(checkbox.checked).toBe(true))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(analysisCalls()).toHaveLength(2)
    expect(analysisCalls()[1][1].request_id).toBe(analysisCalls()[0][1].request_id)
    expect(input.value).toBe('Recoverable isolated requirement')
  })

  it('ignores an in-flight analysis after starting a new search', async () => {
    let release!: (value: Analysis) => void
    const pending = new Promise<Analysis>(resolve => { release = resolve })
    const defaultPost = postMock.getMockImplementation()!
    postMock.mockImplementation((path: string, body: unknown) =>
      path === '/api/v1/analyses' ? pending : defaultPost(path, body))
    const user = userEvent.setup()
    render(<App />)
    await browseFilters(user)
    const checkbox = await screen.findByRole<HTMLInputElement>('checkbox', { name: /Fixture skill/ })
    await user.type(screen.getByLabelText('State'), 'Old requirement')
    await user.click(screen.getByRole('button', { name: /Update filters/ }))
    const body = analysisCalls()[0][1]
    await user.click(screen.getByRole('button', { name: 'New search' }))
    await act(async () => { release(resultFor(body)); await pending })
    expect(screen.getByLabelText<HTMLTextAreaElement>('State').value).toBe('')
    expect(checkbox.checked).toBe(false)
    expect(screen.queryByText('Filters updated.')).toBeNull()
  })

  it('remembers unavailable selected IDs instead of repeatedly fetching them', async () => {
    const defaultApi = apiMock.getMockImplementation()!
    apiMock.mockImplementation((path: string) => path.includes('ids=')
      ? Promise.resolve({ items: [], total: 0, page: 1, page_size: 100 }) : defaultApi(path))
    const defaultPost = postMock.getMockImplementation()!
    postMock.mockImplementation((path: string, body: Parameters<typeof resultFor>[0]) => path === '/api/v1/analyses'
      ? Promise.resolve(resultFor(body, [{ ...fixtureConstraint, filter_id: 'unavailable-filter' }])) : defaultPost(path, body))
    const user = userEvent.setup()
    render(<App />)
    await browseFilters(user)
    await screen.findByRole('checkbox', { name: /Fixture skill/ })
    await user.type(screen.getByLabelText('State'), 'A changed catalog')
    await user.click(screen.getByRole('button', { name: /Update filters/ }))
    await screen.findByText(/Some selected filters are no longer available/)
    await user.type(screen.getByLabelText('Search catalog filters'), 'another search')
    await waitFor(() => expect(apiMock.mock.calls.some(([path]) => path.includes('q=another+search'))).toBe(true))
    expect(apiMock.mock.calls.filter(([path]) => path.includes('ids='))).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Remove unavailable-filter' }))
    expect(screen.queryByText(/Some selected filters are no longer available/)).toBeNull()
  })

  it('returns candidate pagination to page one after a filter edit', async () => {
    const defaultPost = postMock.getMockImplementation()!
    postMock.mockImplementation((path: string, body: { page: number }) => path === '/api/v1/profiles/search'
      ? Promise.resolve({ items: [fixtureMatch], total: 24, page: body.page, page_size: 12 }) : defaultPost(path, body))
    const user = userEvent.setup()
    render(<App />)
    await browseFilters(user)
    await user.click(screen.getByRole('button', { name: 'Show candidates' }))
    await user.click(await screen.findByRole('button', { name: 'Next page' }))
    const searches = () => postMock.mock.calls.filter(([path]) => path === '/api/v1/profiles/search')
    await waitFor(() => expect(searches().at(-1)?.[1].page).toBe(2))
    await user.click(screen.getByRole('checkbox', { name: /Fixture skill/ }))
    await waitFor(() => expect(searches().at(-1)?.[1]).toMatchObject({ page: 1, filters: [{ filter_id: fixtureFilter.id }] }))
  })

  it('keeps candidates collapsed while matches refresh and displays the latest results when opened', async () => {
    const user = userEvent.setup()
    render(<App />)
    await browseFilters(user)
    expect(screen.getByRole('button', { name: 'Show candidates' }).getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('table', { name: 'Matching candidates' })).toBeNull()
    const checkbox = await screen.findByRole<HTMLInputElement>('checkbox', { name: /Fixture skill/ })
    await user.click(checkbox)
    const searches = () => postMock.mock.calls.filter(([path]) => path === '/api/v1/profiles/search')
    await waitFor(() => expect(searches().at(-1)?.[1].filters).toHaveLength(1))
    expect(screen.queryByText('Isolated candidate fixture')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Show candidates' }))
    await screen.findByRole('button', { name: 'Isolated candidate fixture' })
    expect(screen.getByRole('table', { name: 'Matching candidates' })).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Hide candidates' }))
    await user.click(checkbox)
    await waitFor(() => expect(searches().at(-1)?.[1].filters).toHaveLength(0))
    await user.click(screen.getByRole('button', { name: 'Show candidates' }))
    await screen.findByText('No profiles yet')
    expect(screen.queryByRole('button', { name: 'Isolated candidate fixture' })).toBeNull()
    expect(analysisCalls()).toHaveLength(0)
  })
})
