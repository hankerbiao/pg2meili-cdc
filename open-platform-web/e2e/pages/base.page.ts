import { type Locator, type Page, expect } from '@playwright/test'

/**
 * 所有 Page Object 的基类，封装通用导航和等待逻辑。
 */
export class BasePage {
  constructor(protected readonly page: Page) {}

  /** 等待页面脱离 loading 状态 */
  async waitForReady() {
    await this.page.waitForLoadState('networkidle')
  }

  /** 断言当前 URL 包含指定路径 */
  async expectURLContains(segment: string) {
    await expect(this.page).toHaveURL(new RegExp(segment))
  }

  /** 获取顶部导航栏 */
  get siteNav(): Locator {
    return this.page.locator('.site-nav')
  }

  /** 点击顶部导航中的链接 */
  async navTo(name: string | RegExp) {
    await this.page.getByRole('link', { name }).first().click()
  }
}
