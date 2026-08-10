import { ArrowRight, Braces, LockKeyhole } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { oaApi } from '../api/client'
import { useAuth } from '../auth/AuthContext'

export function LoginPage() {
  const { user, login } = useAuth()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const next = params.get('next')?.startsWith('/console') ? params.get('next')! : '/console/apps'
  const oaError = params.get('oa') === 'error'
  if (user) return <Navigate to={next} replace />

  const handleOaLogin = () => {
    const callback = `${window.location.origin}/open-platform/oa/callback`
    window.location.href = oaApi.loginRedirectUrl(callback)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    setPending(true)
    setError('')
    try {
      await login(String(data.get('username')), String(data.get('password')))
      navigate(next, { replace: true })
    } catch (value) {
      setError(value instanceof Error ? value.message : '登录失败')
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-context">
        <span className="product-kicker"><Braces size={18} />MELIDATA CONTROL PLANE</span>
        <h1>管理应用身份与访问密钥</h1>
        <p>集中创建应用、轮换 API Key，并通过审计记录追踪每一次管理操作。</p>
        <div className="login-terminal"><span>$</span><code>Authorization: Bearer ud_live_ak_...</code></div>
      </section>
      <section className="login-panel">
        <div className="login-icon"><LockKeyhole size={22} /></div>
        <h2>管理员登录</h2>
        <p>使用 MeliData 本地管理员凭证继续。</p>
        <form onSubmit={submit}>
          <label>账号<input name="username" required autoComplete="username" placeholder="admin" /></label>
          <label>密码<input name="password" type="password" required autoComplete="current-password" /></label>
          {error && <div className="form-error" role="alert">{error}</div>}
          <button className="button button-primary full" type="submit" disabled={pending}>{pending ? '正在登录' : '进入控制台'}<ArrowRight size={17} /></button>
        </form>
        <div className="login-divider"><span>或</span></div>
        {oaError && <div className="form-error" role="alert">OA 登录失败，无法建立会话，请重试或联系管理员。</div>}
        <button className="button button-secondary full" type="button" onClick={handleOaLogin}>使用 OA 账号登录</button>
      </section>
    </main>
  )
}
