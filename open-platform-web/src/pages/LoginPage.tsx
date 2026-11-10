import { ArrowRight, Braces, Database, KeyRound, LockKeyhole, Search, Waves } from 'lucide-react'
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

  const stages = [
    { title: '数据写入', system: 'PostgreSQL', icon: Database },
    { title: '变更捕获', system: 'CDC · Kafka', icon: Waves },
    { title: '区域搜索', system: 'Meilisearch', icon: Search },
  ]

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
        <span className="product-kicker"><Braces size={18} />MELIDATA · DATA PIPELINE</span>
        <h1>一条数据，如何抵达搜索结果？</h1>
        <p>从中心数据源到区域索引，CDC 将每一次文档变更传递到就近搜索节点。</p>

        <div className="flow-demo-shell" role="img" aria-label="模拟文档从 PostgreSQL 经过 CDC 与 Kafka，同步进 Meilisearch 并成为搜索结果">
          <div className="flow-demo-heading">
            <span className="flow-auto-status"><i />自动循环演示</span>
            <span>模拟事件 · 约 8 秒一轮</span>
          </div>
          <div className="login-flow">
            <span className="login-flow-track" aria-hidden="true" />
            <span className="login-flow-packet" aria-hidden="true">sku-001</span>
            {stages.map(({ title, system, icon: Icon }, index) => (
              <div className={`login-flow-node flow-stage-${index + 1}`} key={title}>
                <span className="login-flow-icon"><Icon size={20} /></span>
                <small>0{index + 1}</small>
                <strong>{title}</strong>
                <span className="login-flow-system">{system}</span>
              </div>
            ))}
          </div>
          <div className="flow-stage-cards">
            <div className="flow-stage-card flow-source-card">
              <span>产品文档</span>
              <strong>Mechanical Keyboard</strong>
              <code>sku-001 · price 699</code>
            </div>
            <div className="flow-stage-card flow-cdc-card">
              <span>变更事件</span>
              <strong>upsert(products)</strong>
              <code>document_id: sku-001</code>
            </div>
            <div className="flow-stage-card flow-result-card">
              <span className="flow-query-label">搜索 keyboard <Search size={12} /></span>
              <strong>Mechanical Keyboard</strong>
              <code>命中 · products / sku-001</code>
            </div>
          </div>
          <div className="flow-demo-footer">
            <span>写入文档 <b>→</b> 捕获变更 <b>→</b> 搜索命中</span>
            <span className="flow-live-dot"><i />演示循环中</span>
          </div>
        </div>
        <p className="login-flow-footnote">仅展示数据流原理；动画为模拟效果，不连接生产服务。</p>
      </section>
      <section className="login-panel">
        <div className="login-icon"><LockKeyhole size={22} /></div>
        <h2>OA 账号登录</h2>
        <p>面向客户和日常使用者，请使用企业 OA 账号继续。</p>
        {oaError && <div className="form-error" role="alert">OA 登录失败，无法建立会话，请重试或联系管理员。</div>}
        <button className="button button-primary full oa-login-button" type="button" onClick={handleOaLogin}>使用 OA 账号登录<ArrowRight size={17} /></button>

        <details className="admin-login-details">
          <summary><KeyRound size={15} />管理员登录</summary>
          <p>仅平台管理员使用本地管理员凭证。</p>
          <form onSubmit={submit}>
            <label>管理员账号<input name="username" required autoComplete="username" placeholder="admin" /></label>
            <label>密码<input name="password" type="password" required autoComplete="current-password" /></label>
            {error && <div className="form-error" role="alert">{error}</div>}
            <button className="button button-secondary full" type="submit" disabled={pending}>{pending ? '正在登录' : '管理员登录'}</button>
          </form>
        </details>
      </section>
    </main>
  )
}
