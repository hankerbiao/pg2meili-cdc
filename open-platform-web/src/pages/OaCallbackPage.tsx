import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { oaApi } from '../api/client'

export function OaCallbackPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [pending, setPending] = useState(true)

  useEffect(() => {
    const status = params.get('status')
    const payload = params.get('payload')
    const next = params.get('next')
    if (!status || !payload) {
      setError('缺少 OA 登录参数，无法完成登录')
      setPending(false)
      return
    }
    oaApi
      .callback({ status, payload, next })
      .then(() => navigate('/console', { replace: true }))
      .catch((value: unknown) => {
        setError(value instanceof Error ? value.message : 'OA 登录失败')
        setPending(false)
      })
  }, [params, navigate])

  return (
    <main className="oa-callback">
      <section className="oa-card">
        {pending && !error ? (
          <>
            <h1>正在完成 OA 登录…</h1>
            <p>正在校验登录信息并建立会话，请稍候。</p>
          </>
        ) : (
          <>
            <h1>OA 登录失败</h1>
            <p className="form-error" role="alert">
              {error}
            </p>
            <div className="oa-actions">
              <button
                className="button button-secondary"
                type="button"
                onClick={() => navigate('/login', { replace: true })}
              >
                返回登录页
              </button>
            </div>
          </>
        )}
      </section>
    </main>
  )
}
