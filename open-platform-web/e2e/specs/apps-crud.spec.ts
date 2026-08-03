import { expect, test } from '@playwright/test'
import { AppsPage } from '../pages'

/**
 * 应用管理 CRUD 测试（mock 层）。
 */

const session = { username: 'admin', csrf_token: 'csrf-test', expires_at: 4102444800 }
const app = {
  id: 'app-1', app_name: 'product_search', display_name: '商品搜索',
  owner_itcode: 'zhangsan', description: '商品目录与区域搜索',
  status: 'active', version: 1,
  created_at: '2026-07-30T08:00:00Z', updated_at: '2026-07-30T08:00:00Z',
}
const frontendSecret = {
  id: 'ak_frontend', app_id: 'app-1', name: 'frontend-search',
  prefix: 'ud_live_ak_frontend', last_four: 'Ab12',
  scopes: ['search:read'], status: 'active',
  expires_at: '2026-12-30T08:00:00Z', last_used_at: null, revoked_at: null,
  version: 1, created_at: '2026-07-30T08:00:00Z',
  api_key: 'ud_live_ak_frontend.full-frontend-secret',
}
const backendSecret = {
  ...frontendSecret,
  id: 'ak_backend', name: 'backend-data', prefix: 'ud_live_ak_backend', last_four: 'Cd34',
  scopes: ['data:read', 'data:write'],
  api_key: 'ud_live_ak_backend.full-backend-secret',
}

test.describe('Apps CRUD @mock', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/v1/open-platform/**', async (route) => {
      const request = route.request()
      const path = new URL(request.url()).pathname
      if (path.endsWith('/session')) return route.fulfill({ json: { data: session } })
      if (path.endsWith('/apps/bootstrap') && request.method() === 'POST') {
        const body = request.postDataJSON()
        const keys = body.initial_keys.length === 1 ? [backendSecret] : [frontendSecret, backendSecret]
        return route.fulfill({ status: 201, json: { data: { app, keys } } })
      }
      if (path.endsWith('/apps')) return route.fulfill({ json: { data: [app] } })
      return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
    })
  })

  test('应用列表展示正确数据', async ({ page }) => {
    const apps = new AppsPage(page)
    await apps.goto()

    await expect(apps.getAppRow('商品搜索')).toBeVisible()
    await expect(page.getByText('product_search')).toBeVisible()
    await expect(page.getByText('zhangsan')).toBeVisible()
    await expect(page.getByText('Active')).toBeVisible()
  })

  test('指标条统计数字正确', async ({ page }) => {
    const apps = new AppsPage(page)
    await apps.goto()
    await apps.expectMetrics(1, 1, 0)
  })

  test('默认创建应用并展示两把密钥', async ({ page }) => {
    const apps = new AppsPage(page)
    await apps.goto()
    await apps.createApp({
      displayName: '商品搜索',
      appName: 'product_search',
      owner: 'zhangsan',
      profile: 'frontend',
    })

    // 密钥弹窗
    await expect(page.getByRole('heading', { name: '保存你的 API Keys' })).toBeVisible()
    await expect(page.getByText(frontendSecret.api_key)).toBeVisible()
    await expect(page.getByText(backendSecret.api_key)).toBeVisible()
    await apps.closeSecretDialog()
    await expect(page.getByText(frontendSecret.api_key)).toHaveCount(0)
    await expect(page.getByText(backendSecret.api_key)).toHaveCount(0)
    await expect(apps.getAppRow('商品搜索')).toBeVisible()
  })

  test('可选择仅创建后端读写密钥', async ({ page }) => {
    const apps = new AppsPage(page)
    await apps.goto()
    await apps.createApp({
      displayName: '商品搜索',
      appName: 'product_search',
      owner: 'zhangsan',
      profile: 'backend',
    })

    await expect(page.getByRole('heading', { name: '保存你的 API Key' })).toBeVisible()
    await expect(page.getByText(backendSecret.api_key)).toBeVisible()
    await expect(page.getByText(frontendSecret.api_key)).toHaveCount(0)
  })

  test('点击应用名进入详情页', async ({ page }) => {
    await page.route('**/api/v1/open-platform/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/session')) return route.fulfill({ json: { data: session } })
      if (path.endsWith('/apps/app-1/keys')) return route.fulfill({ json: { data: [] } })
      if (path.endsWith('/apps/app-1')) return route.fulfill({ json: { data: app } })
      if (path.endsWith('/apps')) return route.fulfill({ json: { data: [app] } })
      return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
    })
    const apps = new AppsPage(page)
    await apps.goto()
    await apps.openApp('商品搜索')
    await page.waitForURL('**/console/apps/app-1')
    await expect(page.getByRole('heading', { name: '商品搜索' })).toBeVisible()
  })

  test('空列表展示引导状态', async ({ page }) => {
    await page.route('**/api/v1/open-platform/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/session')) return route.fulfill({ json: { data: session } })
      if (path.endsWith('/apps')) return route.fulfill({ json: { data: [] } })
      return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
    })
    const apps = new AppsPage(page)
    await apps.goto()
    await expect(apps.emptyState).toBeVisible()
    await expect(page.getByText('创建第一个应用')).toBeVisible()
  })
})
