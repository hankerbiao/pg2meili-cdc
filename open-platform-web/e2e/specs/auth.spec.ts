import { expect, test } from '@playwright/test'
import { LoginPage, AppsPage } from '../pages'
import { mockLoginFlow } from '../utils/mock-platform'

/**
 * 认证流程测试：登录/登出/Session 过期/CSRF/路由守卫。
 */

test.describe('Auth @mock', () => {
  test('空密码提交触发表单校验', async ({ page }) => {
    await mockLoginFlow(page)
    const login = new LoginPage(page)
    await login.goto()
    // HTML5 required 校验：按钮点击后不跳转
    await login.usernameInput.fill('admin')
    await login.submitBtn.click()
    // 仍在登录页
    await expect(login.heading).toBeVisible()
  })

  test('错误密码显示错误提示', async ({ page }) => {
    await page.route('**/api/v1/open-platform/session', (route) => {
      if (route.request().method() === 'POST') {
        return route.fulfill({ status: 401, json: { message: '密码错误', data: null } })
      }
      return route.fulfill({ status: 401, json: { message: '未登录', data: null } })
    })
    const login = new LoginPage(page)
    await login.goto()
    await login.login('admin', 'wrong-password')
    await login.expectError('密码错误')
  })

  test('正确密码登录成功并跳转控制台', async ({ page }) => {
    await mockLoginFlow(page, (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/apps')) return route.fulfill({ json: { data: [] } })
      return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
    })
    const login = new LoginPage(page)
    await login.goto()
    await login.login('admin', 'correct-password')
    await login.expectRedirectToConsole()
  })

  test('?next= 参数登录后跳回原页面', async ({ page }) => {
    await mockLoginFlow(page, (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/audit-logs')) return route.fulfill({ json: { data: [] } })
      if (path.endsWith('/apps')) return route.fulfill({ json: { data: [] } })
      return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
    })
    const login = new LoginPage(page)
    await page.goto('login?next=/console/audit')
    await expect(login.heading).toBeVisible()
    await login.login('admin', 'password')
    await page.waitForURL('**/console/audit', { timeout: 10_000 })
  })

  test('Session 过期（401）自动跳转登录页', async ({ page }) => {
    const session = await mockLoginFlow(page, (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/apps')) return route.fulfill({ json: { data: [] } })
      return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
    })
    const login = new LoginPage(page)
    await login.goto()
    await login.login('admin', 'password')
    await login.expectRedirectToConsole()

    session.expire()
    await page.reload()
    await expect(page.getByRole('heading', { name: '管理员登录' })).toBeVisible()
  })

  test('登出后清除会话并回到公开文档', async ({ page }) => {
    await mockLoginFlow(page, (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/apps')) return route.fulfill({ json: { data: [] } })
      return route.fulfill({ status: 404, json: { message: 'not found', data: null } })
    })
    const login = new LoginPage(page)
    await login.goto()
    await login.login('admin', 'password')
    await login.expectRedirectToConsole()

    // 点击登出
    await page.getByRole('button', { name: /退出|登出|Logout/ }).click()
    await expect(page).toHaveURL(/\/docs\/quickstart$/)
    await expect(page.getByRole('link', { name: '登录控制台' })).toBeVisible()
    await expect(page.getByRole('button', { name: /退出|登出|Logout/ })).toHaveCount(0)
  })
})
