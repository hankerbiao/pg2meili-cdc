import { type Locator, type Page, expect } from '@playwright/test'
import { BasePage } from './base.page'

export class DocsPage extends BasePage {
  readonly sidebar: Locator

  constructor(page: Page) {
    super(page)
    this.sidebar = page.locator('.docs-sidebar')
  }

  async gotoQuickstart() {
    await this.page.goto('docs/quickstart')
    await expect(this.page.getByRole('heading', { name: '用一把 Key，连接数据与搜索' })).toBeVisible()
  }

  async gotoAuthentication() {
    await this.page.goto('docs/authentication')
    await expect(this.page.getByRole('heading', { name: /认证/ })).toBeVisible()
  }

  async gotoPythonSdk() {
    await this.page.goto('docs/python-sdk')
    await expect(this.page.getByRole('heading', { name: '用 Python 接入 UniData' })).toBeVisible()
  }

  async gotoApiReference() {
    await this.page.goto('docs/api-reference')
    await this.waitForReady()
  }

  /** 切换代码块语言 tab */
  async switchCodeTab(language: string) {
    await this.page.getByRole('tab', { name: language }).first().click()
  }

  /** 断言代码块包含文本 */
  async expectCodeContains(text: string) {
    await expect(this.page.getByText(text).first()).toBeVisible()
  }

  /** 断言 API Reference 中可见指定操作 */
  async expectApiVisible(summary: string) {
    await expect(this.page.getByText(summary)).toBeVisible()
  }

  /** 断言 API Reference 中不存在指定内容 */
  async expectApiHidden(text: string) {
    await expect(this.page.getByText(text)).toHaveCount(0)
  }

  /** 断言 Python SDK 下载链接 */
  async expectSdkDownloadLink() {
    const link = this.page.getByRole('link', { name: /下载 Python SDK/ })
    await expect(link).toHaveAttribute('href', '/api/v1/sdk/python/download')
  }
}
