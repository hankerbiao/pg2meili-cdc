import { test as base } from '@playwright/test'
import { ApiClient } from '../utils/api-client'

/**
 * 提供 apiClient fixture 用于测试数据准备/清理。
 * 仅在 integration 项目中有实际后端可用。
 */
export const test = base.extend<{ apiClient: ApiClient }>({
  apiClient: async ({}, use) => {
    const client = new ApiClient(
      process.env.BASE_URL || 'http://127.0.0.1:8080',
    )
    const password = process.env.PLATFORM_PASSWORD
    if (password) {
      await client.login(password)
    }
    await use(client)
  },
})

export { expect } from '@playwright/test'
