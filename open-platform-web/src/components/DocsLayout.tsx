import { ChevronRight, Menu } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'

const docLinks = [
  { to: '/docs/quickstart', label: '快速开始' },
  { to: '/docs/authentication', label: '认证与权限' },
  { to: '/docs/python-sdk', label: 'Python SDK' },
  { to: '/docs/api-reference', label: 'API Reference' },
]

export function DocsLayout({ children, toc }: { children: ReactNode; toc: Array<{ href: string; label: string }> }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="docs-shell">
      <button className="docs-menu-button" type="button" onClick={() => setOpen((value) => !value)}><Menu size={17} />文档导航</button>
      <aside className={open ? 'docs-sidebar open' : 'docs-sidebar'}>
        <div className="sidebar-label">开始使用</div>
        {docLinks.map((link) => <NavLink key={link.to} to={link.to} onClick={() => setOpen(false)}>{link.label}<ChevronRight size={14} /></NavLink>)}
        <div className="sidebar-label spaced">资源</div>
        <a href="/docs" target="_blank" rel="noreferrer">后端 OpenAPI<ChevronRight size={14} /></a>
      </aside>
      <main className="docs-content">{children}</main>
      <aside className="docs-toc" aria-label="本页目录">
        <div className="sidebar-label">本页内容</div>
        {toc.map((item) => <a key={item.href} href={item.href}>{item.label}</a>)}
      </aside>
    </div>
  )
}
