import { test as base, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const STATE_PATH = path.resolve(__dirname, '../.auth/state.json')

/**
 * 扩展 test：提供 authenticatedPage fixture。
 * 如果 storageState 存在则复用登录态，否则回退到普通 page。
 */
export const test = base.extend<{ authenticatedPage: Page }>({
  authenticatedPage: async ({ browser }, use) => {
    const hasState = fs.existsSync(STATE_PATH)
    const context = await browser.newContext(
      hasState ? { storageState: STATE_PATH } : undefined,
    )
    const page = await context.newPage()
    await use(page)
    await context.close()
  },
})

export { expect } from '@playwright/test'
