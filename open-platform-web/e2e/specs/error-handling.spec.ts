import { expect, test } from '@playwright/test'
import { AppsPage } from '../pages'

/**
 * 异常处理测试：网络错误、500、超时、404（mock 层）。
 */

const session = { username: 'admin', csrf_token: 'csrf-test', expires_at: 4102444800 }

test.describe('Error Handling @mock', () => {
  test.beforeEach(async ({ page }) => {
    // 默认登录态
    await page.route('**/api/v1/open-platform/session', (route) =>
      route.fulfill({ json: { data: session } }),
    )
  })

  test('网络中断时显示错误而非白屏', async ({ page }) => {
    await page.route('**/api/v1/open-platform/apps', (route) => route.abort('connectionrefused'))
    const apps = new AppsPage(page)
    await page.goto('console/apps')
    // 页面不白屏，显示错误信息
    await expect(apps.heading).toBeVisible()
    await expect(page.locator('.inline-error')).toBeVisible()
  })

  test('后端 500 显示友好错误', async ({ page }) => {
    await page.route('**/api/v1/open-platform/apps', (route) =>
      route.fulfill({ status: 500, json: { message: '内部服务器错误', data: null } }),
    )
    const apps = new AppsPage(page)
    await page.goto('console/apps')
    await expect(apps.heading).toBeVisible()
    await expect(page.locator('.inline-error')).toContainText('内部服务器错误')
  })

  test('访问不存在的 appId 显示错误提示', async ({ page }) => {
    await page.route('**/api/v1/open-platform/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/session')) return route.fulfill({ json: { data: session } })
      if (path.includes('/apps/nonexistent')) return route.fulfill({ status: 404, json: { message: '应用不存在', data: null } })
      return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
    })
    await page.goto('console/apps/nonexistent')
    await expect(page.getByText(/不存在|加载失败/)).toBeVisible()
  })

  test('创建应用失败显示表单错误', async ({ page }) => {
    await page.route('**/api/v1/open-platform/**', async (route) => {
      const request = route.request()
      const path = new URL(request.url()).pathname
      if (path.endsWith('/session')) return route.fulfill({ json: { data: session } })
      if (path.endsWith('/apps/bootstrap') && request.method() === 'POST') {
        return route.fulfill({ status: 409, json: { message: '应用标识已存在', data: null } })
      }
      if (path.endsWith('/apps')) return route.fulfill({ json: { data: [] } })
      return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
    })
    const apps = new AppsPage(page)
    await apps.goto()
    await apps.createApp({ displayName: '重复应用', appName: 'product_search', owner: 'zhangsan' })
    await expect(page.locator('.form-error')).toContainText('应用标识已存在')
  })
})
