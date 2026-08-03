import { expect, test } from '@playwright/test'

test.describe('Integration @integration', () => {
  test.skip(!process.env.PLATFORM_PASSWORD, '需要 PLATFORM_PASSWORD 和可访问的真实后端')

  test('真实登录态可以加载应用控制台', async ({ page }) => {
    const sessionResponse = await page.request.get('/api/v1/open-platform/session')
    expect(sessionResponse.status()).toBe(200)

    await page.goto('console/apps')
    await expect(page.getByRole('heading', { name: '应用与 API Keys' })).toBeVisible()
    await expect(page.locator('.data-table, .empty-state')).toBeVisible()
    await expect(page.getByRole('heading', { name: '管理员登录' })).toHaveCount(0)
  })
})
