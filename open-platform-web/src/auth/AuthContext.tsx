import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError, AUTH_EXPIRED_EVENT, oaApi, platformApi } from '../api/client'

export type ConsoleRole = 'admin' | 'oa'

/** 统一登录态：管理员密码登录与 OA 单点登录共用控制台，按角色渲染内容。 */
export interface ConsoleUser {
  role: ConsoleRole
  /** admin 时为管理员用户名，oa 时为工号 itcode */
  username: string
  /** 控制台显示的姓名 */
  name: string
  email?: string
  /** 仅 admin 会话有值，写操作需随请求带回 */
  csrf_token?: string
}

interface AuthValue {
  user: ConsoleUser | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<ConsoleUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    ;(async () => {
      try {
        // 1) 管理员会话优先（级别更高）
        const session = await platformApi.getSession()
        if (!active) return
        setUser({ role: 'admin', username: session.username, name: session.username, csrf_token: session.csrf_token })
      } catch (error) {
        // 2) 管理员未登录（401）→ 回退探测 OA 会话
        if (error instanceof ApiError && error.status === 401 && active) {
          try {
            const oa = await oaApi.me()
            if (!active) return
            setUser({ role: 'oa', username: oa.itcode, name: oa.name || oa.itcode, email: oa.email })
          } catch (oaError) {
            if (active) setUser(null)
          }
        } else if (active) {
          setUser(null)
        }
      } finally {
        if (active) setLoading(false)
      }
    })()
    return () => { active = false }
  }, [])

  useEffect(() => {
    const clearExpiredSession = () => setUser(null)
    window.addEventListener(AUTH_EXPIRED_EVENT, clearExpiredSession)
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, clearExpiredSession)
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const session = await platformApi.login(username, password)
    setUser({ role: 'admin', username: session.username, name: session.username, csrf_token: session.csrf_token })
  }, [])

  const logout = useCallback(async () => {
    try {
      if (user?.role === 'oa') {
        await oaApi.logout()
      } else if (user?.csrf_token) {
        await platformApi.logout(user.csrf_token)
      }
    } finally {
      setUser(null)
    }
  }, [user])

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
