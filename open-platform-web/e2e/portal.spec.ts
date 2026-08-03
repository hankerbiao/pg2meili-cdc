import { expect, test } from '@playwright/test'

const session = { username: 'admin', csrf_token: 'csrf-test', expires_at: 4102444800 }
const app = { id: 'app-1', app_name: 'product_search', display_name: '商品搜索', owner_itcode: 'zhangsan', description: '商品目录与区域搜索', status: 'active', version: 1, created_at: '2026-07-30T08:00:00Z', updated_at: '2026-07-30T08:00:00Z' }

test.beforeEach(async ({ page }) => {
  await page.route('**/openapi.json', (route) => route.fulfill({ json: { paths: { '/api/v1/data/{collection}': { post: { operationId: 'write', summary: '写入文档', description: '创建或更新文档', tags: ['generic-data'] } }, '/api/v1/open-platform/apps': { get: { operationId: 'apps', tags: ['open-platform'] } } } } }))
  await page.route('**/api/v1/open-platform/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/session')) return route.fulfill({ status: 401, json: { message: '请先登录开放平台', data: null } })
    return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
  })
})

test('public docs and filtered API reference are available without login', async ({ page }, testInfo) => {
  await page.goto('docs/quickstart')
  await expect(page.getByRole('heading', { name: '用一把 Key，连接数据与搜索' })).toBeVisible()
  await page.getByRole('tab', { name: 'Python' }).first().click()
  await expect(page.getByText('from unidata_sdk import UniDataClient').first()).toBeVisible()
  await page.screenshot({ path: `test-results/${testInfo.project.name}-quickstart.png`, fullPage: true })
  await page.getByRole('link', { name: /API Reference/ }).first().click()
  await expect(page.getByText('写入文档')).toBeVisible()
  await expect(page.getByText('/api/v1/open-platform/apps')).toHaveCount(0)
})

test('Python SDK documentation exposes an installable download', async ({ page }, testInfo) => {
  await page.goto('docs/python-sdk')
  await expect(page.getByRole('heading', { name: '用 Python 接入 UniData' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '常用独立接口' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '通用 request 接口' })).toBeVisible()
  await expect(page.getByRole('link', { name: /下载 Python SDK/ })).toHaveAttribute('href', '/api/v1/sdk/python/download')
  await page.screenshot({ path: `test-results/${testInfo.project.name}-python-sdk.png`, fullPage: true })
})

test('protected console shows login and then application data', async ({ page }, testInfo) => {
  await page.goto('console/apps')
  await expect(page.getByRole('heading', { name: '管理员登录' })).toBeVisible()
  await page.unroute('**/api/v1/open-platform/**')
  await page.route('**/api/v1/open-platform/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/session')) return route.fulfill({ json: { data: session } })
    if (path.endsWith('/apps')) return route.fulfill({ json: { data: [app] } })
    return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
  })
  await page.getByLabel('账号').fill('admin')
  await page.getByLabel('密码').fill('password')
  await page.getByRole('button', { name: /进入控制台/ }).click()
  await expect(page.getByRole('heading', { name: '应用与 API Keys' })).toBeVisible()
  await expect(page.getByText('商品搜索')).toBeVisible()
  await page.screenshot({ path: `test-results/${testInfo.project.name}-console.png`, fullPage: true })
})

test('creating an application selects permissions and updates without refresh', async ({ page }, testInfo) => {
  await page.unroute('**/api/v1/open-platform/**')
  let apps: typeof app[] = []
  const key = {
    id: 'ak_created',
    app_id: app.id,
    name: 'backend-data',
    prefix: 'ud_live_ak_created',
    last_four: 'z9Yx',
    scopes: ['data:read', 'data:write'],
    status: 'active',
    expires_at: '2026-12-30T08:00:00Z',
    last_used_at: null,
    revoked_at: null,
    version: 1,
    created_at: '2026-07-30T08:00:00Z',
    api_key: 'ud_live_ak_created.complete-browser-test-secret',
  }
  await page.route('**/api/v1/open-platform/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/session')) return route.fulfill({ json: { data: session } })
    if (path.endsWith('/apps/bootstrap')) {
      const body = request.postDataJSON()
      expect(body.initial_keys).toHaveLength(1)
      expect(body.initial_keys[0].scopes).toEqual(['data:read', 'data:write'])
      apps = [app]
      return route.fulfill({ status: 201, json: { data: { app, keys: [key] } } })
    }
    if (path.endsWith('/apps')) return route.fulfill({ json: { data: apps } })
    return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
  })

  await page.goto('console/apps')
  await page.getByRole('button', { name: '新建应用' }).first().click()
  await page.getByLabel('显示名称').fill(app.display_name)
  await page.getByLabel('应用标识').fill(app.app_name)
  await page.getByLabel('负责人 itcode').fill(app.owner_itcode)
  await page.getByRole('radio', { name: /仅后端读写/ }).click()
  await expect(page.getByRole('radio', { name: /仅后端读写/ })).toBeChecked()
  await page.screenshot({ path: `test-results/${testInfo.project.name}-create-app-form.png`, fullPage: true })
  await page.getByRole('button', { name: '创建应用与 Key' }).click()

  await expect(page.getByRole('heading', { name: '保存你的 API Key' })).toBeVisible()
  await expect(page.getByText(key.api_key)).toBeVisible()
  await expect(page.getByText(app.display_name)).toBeVisible()
  await page.screenshot({ path: `test-results/${testInfo.project.name}-create-app.png`, fullPage: true })
})

test('API Key lifecycle and audit workflow', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', '完整管理流程只在桌面项目执行')
  await page.unroute('**/api/v1/open-platform/**')
  let keyStatus: 'active' | 'revoked' = 'active'
  const key = { id: 'ak_0123456789abcdef', app_id: app.id, name: 'production', prefix: 'ud_live_ak_0123456789abcdef', last_four: 'z9Yx', scopes: ['search:read'], status: keyStatus, expires_at: '2026-12-30T08:00:00Z', last_used_at: null, revoked_at: null, version: 1, created_at: '2026-07-30T08:00:00Z' }
  const secret = { ...key, api_key: 'ud_live_ak_0123456789abcdef.this-is-a-complete-test-secret-1234567890' }
  await page.route('**/api/v1/open-platform/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/session')) return route.fulfill({ json: { data: session } })
    if (path.endsWith('/audit-logs')) return route.fulfill({ json: { data: [{ id: 'audit-1', actor: 'admin', action: 'key.rotate', target_type: 'api_key', target_id: key.id, app_id: app.id, source_ip: '127.0.0.1', details: null, created_at: '2026-07-30T08:10:00Z' }] } })
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

  await page.goto(`console/apps/${app.id}`)
  await expect(page.getByRole('heading', { name: '商品搜索' })).toBeVisible()
  await page.getByRole('button', { name: '创建 API Key' }).click()
  await page.getByLabel('Key 名称').fill('staging')
  await page.getByRole('button', { name: '创建密钥' }).click()
  await expect(page.getByRole('heading', { name: '保存你的 API Key' })).toBeVisible()
  await expect(page.getByText(secret.api_key)).toBeVisible()
  await page.getByRole('button', { name: '我已保存，关闭' }).click()
  await expect(page.getByText(secret.api_key)).toHaveCount(0)

  await page.getByRole('button', { name: '轮换 production' }).click()
  await page.getByRole('button', { name: '确认轮换' }).click()
  await expect(page.getByRole('heading', { name: '保存你的 API Key' })).toBeVisible()
  await page.getByRole('button', { name: '我已保存，关闭' }).click()

  await page.getByRole('button', { name: '撤销 production' }).click()
  await page.getByRole('button', { name: '确认撤销' }).click()
  await expect(page.getByText('Revoked')).toBeVisible()
  await page.getByRole('link', { name: '审计日志' }).click()
  await expect(page.getByRole('heading', { name: '审计日志' })).toBeVisible()
  await expect(page.getByText('key.rotate')).toBeVisible()
})
