import { Activity, AppWindow, ArrowLeft, Braces, KeyRound, Server } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function ConsoleLayout() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  return (
    <div className="console-shell">
      <aside className="console-sidebar">
        <div className="console-heading"><span className="status-dot" />{isAdmin ? '管理控制台' : '我的控制台'}</div>
        <nav aria-label="控制台导航">
          <NavLink to="/console/apps"><AppWindow size={17} />{isAdmin ? '应用与密钥' : '我的应用'}</NavLink>
          {isAdmin && (
            <>
              <NavLink to="/console/agents"><Server size={17} />代理节点</NavLink>
              <NavLink to="/console/audit"><Activity size={17} />审计日志</NavLink>
              <NavLink to="/console/api-playground"><Braces size={17} />API 调试</NavLink>
            </>
          )}
        </nav>
        <div className="console-sidebar-footer">
          <NavLink to="/docs/quickstart"><ArrowLeft size={16} />返回文档</NavLink>
          <span><KeyRound size={15} />API Key 管理</span>
        </div>
      </aside>
      <main className="console-content"><Outlet /></main>
    </div>
  )
}
