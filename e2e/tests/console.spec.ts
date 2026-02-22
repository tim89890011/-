import { test, expect } from '@playwright/test'

test.describe('Console — zero errors on public pages', () => {
  test('/login.html has zero console errors', async ({ page }) => {
    const errors: string[] = []
    const warnings: string[] = []
    const pageErrors: string[] = []

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text())
      }
      if (msg.type() === 'warning') {
        warnings.push(msg.text())
      }
    })

    page.on('pageerror', (err) => {
      pageErrors.push(err.message)
    })

    page.on('requestfailed', (req) => {
      // Ignore favicon and optional assets
      const url = req.url()
      if (!url.includes('favicon')) {
        errors.push(`Request failed: ${url} — ${req.failure()?.errorText}`)
      }
    })

    await page.goto('/login.html')

    // Wait 3 seconds for async scripts and WS attempts
    await page.waitForTimeout(3_000)

    if (warnings.length > 0) {
      console.log('Warnings (allowed):', warnings)
    }

    expect(errors, `Console errors found:\n${errors.join('\n')}`).toHaveLength(
      0
    )
    expect(
      pageErrors,
      `Page errors found:\n${pageErrors.join('\n')}`
    ).toHaveLength(0)
  })

  test('/register.html has zero console errors', async ({ page }) => {
    const errors: string[] = []
    const pageErrors: string[] = []

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text())
      }
    })

    page.on('pageerror', (err) => {
      pageErrors.push(err.message)
    })

    page.on('requestfailed', (req) => {
      const url = req.url()
      if (!url.includes('favicon')) {
        errors.push(`Request failed: ${url} — ${req.failure()?.errorText}`)
      }
    })

    await page.goto('/register.html')
    await page.waitForTimeout(3_000)

    expect(errors, `Console errors found:\n${errors.join('\n')}`).toHaveLength(
      0
    )
    expect(
      pageErrors,
      `Page errors found:\n${pageErrors.join('\n')}`
    ).toHaveLength(0)
  })
})
