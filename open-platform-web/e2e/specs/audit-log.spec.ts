import { expect, test } from '@playwright/test'
import { AuditPage } from '../pages'

/**
 * 审计日志测试：筛选、分页、数据展示（mock 层）。
 */

const session = { username: 'admin', csrf_token: 'csrf-test', expires_at: 4102444800 }
const app = {
  id: 'app-1', app_name: 'product_search', display_name: '商品搜索',
  owner_itcode: 'zhangsan', description: '', status: 'active', version: 1,
  created_at: '2026-07-30T08:00:00Z', updated_at: '2026-07-30T08:00:00Z',
}

const logs = [
  { id: 'a1', actor: 'admin', action: 'session.login', target_type: 'session', target_id: null, app_id: null, source_ip: '10.0.0.1', details: null, created_at: '2026-07-30T09:00:00Z' },
  { id: 'a2', actor: 'admin', action: 'app.create', target_type: 'app', target_id: 'app-1', app_id: 'app-1', source_ip: '10.0.0.1', details: null, created_at: '2026-07-30T09:01:00Z' },
  { id: 'a3', actor: 'admin', action: 'key.create', target_type: 'api_key', target_id: 'ak_1', app_id: 'app-1', source_ip: '10.0.0.1', details: null, created_at: '2026-07-30T09:02:00Z' },
  { id: 'a4', actor: 'admin', action: 'key.rotate', target_type: 'api_key', target_id: 'ak_1', app_id: 'app-1', source_ip: '10.0.0.2', details: null, created_at: '2026-07-30T09:03:00Z' },
  { id: 'a5', actor: 'admin', action: 'key.revoke', target_type: 'api_key', target_id: 'ak_1', app_id: 'app-1', source_ip: '10.0.0.2', details: null, created_at: '2026-07-30T09:04:00Z' },
]

test.describe('Audit Log @mock', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/v1/open-platform/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/session')) return route.fulfill({ json: { data: session } })
      if (path.endsWith('/apps')) return route.fulfill({ json: { data: [app] } })
      if (path.includes('/audit-logs')) {
        const url = new URL(route.request().url())
        const action = url.searchParams.get('action')
        const filtered = action ? logs.filter((l) => l.action === action) : logs
        return route.fulfill({ json: { data: filtered } })
      }
      return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
    })
  })

  test('默认加载全部日志', async ({ page }) => {
    const audit = new AuditPage(page)
    await audit.goto()

    const rows = await audit.getRowCount()
    expect(rows).toBe(5)
    await audit.expectContainsAction('session.login')
    await audit.expectContainsAction('key.revoke')
  })

  test('按动作筛选', async ({ page }) => {
    const audit = new AuditPage(page)
    await audit.goto()

    await audit.filterByAction('key.rotate')
    const rows = await audit.getRowCount()
    expect(rows).toBe(1)
    await audit.expectContainsAction('key.rotate')
  })

  test('重置筛选恢复全部', async ({ page }) => {
    const audit = new AuditPage(page)
    await audit.goto()

    await audit.filterByAction('key.rotate')
    await audit.resetFilters()
    const rows = await audit.getRowCount()
    expect(rows).toBe(5)
  })

  test('表格列数据正确', async ({ page }) => {
    const audit = new AuditPage(page)
    await audit.goto()

    // 验证第一行数据
    const firstRow = audit.logTable.locator('tbody tr').first()
    await expect(firstRow).toContainText('admin')
    await expect(firstRow).toContainText('session.login')
    await expect(firstRow).toContainText('10.0.0.1')
  })

  test('空结果显示引导', async ({ page }) => {
    await page.route('**/api/v1/open-platform/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/session')) return route.fulfill({ json: { data: session } })
      if (path.endsWith('/apps')) return route.fulfill({ json: { data: [app] } })
      if (path.includes('/audit-logs')) return route.fulfill({ json: { data: [] } })
      return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
    })
    const audit = new AuditPage(page)
    await audit.goto()
    await expect(page.getByText('没有匹配的记录')).toBeVisible()
  })
})
