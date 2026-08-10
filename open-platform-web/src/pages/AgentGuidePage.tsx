import { AlertCircle, BookOpen, Bot, CheckCircle2, Code, KeyRound, Link2, Search, ShieldAlert } from 'lucide-react'
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

function OperationRow({ op }: { op: { method: string; path: string; summary: string; required_scopes: string[]; openapi_ref: string | null } }) {
  return (
    <tr>
      <td><span className={`method-badge ${op.method.toLowerCase()}`}>{op.method}</span></td>
      <td><code>{op.path}</code></td>
      <td>{op.summary}</td>
      <td>{op.required_scopes.map(s => <ScopeTag key={s} scope={s} />)}</td>
      <td>{op.openapi_ref && <a href={op.openapi_ref} target="_blank" rel="noopener">详情</a>}</td>
    </tr>
  )
}

function WorkflowSection({ workflow }: { workflow: { id: string; title: string; steps: string[]; required_scopes: string[] } }) {
  return (
    <div className="workflow-card">
      <h4>{workflow.title}</h4>
      <ol>
        {workflow.steps.map((step, i) => <li key={i}>{step}</li>)}
      </ol>
      <div className="workflow-scopes">
        {workflow.required_scopes.map(s => <ScopeTag key={s} scope={s} />)}
      </div>
    </div>
  )
}

export function AgentGuidePage() {
  const { data, isLoading, isError, error } = useAgentGuide()

  const toc = [
    { href: '#overview', label: '概述' },
    { href: '#authentication', label: '认证与权限' },
    { href: '#workflows', label: '接入流程' },
    { href: '#operations', label: '公开能力' },
    { href: '#examples', label: '代码示例' },
    { href: '#boundaries', label: '边界说明' },
  ]

  if (isLoading) {
    return (
      <DocsLayout toc={toc}>
        <article className="doc-article">
          <div className="eyebrow">AGENT GUIDE</div>
          <h1>AI Agent 集成指南</h1>
          <LoadingSkeleton />
        </article>
      </DocsLayout>
    )
  }

  if (isError || !data) {
    return (
      <DocsLayout toc={toc}>
        <article className="doc-article">
          <div className="eyebrow">AGENT GUIDE</div>
          <h1>AI Agent 集成指南</h1>
          <ErrorState message={error instanceof Error ? error.message : '未知错误'} />
        </article>
      </DocsLayout>
    )
  }

  return (
    <DocsLayout toc={toc}>
      <article className="doc-article">
        <div className="eyebrow">AGENT GUIDE</div>
        <h1>AI Agent 集成指南</h1>
        <p className="lead">
          本指南为 AI Agent 提供 MeliData 服务的只读参考信息，用于为终端用户生成正确的集成代码。
          本指南不是可执行工具接口，不会创建应用、申请密钥或调用任何管理接口。
        </p>

        <div className="guide-notice">
          <Bot size={20} />
          <div>
            <strong>用途说明</strong>
            <p>AI Agent 应仅使用本指南识别的公开业务路径生成集成代码。实际业务调用由用户应用在获得 API Key 后完成。</p>
            <p>将浏览器当前页面的 URL 提供给 AI Agent，使其能够参考这里的公开开发接口、鉴权要求与代码示例完成集成。</p>
          </div>
        </div>

        <div className="guide-meta">
          <span><BookOpen size={16} /> 机器可读版本: <a href="/agent-guide.json">/agent-guide.json</a></span>
          <span><Link2 size={16} /> OpenAPI Schema: <a href="/openapi.json">/openapi.json</a></span>
          <span>服务版本: {data.service.version}</span>
        </div>

        <section id="overview">
          <h2>系统架构</h2>
          <p>MeliData 是一个多区域文档存储与搜索集成服务，支持&quot;单点写入 + 多区域搜索&quot;架构。</p>

          <div className="arch-grid">
            <div className="arch-card">
              <h4>写入路径</h4>
              <ul className="arch-steps">
                {data.architecture.write_path.map((step, i) => (
                  <li key={i}>
                    <span className="step-num">{step.order}</span>
                    <div>
                      <strong>{step.component}</strong>
                      <p>{step.purpose}</p>
                      {step.endpoint && <code className="endpoint-ref">{step.endpoint}</code>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
            <div className="arch-card">
              <h4>搜索路径</h4>
              <ul className="arch-steps">
                {data.architecture.search_path.map((step, i) => (
                  <li key={i}>
                    <span className="step-num">{step.order}</span>
                    <div>
                      <strong>{step.component}</strong>
                      <p>{step.purpose}</p>
                      {step.endpoint && <code className="endpoint-ref">{step.endpoint}</code>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        <section id="authentication">
          <h2>认证与权限</h2>
          <div className="auth-info">
            <div className="auth-header">
              <KeyRound size={24} />
              <div>
                <h4>Bearer 认证</h4>
                <p>所有数据操作都需要在请求头中携带 API Key</p>
              </div>
            </div>
            <CodeBlock language="http" code={`Authorization: Bearer <api_key>`} />
          </div>

          <h3>Scope 权限矩阵</h3>
          <table className="scope-table">
            <thead>
              <tr>
                <th>Scope</th>
                <th>允许能力</th>
                <th>典型使用方</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.authentication.scopes).map(([scope, info]) => (
                <tr key={scope}>
                  <td><ScopeTag scope={scope} /></td>
                  <td>{info.description}</td>
                  <td>{info.typical_users.join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="callout warning">
            <ShieldAlert size={18} />
            <div>
              <strong>Key 安全要求</strong>
              <ul>
                {data.authentication.key_requirements.map((req, i) => <li key={i}>{req}</li>)}
              </ul>
            </div>
          </div>
        </section>

        <section id="workflows">
          <h2>推荐接入流程</h2>
          <div className="workflows-grid">
            {data.workflows.map((workflow) => (
              <WorkflowSection key={workflow.id} workflow={workflow} />
            ))}
          </div>
        </section>

        <section id="operations">
          <h2>公开能力索引</h2>
          <p>以下 API 操作可用于业务集成。点击&quot;详情&quot;查看完整参数定义。</p>
          <div className="operations-table-wrapper">
            <table className="operations-table">
              <thead>
                <tr>
                  <th>方法</th>
                  <th>路径</th>
                  <th>说明</th>
                  <th>Scope</th>
                  <th>参考</th>
                </tr>
              </thead>
              <tbody>
                {data.operations.map((op) => (
                  <OperationRow key={op.operation_id} op={op} />
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section id="examples">
          <h2>代码示例</h2>
          <div className="examples-tabs">
            {data.examples.map((example) => (
              <div key={example.language} className="example-section">
                <h3>{example.title}</h3>
                <p>{example.description}</p>
                <CodeBlock language={example.language === 'python' ? 'python' : example.language === 'typescript' ? 'typescript' : 'text'} code={example.code} />
              </div>
            ))}
          </div>
        </section>

        <section id="boundaries">
          <h2>边界说明</h2>
          <p>以下端点不属于业务集成目标：</p>
          <div className="non-targets-list">
            {data.non_targets.map((nt) => (
              <div key={nt.category} className="non-target-card">
                <h4><ShieldAlert size={16} /> {nt.category}</h4>
                <code>{nt.paths.join(', ')}</code>
                <p>{nt.reason}</p>
              </div>
            ))}
          </div>
          <div className="callout">
            <CheckCircle2 size={18} />
            <span>AI Agent 应只使用本页面公开的 API 操作，不应尝试访问上述受限端点。</span>
          </div>
        </section>
      </article>
    </DocsLayout>
  )
}
