export type AppStatus = 'active' | 'disabled'
export type KeyStatus = 'active' | 'revoked'
export type Scope = 'search:read' | 'data:read' | 'data:write'

export interface Session {
  username: string
  csrf_token: string
  expires_at: number
}

export interface PlatformApp {
  id: string
  app_name: string
  display_name: string
  owner_itcode: string
  description: string | null
  status: AppStatus
  version: number
  created_at: string
  updated_at: string
}

export interface ApiKeyRecord {
  id: string
  app_id: string
  name: string
  prefix: string
  last_four: string
  scopes: Scope[]
  status: KeyStatus
  expires_at: string
  last_used_at: string | null
  revoked_at: string | null
  version: number
  created_at: string
}

export interface ApiKeySecret extends ApiKeyRecord {
  api_key: string
}

export interface AuditLog {
  id: string
  actor: string
  action: string
  target_type: string
  target_id: string | null
  app_id: string | null
  source_ip: string | null
  details: Record<string, unknown> | null
  created_at: string
}

export interface AppCreateInput {
  app_name: string
  display_name: string
  owner_itcode: string
  description?: string | null
}

export interface AppBootstrapInput extends AppCreateInput {
  initial_keys: KeyCreateInput[]
}

export interface AppBootstrapResult {
  app: PlatformApp
  keys: ApiKeySecret[]
}

export interface AppUpdateInput {
  display_name?: string
  owner_itcode?: string
  description?: string | null
  status?: AppStatus
}

export interface KeyCreateInput {
  name: string
  scopes: Scope[]
  expires_at: string
}
