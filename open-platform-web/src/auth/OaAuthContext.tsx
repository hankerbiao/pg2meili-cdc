import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError, oaApi } from '../api/client'
import type { OaUser } from '../api/types'

interface OaAuthValue {
  oaUser: OaUser | null
  loading: boolean
  oaLogin: () => void
  oaLogout: () => Promise<void>
}

const OaAuthContext = createContext<OaAuthValue | null>(null)

export function OaAuthProvider({ children }: { children: ReactNode }) {
  const [oaUser, setOaUser] = useState<OaUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    oaApi.me()
      .then((value) => active && setOaUser(value))
      .catch((error: unknown) => {
        if (!(error instanceof ApiError) || error.status !== 401) console.error(error)
      })
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [])

  const oaLogin = useCallback(() => {
    const next = `${window.location.origin}/open-platform/oa/callback`
    window.location.href = oaApi.loginRedirectUrl(next)
  }, [])

  const oaLogout = useCallback(async () => {
    try {
      await oaApi.logout()
    } finally {
      setOaUser(null)
    }
  }, [])

  const value = useMemo(
    () => ({ oaUser, loading, oaLogin, oaLogout }),
    [oaUser, loading, oaLogin, oaLogout],
  )
  return <OaAuthContext.Provider value={value}>{children}</OaAuthContext.Provider>
}

export function useOaAuth(): OaAuthValue {
  const value = useContext(OaAuthContext)
  if (!value) throw new Error('useOaAuth must be used inside OaAuthProvider')
  return value
}
