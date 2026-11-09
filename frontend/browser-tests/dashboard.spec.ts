import { expect, test } from '@playwright/test'
import type { Analysis, CatalogFilter, Constraint, SavedSearch } from '../src/api/types'

// Isolated browser fixtures. No product database or live Jev request is used.
const filter: CatalogFilter = {
  id: 'fixture-skill', category_id: 'fixture-tools', label: 'Fixture skill',
  description: 'An isolated test filter.', aliases: [], levels: [],
}
const constraint: Constraint = {
  filter_id: filter.id, mode: 'include', requirement: 'mandatory',
  level_id: null, operator: 'exact', source: 'jev',
}

test('minimal workspace, keyboard dialogs, and mobile layout', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/health', route => route.fulfill({ json: {
    status: 'ok', database: { ready: true }, provider: { ready: true },
  } }))
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/config')) return route.fulfill({ json: { provider: 'mock', model: 'demo', max_state_length: 12000 } })
    if (path.endsWith('/categories')) return route.fulfill({ json: [] })
    return route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 30 } })
  })
  await page.setViewportSize({ width: 1440, height: 1200 })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Find the right expertise' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Update filters/ })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Show filters' })).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByRole('textbox', { name: 'Search catalog filters' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Show candidates' })).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByRole('table', { name: 'Matching candidates' })).toHaveCount(0)
  await page.screenshot({ path: 'test-results/dashboard-desktop.png', fullPage: true })

  await page.getByRole('button', { name: 'Show filters' }).click()
  await expect(page.getByText('No selected filters')).toBeVisible()
  await page.getByRole('button', { name: 'Browse catalog' }).click()
  await expect(page.getByText('No filters yet')).toBeVisible()
  await page.getByRole('button', { name: 'Hide filters' }).click()
  await page.getByRole('button', { name: 'Show candidates' }).click()
  await expect(page.getByText('No profiles yet')).toBeVisible()
  await page.getByRole('button', { name: 'Hide candidates' }).click()

  await page.getByRole('button', { name: /Show response/ }).click()
  await expect(page.getByText('No analysis yet')).toBeVisible()
  await page.getByRole('button', { name: /Hide response/ }).click()
  await page.getByLabel('State', { exact: true }).fill('Browser validation input')
  await page.getByRole('button', { name: 'Save search', exact: true }).click()
  await expect(page.getByRole('textbox', { name: 'Search name' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByRole('button', { name: 'New search' }).click()
  await expect(page.getByLabel('State', { exact: true })).toHaveValue('')

  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Saved searches', exact: true }).click()
  await expect(page.getByText('No saved searches yet.')).toBeVisible()
  await page.keyboard.press('Escape')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/dashboard-mobile.png', fullPage: true })
  expect(errors).toEqual([])
})

test('analyze, save, restore, and delete a search', async ({ page }) => {
  const saved: SavedSearch[] = []
  const catalog = [filter, ...Array.from({ length: 29 }, (_, index) => ({
    ...filter, id: `fixture-extra-${index}`, label: `Catalog filter ${index + 2}`,
  }))]
  let providerCalls = 0
  await page.route('**/health', route => route.fulfill({ json: { status: 'ok', database: { ready: true }, provider: { ready: true } } }))
  await page.route('**/api/v1/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const body = request.method() === 'POST' ? request.postDataJSON() : null
    if (path.endsWith('/config')) return route.fulfill({ json: { provider: 'jev', model: 'fixture-model', max_state_length: 12000 } })
    if (path.endsWith('/categories')) return route.fulfill({ json: [{ id: 'fixture-tools', label: 'Tools', count: 1 }] })
    if (path.endsWith('/filters')) return route.fulfill({ json: { items: catalog, total: catalog.length, page: 1, page_size: 30 } })
    if (path.endsWith('/analyses') && body) {
      providerCalls += 1
      const analysis: Analysis = {
        id: 'fixture-analysis', state_text: body.state_text, client_revision: body.client_revision,
        provider: 'jev', model: 'fixture-model', policy_version: 'fixture', catalog_version: 'fixture',
        status: 'completed', created_at: '2026-01-01T00:00:00Z', duration_ms: 4,
        filters: [constraint], decisions: [], provider_response: {}, usage: {},
      }
      return route.fulfill({ json: analysis })
    }
    if (path.endsWith('/saved-searches')) {
      if (body) {
        const item = { ...body, id: 'fixture-saved', created_at: '2026-01-01T00:00:00Z' }
        saved.push(item)
        return route.fulfill({ status: 201, json: item })
      }
      return route.fulfill({ json: { items: saved, total: saved.length, page: 1, page_size: 20 } })
    }
    if (request.method() === 'DELETE') { saved.length = 0; return route.fulfill({ status: 204 }) }
    return route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 12 } })
  })
  await page.goto('/')
  await page.getByLabel('State', { exact: true }).fill('Need fixture skill')
  await page.getByRole('button', { name: /Update filters/ }).click()
  await expect(page.getByText('1 active')).toBeVisible()
  await expect(page.getByRole('table', { name: 'Search filters' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Show filters' }).click()
  await expect(page.getByRole('checkbox', { name: /Fixture skill/ })).toBeChecked()
  await expect(page.getByRole('table', { name: 'Search filters' }).getByRole('row')).toHaveCount(2)
  await page.getByRole('checkbox', { name: 'Selected only' }).uncheck()
  await expect(page.getByRole('table', { name: 'Search filters' }).getByRole('row')).toHaveCount(31)
  const tableRegion = page.getByRole('region', { name: 'Scrollable search filters' })
  expect(await tableRegion.evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true)
  await tableRegion.evaluate(element => { element.scrollTop = element.scrollHeight })
  await expect(page.getByRole('columnheader', { name: 'Filter', exact: true })).toBeVisible()
  await page.screenshot({ path: 'test-results/filters-table-desktop.png', fullPage: true })
  await page.getByRole('button', { name: 'Save search', exact: true }).click()
  await page.getByLabel('Search name').fill('My search')
  await page.getByRole('dialog').getByRole('button', { name: 'Save search', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByRole('button', { name: 'New search' }).click()
  await expect(page.getByRole('checkbox', { name: /Fixture skill/ })).not.toBeChecked()
  await page.getByRole('button', { name: 'Saved searches', exact: true }).click()
  await page.getByRole('button', { name: /^My search/ }).click()
  await expect(page.getByLabel('State', { exact: true })).toHaveValue('Need fixture skill')
  await expect(page.getByRole('checkbox', { name: /Fixture skill/ })).toBeChecked()
  await page.getByRole('button', { name: 'Saved searches', exact: true }).click()
  await page.getByRole('button', { name: 'Delete My search' }).click()
  await expect(page.getByText('No saved searches yet.')).toBeVisible()
  expect(providerCalls).toBe(1)
  await page.keyboard.press('Escape')
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/dashboard-populated-mobile.png', fullPage: true })
  expect(await tableRegion.evaluate(element => element.scrollWidth > element.clientWidth)).toBe(true)
})

test('collapsed candidates, scrolling, and profile details on desktop and mobile', async ({ page }) => {
  const matches = Array.from({ length: 12 }, (_, index) => ({
    profile: {
      id: `candidate-fixture-${index}`, display_name: `Candidate fixture ${index + 1}`,
      title: 'Test engineer', summary: 'Isolated browser fixture.', experience_years: index + 2,
      competencies: [], languages: [],
    },
    score: 100, matched: ['Fixture skill'], unmet: [], unknown: [], eligible: true,
  }))
  let searches = 0
  await page.route('**/health', route => route.fulfill({ json: { status: 'ok', database: { ready: true }, provider: { ready: true } } }))
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/config')) return route.fulfill({ json: { provider: 'mock', model: 'fixture', max_state_length: 12000 } })
    if (path.endsWith('/profiles/search')) {
      searches += 1
      return route.fulfill({ json: { items: matches, total: matches.length, page: 1, page_size: 12 } })
    }
    return route.fulfill({ json: [] })
  })
  await page.setViewportSize({ width: 1440, height: 1200 })
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Show candidates' })).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByRole('heading', { name: /3\. View matches 12$/ })).toBeVisible()
  await expect(page.getByRole('table', { name: 'Matching candidates' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Show candidates' }).click()
  const table = page.getByRole('table', { name: 'Matching candidates' })
  const tableRegion = page.getByRole('region', { name: 'Scrollable candidates' })
  await expect(table.getByRole('row')).toHaveCount(13)
  expect(await tableRegion.evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true)
  await page.getByRole('button', { name: 'Candidate fixture 1', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByRole('dialog').getByText('Fixture skill', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await tableRegion.evaluate(element => { element.scrollTop = element.scrollHeight })
  await expect(page.getByRole('columnheader', { name: 'Candidate', exact: true })).toBeVisible()
  await page.screenshot({ path: 'test-results/candidates-table-desktop.png', fullPage: true })
  await page.getByRole('button', { name: 'Hide candidates' }).click()
  await expect(table).toHaveCount(0)
  await page.getByRole('button', { name: 'Show candidates' }).click()
  await expect(table.getByRole('row')).toHaveCount(13)
  expect(searches).toBe(1)
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await tableRegion.evaluate(element => element.scrollWidth > element.clientWidth)).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/candidates-table-mobile.png', fullPage: true })
})
