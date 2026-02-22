import { test, expect } from '@playwright/test'

test.describe('Smoke — page load & core containers', () => {
  test('/ redirects to login.html or shows login', async ({ page }) => {
    const response = await page.goto('/')
    expect(response).not.toBeNull()
    expect(response!.status()).toBeLessThan(500)

    // Should end up on login.html (redirect) or index.html
    const url = page.url()
    expect(
      url.includes('login.html') || url.includes('index.html')
    ).toBeTruthy()
  })

  test('/login.html loads with correct title and login form', async ({
    page,
  }) => {
    await page.goto('/login.html')
    await expect(page).toHaveTitle(/钢子出击/)
    await expect(page.locator('#loginForm')).toBeVisible()
    await expect(page.locator('#username')).toBeVisible()
    await expect(page.locator('#password')).toBeVisible()
    await expect(page.locator('#loginBtn')).toBeVisible()
  })

  test('/index.html loads without 5xx error', async ({ page }) => {
    const response = await page.goto('/index.html')
    expect(response).not.toBeNull()
    expect(response!.status()).toBeLessThan(500)
  })
})
