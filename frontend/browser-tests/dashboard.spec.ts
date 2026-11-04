import { expect, test } from '@playwright/test'

test('local dashboard, dialogs, and mobile navigation', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.setViewportSize({ width: 1440, height: 1200 })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Find the right expertise.' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Update filters with Jev/ })).toBeDisabled()
  await expect(page.getByText('A clear starting point')).toBeVisible({ timeout: 15000 })
  await expect(page.getByText('The right people, once your data is here')).toBeVisible()
  await page.screenshot({ path: 'test-results/dashboard-desktop.png', fullPage: true })

  await page.getByRole('button', { name: /Show response/ }).click()
  await expect(page.getByText('No analysis yet')).toBeVisible()
  await page.getByRole('button', { name: /Hide response/ }).click()
  await page.getByRole('button', { name: 'Getting started' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)

  await page.getByLabel('State for Jev').fill('Browser validation input')
  await expect(page.getByRole('button', { name: /Update filters with Jev/ })).toBeEnabled()
  await page.getByRole('button', { name: 'Save search', exact: true }).click()
  await expect(page.getByRole('textbox', { name: 'Search name' })).toBeFocused()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'New search' }).click()
  await expect(page.getByLabel('State for Jev')).toHaveValue('')

  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('button', { name: 'Saved searches', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect.poll(async () => { const rect = await page.locator('aside').boundingBox(); return (rect?.x || 0) + (rect?.width || 0) }).toBeLessThanOrEqual(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/dashboard-mobile.png', fullPage: true })
  expect(errors).toEqual([])
})
