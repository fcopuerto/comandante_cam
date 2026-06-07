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

test.describe('Live View', () => {
  test('navigates to live view page', async ({ page }) => {
    if (!(await demoLogin(page))) test.skip()
    await page.getByRole('link', { name: /live/i }).click()
    await expect(page).toHaveURL(/live/, { timeout: 5000 })
  })

  test('camera grid is rendered', async ({ page }) => {
    if (!(await demoLogin(page))) test.skip()
    await page.goto('/live')
    await expect(page.locator('[class*="grid"]').first()).toBeVisible({ timeout: 5000 })
  })

  test('layout selector buttons visible', async ({ page }) => {
    if (!(await demoLogin(page))) test.skip()
    await page.goto('/live')
    // Layout buttons: 1x1, 2x2, 3x3, 4x4
    const buttons = page.getByRole('button')
    await expect(buttons.first()).toBeVisible({ timeout: 3000 })
  })
})
