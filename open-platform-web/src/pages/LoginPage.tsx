import { ArrowRight, Braces, LockKeyhole } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function LoginPage() {
  const { session, login } = useAuth()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const next = params.get('next')?.startsWith('/console') ? params.get('next')! : '/console/apps'
  if (session) return <Navigate to={next} replace />

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
        <span className="product-kicker"><Braces size={18} />UNIDATA CONTROL PLANE</span>
        <h1>管理应用身份与访问密钥</h1>
        <p>集中创建应用、轮换 API Key，并通过审计记录追踪每一次管理操作。</p>
        <div className="login-terminal"><span>$</span><code>Authorization: Bearer ud_live_ak_...</code></div>
      </section>
      <section className="login-panel">
        <div className="login-icon"><LockKeyhole size={22} /></div>
        <h2>管理员登录</h2>
        <p>使用 UniData 本地管理员凭证继续。</p>
        <form onSubmit={submit}>
          <label>账号<input name="username" required autoComplete="username" placeholder="admin" /></label>
          <label>密码<input name="password" type="password" required autoComplete="current-password" /></label>
          {error && <div className="form-error" role="alert">{error}</div>}
          <button className="button button-primary full" type="submit" disabled={pending}>{pending ? '正在登录' : '进入控制台'}<ArrowRight size={17} /></button>
        </form>
      </section>
    </main>
  )
}
