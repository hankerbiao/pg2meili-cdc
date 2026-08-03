import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, request } from './client'

describe('request', () => {
  afterEach(() => vi.restoreAllMocks())

  it('adds credentials and CSRF to write requests', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ data: { ok: true } }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    await request('/api/v1/open-platform/apps', { method: 'POST', body: '{}' }, 'csrf-value')
    const [, options] = fetchMock.mock.calls[0]
    expect(options?.credentials).toBe('include')
    expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('csrf-value')
  })

  it('does not add CSRF to GET requests', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ data: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    await request('/api/v1/open-platform/apps', {}, 'csrf-value')
    const [, options] = fetchMock.mock.calls[0]
    expect(new Headers(options?.headers).has('X-CSRF-Token')).toBe(false)
  })

  it('normalizes API error messages', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ message: '管理员会话无效' }), { status: 401, headers: { 'Content-Type': 'application/json' } }))
    await expect(request('/api/v1/open-platform/session')).rejects.toEqual(new ApiError(401, '管理员会话无效'))
  })
})
