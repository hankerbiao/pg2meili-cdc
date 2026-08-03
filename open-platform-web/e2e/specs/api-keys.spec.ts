import { expect, test } from '@playwright/test'
import { AppDetailPage } from '../pages'

/**
 * API Key 生命周期测试：创建、轮换、撤销（mock 层）。
 */

const session = { username: 'admin', csrf_token: 'csrf-test', expires_at: 4102444800 }
const app = {
  id: 'app-1', app_name: 'product_search', display_name: '商品搜索',
  owner_itcode: 'zhangsan', description: '商品目录与区域搜索',
  status: 'active', version: 1,
  created_at: '2026-07-30T08:00:00Z', updated_at: '2026-07-30T08:00:00Z',
}

test.describe('API Keys @mock', () => {
  let keyStatus: 'active' | 'revoked' = 'active'
  const key = {
    id: 'ak_0123456789abcdef', app_id: app.id, name: 'production',
    prefix: 'ud_live_ak_0123456789abcdef', last_four: 'z9Yx',
    scopes: ['search:read'], status: 'active' as string,
    expires_at: '2026-12-30T08:00:00Z', last_used_at: null, revoked_at: null,
    version: 1, created_at: '2026-07-30T08:00:00Z',
  }
  const secret = { ...key, api_key: 'ud_live_ak_0123456789abcdef.this-is-a-complete-test-secret-1234567890' }

  test.beforeEach(async ({ page }) => {
    keyStatus = 'active'
    await page.route('**/api/v1/open-platform/**', async (route) => {
      const request = route.request()
      const path = new URL(request.url()).pathname
      if (path.endsWith('/session')) return route.fulfill({ json: { data: session } })
      if (path.endsWith(`/apps/${app.id}/keys`)) {
        if (request.method() === 'POST') return route.fulfill({ status: 201, json: { data: secret } })
        return route.fulfill({ json: { data: [{ ...key, status: keyStatus, revoked_at: keyStatus === 'revoked' ? '2026-07-30T08:20:00Z' : null }] } })
      }
      if (path.endsWith(`/keys/${key.id}/rotate`)) return route.fulfill({ status: 201, json: { data: secret } })
      if (path.endsWith(`/keys/${key.id}/revoke`)) { keyStatus = 'revoked'; return route.fulfill({ json: { data: { ...key, status: keyStatus } } }) }
      if (path.endsWith(`/apps/${app.id}`)) return route.fulfill({ json: { data: app } })
      if (path.endsWith('/apps')) return route.fulfill({ json: { data: [app] } })
      return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
    })
  })

  test('创建 Key 并展示一次性密钥', async ({ page }) => {
    const detail = new AppDetailPage(page)
    await detail.goto(app.id)

    await detail.createKey({ name: 'staging' })
    await detail.expectSecretDialog()
    await expect(page.getByText(secret.api_key)).toBeVisible()

    // 关闭后密钥不可见
    await detail.closeSecretDialog()
    await expect(page.getByText(secret.api_key)).toHaveCount(0)
  })

  test('轮换 Key 展示新密钥', async ({ page }) => {
    const detail = new AppDetailPage(page)
    await detail.goto(app.id)

    await detail.rotateKey('production')
    await detail.expectSecretDialog()
    await detail.closeSecretDialog()
  })

  test('撤销 Key 后状态变为 Revoked', async ({ page }) => {
    const detail = new AppDetailPage(page)
    await detail.goto(app.id)

    await detail.revokeKey('production')
    await detail.expectKeyStatus('production', 'Revoked')
    // 撤销后操作按钮消失
    await expect(page.getByRole('button', { name: '轮换 production' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: '撤销 production' })).toHaveCount(0)
  })

  test('完整生命周期：创建 → 轮换 → 撤销 → 审计', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'desktop' && testInfo.project.name !== 'mock-desktop' && testInfo.project.name !== 'integration-desktop', '完整流程只在桌面项目执行')

    // 补充审计日志 mock
    await page.route('**/api/v1/open-platform/audit-logs*', (route) =>
      route.fulfill({
        json: {
          data: [{
            id: 'audit-1', actor: 'admin', action: 'key.rotate',
            target_type: 'api_key', target_id: key.id, app_id: app.id,
            source_ip: '127.0.0.1', details: null, created_at: '2026-07-30T08:10:00Z',
          }],
        },
      }),
    )

    const detail = new AppDetailPage(page)
    await detail.goto(app.id)

    // 创建
    await detail.createKey({ name: 'staging' })
    await detail.expectSecretDialog()
    await detail.closeSecretDialog()

    // 轮换
    await detail.rotateKey('production')
    await detail.expectSecretDialog()
    await detail.closeSecretDialog()

    // 撤销
    await detail.revokeKey('production')
    await detail.expectKeyStatus('production', 'Revoked')

    // 审计日志
    await page.getByRole('link', { name: '审计日志' }).click()
    await expect(page.getByRole('heading', { name: '审计日志' })).toBeVisible()
    await expect(page.getByText('key.rotate')).toBeVisible()
  })
})
