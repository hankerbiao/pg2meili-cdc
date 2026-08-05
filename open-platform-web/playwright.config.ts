import { defineConfig, devices } from '@playwright/test'

const browserChannel = process.env.PLAYWRIGHT_CHANNEL ?? (process.env.CI ? undefined : 'chrome')
const configuredSlowMo = Number(process.env.PLAYWRIGHT_SLOW_MO ?? 0)
const slowMo = Number.isFinite(configuredSlowMo) && configuredSlowMo > 0 ? configuredSlowMo : 0

export default defineConfig({
  testDir: './e2e/specs',
  outputDir: './e2e/test-results',
  globalSetup: './e2e/global-setup.ts',
  timeout: slowMo ? 120_000 : 30_000,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : 4,
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
  ],
  use: {
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:4178/open-platform/',
    channel: browserChannel,
    launchOptions: slowMo ? { slowMo } : undefined,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 4178',
    url: 'http://127.0.0.1:4178/open-platform/',
    reuseExistingServer: !process.env.CI,
  },
  projects: [
    // Mock 测试 — 桌面（每次 PR 必跑）
    {
      name: 'mock-desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
      grep: /@mock/,
      grepInvert: /@responsive/,
    },
    // Integration 测试 — 桌面（需要真实后端）
    {
      name: 'integration-desktop',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 900 },
        baseURL: process.env.BASE_URL || 'http://127.0.0.1:8080/open-platform/',
        storageState: process.env.PLATFORM_PASSWORD ? './e2e/.auth/state.json' : undefined,
      },
      grep: /@integration/,
    },
    // 响应式 — 平板
    {
      name: 'tablet',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1024, height: 900 } },
      grep: /@responsive/,
    },
    // 响应式 — 移动端
    {
      name: 'mobile',
      use: { ...devices['Desktop Chrome'], viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true },
      grep: /@responsive/,
    },
  ],
})
