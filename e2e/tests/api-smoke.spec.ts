import { test, expect } from '@playwright/test'

test.describe('API Smoke — backend health & public endpoints', () => {
  test('GET /api/health/live returns alive', async ({ request }) => {
    const response = await request.get('/api/health/live')
    expect(response.status()).toBe(200)

    const body = await response.json()
    expect(body.status).toBe('alive')
  })

  test('GET /api/health/ready returns 200 with status field', async ({
    request,
  }) => {
    const response = await request.get('/api/health/ready')
    expect(response.status()).toBe(200)

    const body = await response.json()
    // Status can be "ready" or "not_ready" depending on backend state
    expect(body.status).toBeDefined()
    expect(['ready', 'not_ready']).toContain(body.status)
  })

  test('GET /api/settings/presets returns valid presets JSON', async ({
    request,
  }) => {
    const response = await request.get('/api/settings/presets')
    expect(response.status()).toBe(200)

    const body = await response.json()
    expect(body).toHaveProperty('presets')
    expect(typeof body.presets).toBe('object')
  })

  test('GET /api/auth/captcha returns captcha_id', async ({ request }) => {
    const response = await request.get('/api/auth/captcha')
    expect(response.status()).toBe(200)

    const body = await response.json()
    expect(body).toHaveProperty('captcha_id')
    expect(body).toHaveProperty('question')
    expect(typeof body.captcha_id).toBe('string')
    expect(body.captcha_id.length).toBeGreaterThan(0)
  })
})
