import { type Locator, type Page, expect } from '@playwright/test'
import { BasePage } from './base.page'

export class AuditPage extends BasePage {
  readonly heading: Locator
  readonly filterForm: Locator
  readonly logTable: Locator
  readonly prevBtn: Locator
  readonly nextBtn: Locator
  readonly pageInfo: Locator

  constructor(page: Page) {
    super(page)
    this.heading = page.getByRole('heading', { name: '审计日志' })
    this.filterForm = page.locator('.filter-bar')
    this.logTable = page.locator('.data-table')
    this.prevBtn = page.getByRole('button', { name: '上一页' })
    this.nextBtn = page.getByRole('button', { name: '下一页' })
    this.pageInfo = page.locator('.pagination span')
  }

  async goto() {
    await this.page.goto('console/audit')
    await expect(this.heading).toBeVisible()
  }

  /** 按动作筛选 */
  async filterByAction(action: string) {
    await this.filterForm.getByLabel('动作').selectOption(action)
    await this.filterForm.getByRole('button', { name: '筛选' }).click()
  }

  /** 按应用筛选 */
  async filterByApp(appName: string) {
    await this.filterForm.getByLabel('应用').selectOption({ label: appName })
    await this.filterForm.getByRole('button', { name: '筛选' }).click()
  }

  /** 重置筛选 */
  async resetFilters() {
    await this.filterForm.getByRole('button', { name: '重置' }).click()
  }

  /** 断言表格包含指定动作文本 */
  async expectContainsAction(action: string) {
    await expect(this.logTable).toContainText(action)
  }

  /** 断言表格行数 */
  async getRowCount(): Promise<number> {
    return this.logTable.locator('tbody tr').count()
  }

  /** 翻页 */
  async nextPage() {
    await this.nextBtn.click()
  }

  async prevPage() {
    await this.prevBtn.click()
  }
}
