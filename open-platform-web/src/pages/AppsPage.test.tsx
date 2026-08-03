import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ApiKeySecret, PlatformApp } from '../api/types'
import { AppsPage } from './AppsPage'

const api = vi.hoisted(() => ({
  listApps: vi.fn(),
  bootstrapApp: vi.fn(),
}))

vi.mock('../api/client', () => ({
  platformApi: {
    listApps: api.listApps,
    bootstrapApp: api.bootstrapApp,
  },
}))

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({
    session: { username: 'admin', csrf_token: 'csrf-test', expires_at: 4102444800 },
  }),
}))

const app: PlatformApp = {
  id: 'app-created',
  app_name: 'product_search',
  display_name: '商品搜索',
  owner_itcode: 'zhangsan',
  description: '商品目录',
  status: 'active',
  version: 1,
  created_at: '2026-07-30T08:00:00Z',
  updated_at: '2026-07-30T08:00:00Z',
}

const frontendKey: ApiKeySecret = {
  id: 'ak_frontend',
  app_id: app.id,
  name: 'frontend-search',
  prefix: 'ud_live_ak_frontend',
  last_four: 'z9Yx',
  scopes: ['search:read'],
  status: 'active',
  expires_at: '2026-12-30T08:00:00Z',
  last_used_at: null,
  revoked_at: null,
  version: 1,
  created_at: '2026-07-30T08:00:00Z',
  api_key: 'ud_live_ak_frontend.complete-frontend-secret',
}

const backendKey: ApiKeySecret = {
  ...frontendKey,
  id: 'ak_backend',
  name: 'backend-data',
  prefix: 'ud_live_ak_backend',
  scopes: ['data:read', 'data:write'],
  api_key: 'ud_live_ak_backend.complete-backend-secret',
}

describe('AppsPage', () => {
  beforeEach(() => {
    api.listApps.mockReset()
    api.bootstrapApp.mockReset()
    api.listApps.mockResolvedValueOnce([]).mockResolvedValue([app])
    api.bootstrapApp.mockResolvedValue({ app, keys: [frontendKey, backendKey] })
  })

  it('creates an app with the selected initial key and updates the list immediately', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const user = userEvent.setup()
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter><AppsPage /></MemoryRouter>
      </QueryClientProvider>,
    )

    await screen.findByText('创建第一个应用')
    await user.click(screen.getAllByRole('button', { name: '新建应用' })[0])
    await user.type(screen.getByLabelText('显示名称'), app.display_name)
    await user.type(screen.getByLabelText('应用标识'), app.app_name)
    await user.type(screen.getByLabelText('负责人 itcode'), app.owner_itcode)
    await user.type(screen.getByLabelText('描述'), app.description!)
    await user.click(screen.getByRole('button', { name: '创建应用与 Key' }))

    await waitFor(() => expect(api.bootstrapApp).toHaveBeenCalledOnce())
    expect(api.bootstrapApp.mock.calls[0][0]).toMatchObject({
      app_name: app.app_name,
      initial_keys: [
        { name: 'frontend-search', scopes: ['search:read'] },
        { name: 'backend-data', scopes: ['data:read', 'data:write'] },
      ],
    })
    expect(await screen.findByRole('heading', { name: '保存你的 API Keys' })).toBeVisible()
    expect(screen.getByText(frontendKey.api_key)).toBeVisible()
    expect(screen.getByText(backendKey.api_key)).toBeVisible()
    expect(screen.getByText(app.display_name)).toBeInTheDocument()
  })
})
