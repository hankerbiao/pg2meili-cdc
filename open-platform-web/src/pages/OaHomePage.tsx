import { useOaAuth } from '../auth/OaAuthContext'

export function OaHomePage() {
  const { oaUser, oaLogout } = useOaAuth()
  const profile = oaUser?.profile ?? {}
  const profileKeys = Object.keys(profile)

  return (
    <main className="oa-home">
      <section className="oa-card">
        <span className="product-kicker">UNIDATA · OA 账号</span>
        <h1>欢迎，{oaUser?.name || oaUser?.itcode}</h1>
        <dl className="oa-meta">
          <div>
            <dt>工号 (itcode)</dt>
            <dd>{oaUser?.itcode}</dd>
          </div>
          {oaUser?.email ? (
            <div>
              <dt>邮箱</dt>
              <dd>{oaUser.email}</dd>
            </div>
          ) : null}
        </dl>
        {profileKeys.length > 0 && (
          <details className="oa-profile">
            <summary>查看原始资料 (profile)</summary>
            <pre>{JSON.stringify(profile, null, 2)}</pre>
          </details>
        )}
        <div className="oa-actions">
          <button className="button button-secondary" type="button" onClick={() => void oaLogout()}>
            退出 OA 登录
          </button>
        </div>
      </section>
    </main>
  )
}
