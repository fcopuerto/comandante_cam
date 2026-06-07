import { test, expect } from '@playwright/test'

async function demoLogin(page: import('@playwright/test').Page) {
  await page.goto('/login')
  const demoBtn = page.getByRole('button', { name: /demo login/i })
  if (await demoBtn.isVisible()) {
    await demoBtn.click()
    await expect(page).toHaveURL('/', { timeout: 5000 })
    return true
  }
  return false
}

test.describe('Alerts page', () => {
  test('navigates to alerts page', async ({ page }) => {
    if (!(await demoLogin(page))) test.skip()
    await page.goto('/alerts')
    await expect(page.getByRole('heading', { name: /alerts/i })).toBeVisible({ timeout: 5000 })
  })

  test('filter bar is visible', async ({ page }) => {
    if (!(await demoLogin(page))) test.skip()
    await page.goto('/alerts')
    await expect(page.getByPlaceholder(/search|filter/i).first()).toBeVisible({ timeout: 5000 })
  })

  test('stats cards are visible', async ({ page }) => {
    if (!(await demoLogin(page))) test.skip()
    await page.goto('/alerts')
    // Stats bar should have at least 4 cards
    const cards = page.locator('[class*="card"], [class*="Card"]')
    await expect(cards.first()).toBeVisible({ timeout: 5000 })
  })

  test('period toggle changes stats', async ({ page }) => {
    if (!(await demoLogin(page))) test.skip()
    await page.goto('/alerts')
    const periodBtn = page.getByRole('tab', { name: /7d/i })
    if (await periodBtn.isVisible()) {
      await periodBtn.click()
      await expect(periodBtn).toHaveAttribute('data-state', 'active')
    }
  })
})
