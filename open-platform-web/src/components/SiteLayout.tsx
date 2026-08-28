import { BookOpen, Braces, KeyRound, LogIn, LogOut, Menu, Rocket, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function SiteLayout({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/docs/quickstart')
  }

  return (
    <div className="site-shell">
      <header className="top-nav">
        <NavLink to="/docs/quickstart" className="brand" aria-label="MeliData 开放平台首页">
          <span className="brand-mark"><Braces size={18} /></span>
          <span>MeliData</span><span className="brand-accent">Open Platform</span>
        </NavLink>
        <nav className={mobileOpen ? 'main-nav open' : 'main-nav'} aria-label="主导航">
          <NavLink to="/docs/quickstart" onClick={() => setMobileOpen(false)}><BookOpen size={16} />快速开始</NavLink>
          <NavLink to="/docs/how-to-use" onClick={() => setMobileOpen(false)}><Rocket size={16} />How to use</NavLink>
          <NavLink to="/docs/api-reference" onClick={() => setMobileOpen(false)}><Braces size={16} />API Reference</NavLink>
          <NavLink to="/console/apps" onClick={() => setMobileOpen(false)}><KeyRound size={16} />控制台</NavLink>
        </nav>
        <div className="account-actions">
          {user ? (
            <>
              <span className="account-name">{user.name}</span>
              <button className="icon-button" type="button" onClick={handleLogout} aria-label="退出登录" title="退出登录"><LogOut size={17} /></button>
            </>
          ) : (
            <NavLink className="button button-primary compact" to="/login"><LogIn size={16} />登录控制台</NavLink>
          )}
          <button className="icon-button mobile-menu" type="button" onClick={() => setMobileOpen((value) => !value)} aria-label="切换导航">
            {mobileOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </header>
      {children}
    </div>
  )
}
