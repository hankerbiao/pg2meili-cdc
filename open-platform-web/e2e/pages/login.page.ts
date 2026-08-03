import { type Locator, type Page, expect } from '@playwright/test'
import { BasePage } from './base.page'

export class LoginPage extends BasePage {
  readonly usernameInput: Locator
  readonly passwordInput: Locator
  readonly submitBtn: Locator
  readonly errorAlert: Locator
  readonly heading: Locator

  constructor(page: Page) {
    super(page)
    this.usernameInput = page.getByLabel('账号')
    this.passwordInput = page.getByLabel('密码')
    this.submitBtn = page.getByRole('button', { name: /进入控制台/ })
    this.errorAlert = page.getByRole('alert')
    this.heading = page.getByRole('heading', { name: '管理员登录' })
  }

  async goto() {
    await this.page.goto('login')
    await expect(this.heading).toBeVisible()
  }

  async login(username: string, password: string) {
    await this.usernameInput.fill(username)
    await this.passwordInput.fill(password)
    await this.submitBtn.click()
  }

  async expectError(message: string | RegExp) {
    await expect(this.errorAlert).toBeVisible()
    await expect(this.errorAlert).toContainText(message)
  }

  async expectRedirectToConsole() {
    await this.page.waitForURL('**/console/apps', { timeout: 10_000 })
  }
}
