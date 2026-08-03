import { expect, test } from '@playwright/test'

/**
 * 响应式测试：移动端/平板布局适配。
 * 仅在 mobile 和 tablet 项目中运行。
 */

const session = { username: 'admin', csrf_token: 'csrf-test', expires_at: 4102444800 }
const app = {
  id: 'app-1', app_name: 'product_search', display_name: '商品搜索',
  owner_itcode: 'zhangsan', description: '商品目录与区域搜索',
  status: 'active', version: 1,
  created_at: '2026-07-30T08:00:00Z', updated_at: '2026-07-30T08:00:00Z',
}

test.describe('Responsive @mock @responsive', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/v1/open-platform/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/session')) return route.fulfill({ json: { data: session } })
      if (path.endsWith('/apps')) return route.fulfill({ json: { data: [app] } })
      if (path.endsWith('/apps/app-1/keys')) return route.fulfill({ json: { data: [] } })
      if (path.endsWith('/apps/app-1')) return route.fulfill({ json: { data: app } })
      return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
    })
    await page.route('**/openapi.json', (route) =>
      route.fulfill({ json: { paths: {} } }),
    )
  })

  test('文档页在小屏正常渲染', async ({ page }, testInfo) => {
    await page.goto('docs/quickstart')
    await expect(page.getByRole('heading', { name: '用一把 Key，连接数据与搜索' })).toBeVisible()
    // 内容不溢出视口
    const body = page.locator('body')
    const box = await body.boundingBox()
    const viewport = page.viewportSize()!
    expect(box!.width).toBeLessThanOrEqual(viewport.width + 1)
  })

  test('控制台表格在小屏可滚动', async ({ page }, testInfo) => {
    await page.goto('console/apps')
    await expect(page.getByRole('heading', { name: '应用与 API Keys' })).toBeVisible()
    // 表格容器存在且可滚动
    const tableScroll = page.locator('.table-scroll')
    if (await tableScroll.isVisible()) {
      const overflow = await tableScroll.evaluate((el) => getComputedStyle(el).overflowX)
      expect(['auto', 'scroll']).toContain(overflow)
    }
  })

  test('弹窗不溢出小屏视口', async ({ page }, testInfo) => {
    await page.goto('console/apps')
    await page.getByRole('button', { name: '新建应用' }).first().click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    const box = await dialog.boundingBox()
    const viewport = page.viewportSize()!
    expect(box!.width).toBeLessThanOrEqual(viewport.width)
    expect(box!.x).toBeGreaterThanOrEqual(0)
  })

  test('登录页在小屏正常展示', async ({ page }) => {
    await page.route('**/api/v1/open-platform/session', (route) =>
      route.fulfill({ status: 401, json: { message: '未登录', data: null } }),
    )
    await page.goto('login')
    await expect(page.getByRole('heading', { name: '管理员登录' })).toBeVisible()
    // 表单可见且可交互
    await expect(page.getByLabel('密码')).toBeVisible()
    await expect(page.getByRole('button', { name: /进入控制台/ })).toBeVisible()
  })
})
