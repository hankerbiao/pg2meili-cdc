import { expect, test } from '@playwright/test'
import { DocsPage, LoginPage, AppsPage } from '../pages'
import { mockLoginFlow } from '../utils/mock-platform'

/**
 * 冒烟测试：验证核心路径可用。
 * 使用 mock API，无后端依赖。
 */

const app = {
  id: 'app-1', app_name: 'product_search', display_name: '商品搜索',
  owner_itcode: 'zhangsan', description: '商品目录与区域搜索',
  status: 'active', version: 1,
  created_at: '2026-07-30T08:00:00Z', updated_at: '2026-07-30T08:00:00Z',
}

test.describe('Smoke @mock @smoke', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/openapi.json', (route) =>
      route.fulfill({
        json: {
          paths: {
            '/api/v1/data/{collection}': {
              post: { operationId: 'write', summary: '写入文档', description: '创建或更新文档', tags: ['generic-data'] },
            },
            '/api/v1/open-platform/apps': {
              get: { operationId: 'apps', tags: ['open-platform'] },
            },
          },
        },
      }),
    )
  })

  test('首页重定向到 quickstart 文档', async ({ page }) => {
    const docs = new DocsPage(page)
    await page.goto('')
    await page.waitForURL('**/docs/quickstart')
    await expect(page.getByRole('heading', { name: '用一把 Key，连接数据与搜索' })).toBeVisible()
  })

  test('未登录访问控制台跳转登录页', async ({ page }) => {
    await page.route('**/api/v1/open-platform/**', (route) =>
      route.fulfill({ status: 401, json: { message: '请先登录开放平台', data: null } }),
    )
    const login = new LoginPage(page)
    await page.goto('console/apps')
    await expect(login.heading).toBeVisible()
  })

  test('正确密码登录后进入控制台', async ({ page }) => {
    await mockLoginFlow(page, (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/apps')) return route.fulfill({ json: { data: [app] } })
      return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
    })
    const login = new LoginPage(page)
    await login.goto()
    await login.login('admin', 'password')
    await login.expectRedirectToConsole()

    const apps = new AppsPage(page)
    await expect(apps.heading).toBeVisible()
    await expect(page.getByText('商品搜索')).toBeVisible()
  })

  test('文档站和 API Reference 无需登录', async ({ page }) => {
    const docs = new DocsPage(page)
    await docs.gotoQuickstart()
    await docs.switchCodeTab('Python')
    await docs.expectCodeContains('from unidata_sdk import UniDataClient')

    await docs.gotoApiReference()
    await docs.expectApiVisible('写入文档')
    await docs.expectApiHidden('/api/v1/open-platform/apps')
  })
})
