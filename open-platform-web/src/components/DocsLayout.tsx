import { ChevronRight, Menu } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'

const quickstartLinks = [
  { to: '/docs/how-to-use', label: 'How to use' },
  { to: '/docs/authentication', label: '认证与权限' },
  { to: '/docs/python-sdk', label: 'Python SDK' },
  { to: '/docs/api-reference', label: 'API Reference' },
]

const docLinks = [
  { to: '/docs/runtime-architecture', label: '区域搜索与同步' },
  { to: '/docs/agent-guide', label: 'AI Agent 接入' },
]

export function DocsLayout({ children, toc }: { children: ReactNode; toc: Array<{ href: string; label: string }> }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="docs-shell">
      <button className="docs-menu-button" type="button" onClick={() => setOpen((value) => !value)}><Menu size={17} />文档导航</button>
      <aside className={open ? 'docs-sidebar open' : 'docs-sidebar'}>
        <div className="sidebar-label">开始使用</div>
        <div className="docs-nav-group">
          <NavLink className="docs-nav-group-title" to="/docs/quickstart" onClick={() => setOpen(false)}>快速开始</NavLink>
          <div className="docs-nav-group-links">
            {quickstartLinks.map((link) => <NavLink key={link.to} to={link.to} onClick={() => setOpen(false)}>{link.label}<ChevronRight size={14} /></NavLink>)}
          </div>
        </div>
        {docLinks.map((link) => <NavLink key={link.to} to={link.to} onClick={() => setOpen(false)}>{link.label}<ChevronRight size={14} /></NavLink>)}
      </aside>
      <main className="docs-content">{children}</main>
      <aside className="docs-toc" aria-label="本页目录">
        <div className="sidebar-label">本页内容</div>
        {toc.map((item) => <a key={item.href} href={item.href}>{item.label}</a>)}
      </aside>
    </div>
  )
}
