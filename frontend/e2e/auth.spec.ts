import { test, expect } from '@playwright/test'

test.describe('Authentication', () => {
  test('login page loads', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByRole('heading', { name: /sign in|login|nvr/i })).toBeVisible()
    await expect(page.getByLabel(/email/i)).toBeVisible()
    await expect(page.getByLabel('Password')).toBeVisible()
  })

  test('shows validation errors on empty submit', async ({ page }) => {
    await page.goto('/login')
    await page.getByRole('button', { name: /sign in|login/i }).click()
    await expect(page.getByText(/required|invalid/i)).toBeVisible({ timeout: 3000 })
  })

  test('demo login works in dev mode', async ({ page }) => {
    await page.goto('/login')
    const demoBtn = page.getByRole('button', { name: /demo login/i })
    if (await demoBtn.isVisible()) {
      await demoBtn.click()
      await expect(page).toHaveURL('/', { timeout: 5000 })
    } else {
      test.skip()
    }
  })

  test('redirects unauthenticated user to login', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/login/, { timeout: 5000 })
  })

  test('logout clears session', async ({ page }) => {
    await page.goto('/login')
    const demoBtn = page.getByRole('button', { name: /demo login/i })
    if (await demoBtn.isVisible()) {
      await demoBtn.click()
      await expect(page).toHaveURL('/', { timeout: 5000 })
      // Open user dropdown and logout
      const userMenu = page.getByRole('button', { name: /user menu|profile|avatar/i }).first()
      if (await userMenu.isVisible()) {
        await userMenu.click()
        const logoutBtn = page.getByRole('menuitem', { name: /logout|sign out/i })
        if (await logoutBtn.isVisible()) {
          await logoutBtn.click()
          await expect(page).toHaveURL(/login/, { timeout: 5000 })
        }
      }
    } else {
      test.skip()
    }
  })
})
