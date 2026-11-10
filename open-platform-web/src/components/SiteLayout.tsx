import { Braces, LogIn, LogOut } from 'lucide-react'
import type { ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function SiteLayout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/docs/quickstart')
  }

  return (
    <div className="site-shell">
      <header className="top-nav">
        <NavLink to="/docs/how-to-use" className="brand" aria-label="MeliData 开放平台首页">
          <span className="brand-mark"><Braces size={18} /></span>
          <span>MeliData</span><span className="brand-accent">Open Platform</span>
        </NavLink>
        <div className="account-actions">
          {user ? (
            <>
              <span className="account-name">{user.name}</span>
              <button className="icon-button" type="button" onClick={handleLogout} aria-label="退出登录" title="退出登录"><LogOut size={17} /></button>
            </>
          ) : (
            <NavLink className="button button-primary compact" to="/login"><LogIn size={16} />登录控制台</NavLink>
          )}
        </div>
      </header>
      {children}
    </div>
  )
}
