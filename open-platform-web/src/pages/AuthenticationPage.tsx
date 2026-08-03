import { AlertTriangle, ShieldCheck } from 'lucide-react'
import { CodeBlock } from '../components/CodeBlock'
import { DocsLayout } from '../components/DocsLayout'

export function AuthenticationPage() {
  return (
    <DocsLayout toc={[{ href: '#header', label: '请求头' }, { href: '#scopes', label: '权限范围' }, { href: '#errors', label: '错误响应' }, { href: '#security', label: '安全建议' }]}>
      <article className="doc-article">
        <div className="eyebrow">AUTHENTICATION</div>
        <h1>API Key 认证</h1>
        <p className="lead">每把 Key 归属于一个应用，并独立拥有权限、有效期和撤销状态。旧 JWT 不再被任何数据或搜索 API 接受。</p>
        <section id="header"><h2>请求头</h2><p>所有调用都通过标准 Bearer 请求头传递完整 API Key。</p><CodeBlock language="http" code={'Authorization: Bearer ud_live_ak_0123456789abcdef.<secret>'} /></section>
        <section id="scopes"><h2>权限范围</h2><div className="scope-list"><div><code>search:read</code><span>发现区域节点并执行搜索</span></div><div><code>data:read</code><span>读取文档与集合信息</span></div><div><code>data:write</code><span>写入、删除文档并管理索引设置</span></div></div></section>
        <section id="errors"><h2>错误响应</h2><table className="docs-table"><thead><tr><th>状态码</th><th>错误码</th><th>含义</th></tr></thead><tbody><tr><td>401</td><td><code>INVALID_API_KEY</code></td><td>Key 无效、过期、撤销或应用已禁用</td></tr><tr><td>403</td><td><code>INSUFFICIENT_SCOPE</code></td><td>Key 缺少当前操作所需权限</td></tr><tr><td>503</td><td><code>AUTH_UNAVAILABLE</code></td><td>区域鉴权缓存暂时不可用</td></tr></tbody></table></section>
        <section id="security"><h2>安全建议</h2><div className="security-grid"><div><ShieldCheck /><strong>服务端保存</strong><span>不要把 Key 放进浏览器包、仓库或日志。</span></div><div><AlertTriangle /><strong>按用途拆分</strong><span>生产、测试和不同工作负载使用独立 Key。</span></div></div></section>
      </article>
    </DocsLayout>
  )
}
