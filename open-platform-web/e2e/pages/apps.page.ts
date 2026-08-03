import { type Locator, type Page, expect } from '@playwright/test'
import { BasePage } from './base.page'

export class AppsPage extends BasePage {
  readonly heading: Locator
  readonly createBtn: Locator
  readonly appTable: Locator
  readonly metricStrip: Locator
  readonly emptyState: Locator

  constructor(page: Page) {
    super(page)
    this.heading = page.getByRole('heading', { name: '应用与 API Keys' })
    this.createBtn = page.getByRole('button', { name: '新建应用' }).first()
    this.appTable = page.locator('.data-table')
    this.metricStrip = page.locator('.metric-strip')
    this.emptyState = page.locator('.empty-state')
  }

  async goto() {
    await this.page.goto('console/apps')
    await expect(this.heading).toBeVisible()
  }

  /** 打开新建应用弹窗 */
  async openCreateDialog() {
    await this.createBtn.click()
    await expect(this.page.getByRole('heading', { name: '新建应用' })).toBeVisible()
  }

  /** 填写新建应用表单并提交 */
  async createApp(opts: {
    displayName: string
    appName: string
    owner: string
    profile?: 'frontend' | 'backend'
    description?: string
  }) {
    await this.openCreateDialog()
    await this.page.getByLabel('显示名称').fill(opts.displayName)
    await this.page.getByLabel('应用标识').fill(opts.appName)
    await this.page.getByLabel('负责人 itcode').fill(opts.owner)
    if (opts.profile === 'backend') {
      await this.page.getByRole('radio', { name: /仅后端读写/ }).check()
    }
    if (opts.description) {
      await this.page.getByLabel('描述').fill(opts.description)
    }
    await this.page.getByRole('button', { name: '创建应用与 Key' }).click()
  }

  /** 获取表格中指定应用行 */
  getAppRow(name: string): Locator {
    return this.appTable.getByRole('row').filter({ hasText: name })
  }

  /** 点击应用名进入详情 */
  async openApp(name: string) {
    await this.getAppRow(name).getByRole('link').first().click()
  }

  /** 断言指标条数字 */
  async expectMetrics(total: number, active: number, disabled: number) {
    const items = this.metricStrip.locator('div')
    await expect(items.nth(0)).toContainText(String(total))
    await expect(items.nth(1)).toContainText(String(active))
    await expect(items.nth(2)).toContainText(String(disabled))
  }

  /** 断言密钥弹窗出现并返回完整 key */
  async expectSecretDialog(): Promise<string> {
    await expect(this.page.getByRole('heading', { name: /保存你的 API Keys?/ })).toBeVisible()
    const secretText = await this.page.locator('.secret-display code, .secret-display').innerText()
    return secretText.trim()
  }

  /** 关闭密钥弹窗 */
  async closeSecretDialog() {
    await this.page.getByRole('button', { name: '我已保存，关闭' }).click()
  }
}
