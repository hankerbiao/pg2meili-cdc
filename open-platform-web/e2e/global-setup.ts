import { chromium, type FullConfig } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const statePath = path.resolve('e2e/.auth/state.json')

/**
 * 全局 setup：登录一次，保存 storageState 供后续测试复用。
 * 密码通过环境变量 PLATFORM_PASSWORD 注入。
 */
async function globalSetup(config: FullConfig) {
  const baseURL = config.projects.find((p) => p.name.startsWith('integration'))?.use?.baseURL
    ?? process.env.BASE_URL
    ?? 'http://127.0.0.1:8081/open-platform/'
  const password = process.env.PLATFORM_PASSWORD
  if (!password) {
    fs.rmSync(statePath, { force: true })
    console.warn('[global-setup] PLATFORM_PASSWORD 未设置，跳过登录态保存（mock 测试不受影响）')
    return
  }

  const channel = process.env.PLAYWRIGHT_CHANNEL ?? (process.env.CI ? undefined : 'chrome')
  const browser = await chromium.launch({ channel })
  try {
    const page = await browser.newPage()
    const loginUrl = new URL('login', baseURL.endsWith('/') ? baseURL : `${baseURL}/`)

    await page.goto(loginUrl.toString())
    await page.getByLabel('账号').fill('admin')
    await page.getByLabel('密码').fill(password)
    await page.getByRole('button', { name: /进入控制台/ }).click()
    await page.waitForURL('**/console/apps', { timeout: 15_000 })

    fs.mkdirSync(path.dirname(statePath), { recursive: true })
    await page.context().storageState({ path: statePath })
  } finally {
    await browser.close()
  }
}

export default globalSetup
