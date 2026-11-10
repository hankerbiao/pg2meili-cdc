import { AlertCircle, BookOpen, Bot, CheckCircle2, KeyRound, Link2, ShieldAlert } from 'lucide-react'
import { DocsLayout } from '../components/DocsLayout'
import { CodeBlock } from '../components/CodeBlock'
import { useAgentGuide } from '../api/useAgentGuide'

function LoadingSkeleton() {
  return (
    <div className="skeleton-container">
      <div className="skeleton skeleton-title" />
      <div className="skeleton skeleton-text" />
      <div className="skeleton skeleton-text short" />
      <div className="skeleton skeleton-block" />
    </div>
  )
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="error-state">
      <AlertCircle size={48} />
      <h2>Agent Guide 暂不可用</h2>
      <p>{message}</p>
      <p>你可以访问以下链接获取更多信息：</p>
      <ul>
        <li><a href="/openapi.json" target="_blank" rel="noopener">REST API Schema (OpenAPI)</a></li>
        <li><a href="/docs" target="_blank" rel="noopener">人类可读文档</a></li>
      </ul>
    </div>
  )
}

function ScopeTag({ scope }: { scope: string }) {
  const colors: Record<string, string> = {
    'data:read': 'scope-read',
    'data:write': 'scope-write',
    'search:read': 'scope-search',
  }
  return <span className={`scope-tag ${colors[scope] || ''}`}>{scope}</span>
}

export function AgentGuidePage() {
  const { data, isLoading, isError, error } = useAgentGuide()
  const toc = [
    { href: '#start', label: '接入流程' },
    { href: '#authentication', label: '认证与权限' },
    { href: '#examples', label: 'cURL 示例' },
    { href: '#operations', label: 'API 清单' },
  ]

  if (isLoading) {
    return <DocsLayout toc={toc}><article className="doc-article"><div className="eyebrow">AGENT GUIDE</div><h1>AI Agent 集成指南</h1><LoadingSkeleton /></article></DocsLayout>
  }
  if (isError || !data) {
    return <DocsLayout toc={toc}><article className="doc-article"><div className="eyebrow">AGENT GUIDE</div><h1>AI Agent 集成指南</h1><ErrorState message={error instanceof Error ? error.message : '未知错误'} /></article></DocsLayout>
  }

  const searchExample = `curl --request POST \\
  --url "$SEARCH_BASE_URL/api/v1/collections/products/search" \\
  --header "Authorization: Bearer $MELIDATA_API_KEY" \\
  --header "Content-Type: application/json" \\
  --data '{"q":"keyboard","limit":10}'`

  return (
    <DocsLayout toc={toc}>
      <article className="doc-article agent-guide-article">
        <div className="eyebrow">AGENT GUIDE</div>
        <h1>AI Agent 集成指南</h1>
        <p className="lead">给 AI 编程助手的 MeliData 接入速查。按顺序验证 cURL 请求，再将请求集成到服务端应用。</p>

        <div className="guide-notice">
          <Bot size={20} />
          <div>
            <strong>把本页链接交给 AI 助手即可</strong>
            <p>API Key 由你的服务端安全保存。请勿将 Key 粘贴到聊天、浏览器代码或仓库。</p>
          </div>
        </div>

        <div className="guide-meta">
          <span><BookOpen size={16} /> <a href="/docs/api-reference">API Reference</a></span>
          <span><Link2 size={16} /> <a href="/openapi.json">OpenAPI Schema</a></span>
          <span>服务版本：{data.service.version}</span>
        </div>

        <section id="start">
          <h2>三步完成接入</h2>
          <ol className="onboarding-flow" aria-label="AI Agent 接入步骤">
            <li className="onboarding-flow-step"><span className="onboarding-flow-number">01</span><h3>准备服务端 API Key</h3><p>按需申请 <code>data:write</code>、<code>data:read</code> 或 <code>search:read</code> 权限。</p></li>
            <li className="onboarding-flow-step"><span className="onboarding-flow-number">02</span><h3>用 cURL 验证请求</h3><p>在安全的终端环境验证写入、节点发现和搜索请求。</p></li>
            <li className="onboarding-flow-step"><span className="onboarding-flow-number">03</span><h3>集成到服务端</h3><p>将请求转换为应用代码，并从密钥管理系统读取 API Key。</p></li>
          </ol>
          <div className="guide-meta">
            <span><strong>数据 API</strong> <code>{data.endpoints.data_base_url}</code></span>
            <span><strong>区域搜索</strong> 使用在线节点返回的 <code>base_url</code></span>
          </div>
        </section>

        <section id="authentication">
          <h2>认证与权限</h2>
          <div className="auth-info">
            <div className="auth-header">
              <KeyRound size={24} />
              <div><h4>Bearer 认证</h4><p>所有业务请求都在请求头中携带 API Key。</p></div>
            </div>
            <p>请求头：<code>Authorization: Bearer $MELIDATA_API_KEY</code></p>
          </div>
          <div className="scope-list">
            {Object.entries(data.authentication.scopes).map(([scope, info]) => (
              <div className="scope-list-item" key={scope}><ScopeTag scope={scope} /><span>{info.description}</span></div>
            ))}
          </div>
          <div className="callout warning">
            <ShieldAlert size={18} />
            <div><strong>Key 安全要求</strong><ul>{data.authentication.key_requirements.slice(0, 3).map((req, i) => <li key={i}>{req}</li>)}</ul></div>
          </div>
        </section>

        <section id="examples">
          <h2>cURL 示例</h2>
          <p>先在终端安全设置 <code>MELIDATA_API_KEY</code>，以下命令可直接作为请求模板。</p>
          <h3>写入一条文档</h3>
          <CodeBlock language="curl" code={`curl --request POST \\
  --url "${data.endpoints.data_base_url}/api/v1/data/products" \\
  --header "Authorization: Bearer $MELIDATA_API_KEY" \\
  --header "Content-Type: application/json" \\
  --data '{"id":"sku-001","name":"Keyboard","price":699}'`} />
          <h3>查询在线区域节点</h3>
          <CodeBlock language="curl" code={`curl --request GET \\
  --url "${data.endpoints.data_base_url}/api/v1/agents/online" \\
  --header "Authorization: Bearer $MELIDATA_API_KEY"`} />
          <h3>搜索文档</h3>
          <p>将在线节点响应中的区域 <code>base_url</code> 设为 <code>SEARCH_BASE_URL</code>，再发起搜索。</p>
          <CodeBlock language="curl" code={searchExample} />
        </section>

        <section id="operations">
          <h2>业务 API 清单</h2>
          <div className="operations-table-wrapper">
            <table className="operations-table">
              <thead><tr><th>方法</th><th>路径</th><th>用途</th><th>权限</th></tr></thead>
              <tbody>{data.operations.filter((op) => op.operation_id !== 'python_sdk_download').map((op) => (
                <tr key={op.operation_id}>
                  <td><span className={`method-badge ${op.method.toLowerCase()}`}>{op.method}</span></td>
                  <td><code>{op.path}</code></td><td>{op.summary}</td>
                  <td>{op.required_scopes.map((scope) => <ScopeTag key={scope} scope={scope} />)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className="callout"><CheckCircle2 size={18} /><span>完整参数、请求和响应定义请查看 <a href="/docs/api-reference">API Reference</a>。管理与内部接口不用于业务集成。</span></div>
        </section>
      </article>
    </DocsLayout>
  )
}
