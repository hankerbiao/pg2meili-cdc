import { expect, test } from '@playwright/test'
import { DocsPage } from '../pages'

/**
 * 文档站测试：导航、代码块、SDK 下载、API Reference 过滤。
 */

test.describe('Docs @mock', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/openapi.json', (route) =>
      route.fulfill({
        json: {
          paths: {
            '/api/v1/data/{collection}': {
              post: { operationId: 'write', summary: '写入文档', description: '创建或更新文档', tags: ['generic-data'] },
            },
            '/api/v1/search': {
              get: { operationId: 'search', summary: '搜索数据', description: '全文搜索', tags: ['generic-data'] },
            },
            '/api/v1/open-platform/apps': {
              get: { operationId: 'apps', tags: ['open-platform'] },
            },
            '/api/v1/open-platform/session': {
              post: { operationId: 'login', tags: ['open-platform'] },
            },
          },
        },
      }),
    )
  })

  test('Quickstart 页面代码块语言切换', async ({ page }, testInfo) => {
    const docs = new DocsPage(page)
    await docs.gotoQuickstart()

    // 默认 curl
    await docs.expectCodeContains('curl')

    // 切换 Python
    await docs.switchCodeTab('Python')
    await docs.expectCodeContains('from unidata_sdk import UniDataClient')

    await page.screenshot({ path: `e2e/test-results/${testInfo.project.name}-quickstart.png`, fullPage: true })
  })

  test('Python SDK 页面展示下载链接', async ({ page }, testInfo) => {
    const docs = new DocsPage(page)
    await docs.gotoPythonSdk()

    await expect(page.getByRole('heading', { name: '常用独立接口' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '通用 request 接口' })).toBeVisible()
    await docs.expectSdkDownloadLink()

    await page.screenshot({ path: `e2e/test-results/${testInfo.project.name}-python-sdk.png`, fullPage: true })
  })

  test('API Reference 只展示公开 tag 的接口', async ({ page }) => {
    const docs = new DocsPage(page)
    await docs.gotoApiReference()

    // 公开接口可见
    await docs.expectApiVisible('写入文档')
    await docs.expectApiVisible('搜索数据')

    // 内部管理接口不可见
    await docs.expectApiHidden('/api/v1/open-platform/apps')
    await docs.expectApiHidden('/api/v1/open-platform/session')
  })

  test('侧边栏导航链接正确', async ({ page }) => {
    await page.goto('docs/quickstart')
    const sidebar = page.locator('.docs-sidebar')

    await expect(sidebar.getByRole('link', { name: /Quickstart|快速开始/ })).toBeVisible()
    await expect(sidebar.getByRole('link', { name: /Python SDK/ })).toBeVisible()
    await expect(sidebar.getByRole('link', { name: /API Reference/ })).toBeVisible()
  })
})
