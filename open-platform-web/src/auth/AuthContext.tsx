import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError, AUTH_EXPIRED_EVENT, platformApi } from '../api/client'
import type { Session } from '../api/types'

interface AuthValue {
  session: Session | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    platformApi.getSession()
      .then((value) => active && setSession(value))
      .catch((error: unknown) => {
        if (!(error instanceof ApiError) || error.status !== 401) console.error(error)
      })
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [])

  useEffect(() => {
    const clearExpiredSession = () => setSession(null)
    window.addEventListener(AUTH_EXPIRED_EVENT, clearExpiredSession)
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, clearExpiredSession)
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    setSession(await platformApi.login(username, password))
  }, [])

  const logout = useCallback(async () => {
    try {
      if (session) await platformApi.logout(session.csrf_token)
    } finally {
      setSession(null)
    }
  }, [session])

  const value = useMemo(() => ({ session, loading, login, logout }), [session, loading, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
