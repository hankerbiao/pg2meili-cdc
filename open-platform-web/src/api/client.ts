import type {
  AgentNode,
  ApiKeyRecord,
  ApiKeySecret,
  AppBootstrapInput,
  AppBootstrapResult,
  AppCreateInput,
  AppUpdateInput,
  AuditLog,
  KeyCreateInput,
  OaUser,
  PlatformApp,
  Session,
} from './types'

interface ApiEnvelope<T> {
  data: T
  message?: string
}

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

export const AUTH_EXPIRED_EVENT = 'unidata:auth-expired'

export async function request<T>(
  path: string,
  options: RequestInit = {},
  csrfToken?: string,
): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers = new Headers(options.headers)
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) {
    headers.set('X-CSRF-Token', csrfToken)
  }
  const response = await fetch(path, { ...options, method, headers, credentials: 'include' })
  const payload = (await response.json().catch(() => ({}))) as Partial<ApiEnvelope<T>> & { detail?: string }
  if (!response.ok) {
    if (response.status === 401 && typeof window !== 'undefined') {
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
    }
    throw new ApiError(response.status, payload.detail ?? payload.message ?? '请求失败，请稍后重试')
  }
  return payload.data as T
}

const base = '/api/v1/open-platform'

export const platformApi = {
  getSession: () => request<Session>(`${base}/session`),
  login: (username: string, password: string) =>
    request<Session>(`${base}/session`, { method: 'POST', body: JSON.stringify({ username, password }) }),
  logout: (csrf?: string) => request<{ logged_out: boolean }>(`${base}/session`, { method: 'DELETE' }, csrf),
  listApps: () => request<PlatformApp[]>(`${base}/apps`),
  getApp: (id: string) => request<PlatformApp>(`${base}/apps/${encodeURIComponent(id)}`),
  createApp: (input: AppCreateInput, csrf?: string) =>
    request<PlatformApp>(`${base}/apps`, { method: 'POST', body: JSON.stringify(input) }, csrf),
  bootstrapApp: (input: AppBootstrapInput, csrf?: string) =>
    request<AppBootstrapResult>(`${base}/apps/bootstrap`, { method: 'POST', body: JSON.stringify(input) }, csrf),
  updateApp: (id: string, input: AppUpdateInput, csrf?: string) =>
    request<PlatformApp>(`${base}/apps/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(input) }, csrf),
  listKeys: (appId: string) => request<ApiKeyRecord[]>(`${base}/apps/${encodeURIComponent(appId)}/keys`),
  createKey: (appId: string, input: KeyCreateInput, csrf?: string) =>
    request<ApiKeySecret>(`${base}/apps/${encodeURIComponent(appId)}/keys`, { method: 'POST', body: JSON.stringify(input) }, csrf),
  rotateKey: (keyId: string, csrf?: string) =>
    request<ApiKeySecret>(`${base}/keys/${encodeURIComponent(keyId)}/rotate`, { method: 'POST' }, csrf),
  revokeKey: (keyId: string, csrf?: string) =>
    request<ApiKeyRecord>(`${base}/keys/${encodeURIComponent(keyId)}/revoke`, { method: 'POST' }, csrf),
  listAuditLogs: (params: URLSearchParams) => request<AuditLog[]>(`${base}/audit-logs?${params.toString()}`),
  listAgents: () => request<AgentNode[]>(`${base}/agents`),
}

const oaBase = '/api/v1/auth/oa'

export const oaApi = {
  loginRedirectUrl: (next: string) => `${oaBase}/login?next=${encodeURIComponent(next)}`,
  callback: (body: { status: string; payload: string; next?: string | null }) =>
    request<OaUser>(`${oaBase}/callback`, { method: 'POST', body: JSON.stringify(body) }),
  me: () => request<OaUser>(`${oaBase}/me`),
  logout: () => request<{ logged_out: boolean }>(`${oaBase}/logout`, { method: 'DELETE' }),
}
