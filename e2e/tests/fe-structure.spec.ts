import { test, expect } from '@playwright/test'

test.describe('FE Structure — UI element verification', () => {
  test('/login.html has login form with all required fields', async ({
    page,
  }) => {
    await page.goto('/login.html')

    // Form exists
    await expect(page.locator('#loginForm')).toBeVisible()

    // Username input
    const username = page.locator('#username')
    await expect(username).toBeVisible()
    await expect(username).toHaveAttribute('type', 'text')

    // Password input
    const password = page.locator('#password')
    await expect(password).toBeVisible()
    await expect(password).toHaveAttribute('type', 'password')

    // Submit button
    await expect(page.locator('#loginBtn')).toBeVisible()

    // Navigation links
    await expect(page.locator('a[href="/register.html"]')).toBeVisible()
    await expect(
      page.locator('a[href="/forgot-password.html"]')
    ).toBeVisible()
  })

  test('/register.html has registration form', async ({ page }) => {
    await page.goto('/register.html')

    await expect(page.locator('#registerForm')).toBeVisible()
    await expect(page.locator('#username')).toBeVisible()
    await expect(page.locator('#password')).toBeVisible()
    await expect(page.locator('#captchaAnswer')).toBeVisible()

    // Back to login link
    await expect(page.locator('a[href="/login.html"]')).toBeVisible()
  })

  test('/settings.html loads without JS errors', async ({ page }) => {
    const pageErrors: string[] = []

    page.on('pageerror', (err) => {
      pageErrors.push(err.message)
    })

    const response = await page.goto('/settings.html')
    expect(response).not.toBeNull()
    expect(response!.status()).toBeLessThan(500)

    // Settings page may redirect to login if not authenticated, that's OK
    // We just verify it doesn't crash with a 5xx or throw uncaught JS errors
    expect(
      pageErrors,
      `Page errors on settings.html:\n${pageErrors.join('\n')}`
    ).toHaveLength(0)
  })
})
