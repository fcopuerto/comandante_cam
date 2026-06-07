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

test.describe('Recordings / Export', () => {
  test('navigates to recordings page', async ({ page }) => {
    if (!(await demoLogin(page))) test.skip()
    await page.goto('/recordings')
    await expect(page.getByRole('heading', { name: /recordings/i })).toBeVisible({ timeout: 5000 })
  })

  test('calendar is visible', async ({ page }) => {
    if (!(await demoLogin(page))) test.skip()
    await page.goto('/recordings')
    // Calendar renders month/year heading
    const calendar = page.locator('[class*="calendar"], [class*="Calendar"], [role="grid"]')
    await expect(calendar.first()).toBeVisible({ timeout: 5000 })
  })

  test('camera list is visible', async ({ page }) => {
    if (!(await demoLogin(page))) test.skip()
    await page.goto('/recordings')
    // Camera selector in sidebar
    const sidebar = page.locator('aside, [class*="sidebar"], [class*="left"]').first()
    await expect(sidebar).toBeVisible({ timeout: 5000 })
  })

  test('export button is present', async ({ page }) => {
    if (!(await demoLogin(page))) test.skip()
    await page.goto('/recordings')
    const exportBtn = page.getByRole('button', { name: /export/i })
    await expect(exportBtn).toBeVisible({ timeout: 5000 })
  })
})
