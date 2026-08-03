/**
 * 直接调用后端 API 的客户端，用于 integration 测试的数据准备/清理。
 * 不依赖浏览器，通过 fetch 操作后端。
 */

interface SessionData {
  username: string
  csrf_token: string
  expires_at: number
}

export class ApiClient {
  private baseUrl: string
  private cookie = ''
  private csrf = ''

  constructor(host: string) {
    this.baseUrl = `${host.replace(/\/$/, '')}/api/v1/open-platform`
  }

  async login(password: string) {
    const res = await fetch(`${this.baseUrl}/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'admin', password }),
    })
    if (!res.ok) throw new Error(`Login failed: ${res.status} ${await res.text()}`)
    const { data } = (await res.json()) as { data: SessionData }
    this.csrf = data.csrf_token
    // 提取 set-cookie
    const setCookie = res.headers.get('set-cookie')
    if (setCookie) this.cookie = setCookie.split(';')[0]
  }

  private headers(): Record<string, string> {
    const h: Record<string, string> = { 'Content-Type': 'application/json' }
    if (this.cookie) h['Cookie'] = this.cookie
    if (this.csrf) h['X-CSRF-Token'] = this.csrf
    return h
  }

  // ─── Apps ───────────────────────────────────────────────

  async listApps() {
    const res = await fetch(`${this.baseUrl}/apps`, { headers: this.headers() })
    const { data } = await res.json()
    return data as any[]
  }

  async createApp(input: { display_name: string; app_name: string; owner_itcode: string; description?: string }) {
    const res = await fetch(`${this.baseUrl}/apps`, {
      method: 'POST',
      headers: this.headers(),
      body: JSON.stringify(input),
    })
    const { data } = await res.json()
    return data
  }

  async bootstrapApp(input: {
    display_name: string
    app_name: string
    owner_itcode: string
    description?: string
    initial_keys: Array<{ name: string; scopes: string[]; expires_at: string }>
  }) {
    const res = await fetch(`${this.baseUrl}/apps/bootstrap`, {
      method: 'POST',
      headers: this.headers(),
      body: JSON.stringify(input),
    })
    const { data } = await res.json()
    return data as { app: any; keys: any[] }
  }

  async updateApp(appId: string, input: Record<string, unknown>) {
    const res = await fetch(`${this.baseUrl}/apps/${appId}`, {
      method: 'PATCH',
      headers: this.headers(),
      body: JSON.stringify(input),
    })
    const { data } = await res.json()
    return data
  }

  // ─── Keys ───────────────────────────────────────────────

  async listKeys(appId: string) {
    const res = await fetch(`${this.baseUrl}/apps/${appId}/keys`, { headers: this.headers() })
    const { data } = await res.json()
    return data as any[]
  }

  async createKey(appId: string, input: { name: string; scopes: string[]; expires_at: string }) {
    const res = await fetch(`${this.baseUrl}/apps/${appId}/keys`, {
      method: 'POST',
      headers: this.headers(),
      body: JSON.stringify(input),
    })
    const { data } = await res.json()
    return data
  }

  async rotateKey(keyId: string) {
    const res = await fetch(`${this.baseUrl}/keys/${keyId}/rotate`, {
      method: 'POST',
      headers: this.headers(),
    })
    const { data } = await res.json()
    return data
  }

  async revokeKey(keyId: string) {
    const res = await fetch(`${this.baseUrl}/keys/${keyId}/revoke`, {
      method: 'POST',
      headers: this.headers(),
    })
    const { data } = await res.json()
    return data
  }

  // ─── Audit ──────────────────────────────────────────────

  async listAuditLogs(params?: URLSearchParams) {
    const qs = params ? `?${params.toString()}` : ''
    const res = await fetch(`${this.baseUrl}/audit-logs${qs}`, { headers: this.headers() })
    const { data } = await res.json()
    return data as any[]
  }

  // ─── Session ────────────────────────────────────────────

  async logout() {
    await fetch(`${this.baseUrl}/session`, {
      method: 'DELETE',
      headers: this.headers(),
    })
    this.cookie = ''
    this.csrf = ''
  }
}
