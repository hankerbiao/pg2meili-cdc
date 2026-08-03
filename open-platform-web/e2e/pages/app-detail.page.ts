import { type Locator, type Page, expect } from '@playwright/test'
import { BasePage } from './base.page'

export class AppDetailPage extends BasePage {
  readonly heading: Locator
  readonly editBtn: Locator
  readonly createKeyBtn: Locator
  readonly keyTable: Locator
  readonly backLink: Locator

  constructor(page: Page) {
    super(page)
    this.heading = page.locator('.app-detail-header h1')
    this.editBtn = page.getByRole('button', { name: '编辑' })
    this.createKeyBtn = page.getByRole('button', { name: '创建 API Key' }).first()
    this.keyTable = page.locator('.key-table')
    this.backLink = page.getByRole('link', { name: '所有应用' })
  }

  async goto(appId: string) {
    await this.page.goto(`console/apps/${appId}`)
    await expect(this.heading).toBeVisible()
  }

  /** 获取应用状态 badge 文本 */
  async getStatus(): Promise<string> {
    return (await this.page.locator('.app-meta .status-badge').innerText()).trim()
  }

  /** 打开编辑弹窗并修改字段 */
  async editApp(opts: { displayName?: string; owner?: string; description?: string }) {
    await this.editBtn.click()
    await expect(this.page.getByRole('heading', { name: '编辑应用' })).toBeVisible()
    if (opts.displayName) {
      const input = this.page.getByLabel('显示名称')
      await input.clear()
      await input.fill(opts.displayName)
    }
    if (opts.owner) {
      const input = this.page.getByLabel('负责人 itcode')
      await input.clear()
      await input.fill(opts.owner)
    }
    if (opts.description) {
      await this.page.getByLabel('描述').fill(opts.description)
    }
    await this.page.getByRole('button', { name: '保存更改' }).click()
  }

  /** 创建 API Key */
  async createKey(opts: { name: string; scopes?: string[] }) {
    await this.createKeyBtn.click()
    await expect(this.page.getByRole('heading', { name: '创建 API Key' })).toBeVisible()
    await this.page.getByLabel('Key 名称').fill(opts.name)
    if (opts.scopes) {
      // 先取消默认选中，再选中指定的
      for (const scope of ['搜索只读', '数据只读', '数据写入']) {
        const checkbox = this.page.getByLabel(scope)
        const isChecked = await checkbox.isChecked()
        const shouldCheck = opts.scopes.some((s) =>
          (s === 'search:read' && scope === '搜索只读') ||
          (s === 'data:read' && scope === '数据只读') ||
          (s === 'data:write' && scope === '数据写入'),
        )
        if (isChecked !== shouldCheck) await checkbox.click()
      }
    }
    await this.page.getByRole('button', { name: '创建密钥' }).click()
  }

  /** 轮换指定 key */
  async rotateKey(keyName: string) {
    await this.page.getByRole('button', { name: `轮换 ${keyName}` }).click()
    await this.page.getByRole('button', { name: '确认轮换' }).click()
  }

  /** 撤销指定 key */
  async revokeKey(keyName: string) {
    await this.page.getByRole('button', { name: `撤销 ${keyName}` }).click()
    await this.page.getByRole('button', { name: '确认撤销' }).click()
  }

  /** 禁用/启用应用 */
  async toggleStatus() {
    const btn = this.page.getByRole('button', { name: /禁用应用|启用应用/ })
    const isDisable = (await btn.innerText()).includes('禁用')
    await btn.click()
    await this.page.getByRole('button', { name: isDisable ? '确认禁用' : '确认启用' }).click()
  }

  /** 断言密钥弹窗出现 */
  async expectSecretDialog() {
    await expect(this.page.getByRole('heading', { name: '保存你的 API Key' })).toBeVisible()
  }

  /** 关闭密钥弹窗 */
  async closeSecretDialog() {
    await this.page.getByRole('button', { name: '我已保存，关闭' }).click()
  }

  /** 获取 key 表格中指定行 */
  getKeyRow(keyName: string): Locator {
    return this.keyTable.getByRole('row').filter({ hasText: keyName })
  }

  /** 断言 key 状态 */
  async expectKeyStatus(keyName: string, status: 'Active' | 'Revoked') {
    await expect(this.getKeyRow(keyName)).toContainText(status)
  }
}
