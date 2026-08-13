import { ChevronRight, LoaderCircle, ShieldAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import { CodeBlock } from '../components/CodeBlock'
import { DocsLayout } from '../components/DocsLayout'
import { regionalSearchOperation, type PublicOperation } from '../api/openapi'
import { useOpenApiOperations } from '../api/useOpenApi'

const methodClass = (method: string) => `method method-${method.toLowerCase()}`

export function ApiReferencePage() {
  const query = useOpenApiOperations()
  const operations = useMemo(() => [...(query.data ?? []), regionalSearchOperation], [query.data])
  const [selectedId, setSelectedId] = useState('regional-search')
  const selected = operations.find((item) => item.id === selectedId) ?? operations[0]

  return (
    <DocsLayout toc={[{ href: '#instructions', label: 'AI 使用规则' }, { href: '#contract', label: '核心契约' }, { href: '#endpoints', label: '端点列表' }, { href: '#operation', label: '请求详情' }]}>
      <article className="doc-article reference-article">
        <div className="eyebrow">API REFERENCE</div>
        <h1>调用方 API</h1>
        <p className="lead">本页是 AI Agent 生成业务集成代码的契约。管理员、内部同步和 API Key 生命周期接口不会在此公开。</p>
        <section id="instructions"><h2>AI 使用规则</h2><div className="callout warning"><ShieldAlert size={18} /><span>只使用本页公开业务 API。不要直接写入 Meilisearch，不要创建或猜测 API Key；只有用户明确授权并提供 Key 后才执行实际请求。</span></div><CodeBlock language="instructions" code={'MUST: 将本页当作 MeliData 业务集成契约，不调用开放平台管理接口。\nMUST: 所有业务写入经过 /api/v1/data/...，搜索经过区域 Agent。\nMUST: 默认 SEARCH_BASE_URL 为 https://meilisearch.1oa.com.cn/documents。\nMUST: 用户明确授权并提供 API Key 后才执行一次真实请求，否则只生成代码。\nDO NOT: 把 /documents 单独当作完整 POST 搜索接口。\nDO NOT: 直接写入 Meilisearch 或创建、申请、猜测 API Key。'} /></section>
        <section id="contract"><h2>核心契约</h2><table className="docs-table"><thead><tr><th>能力</th><th>Scope</th><th>路径</th></tr></thead><tbody><tr><td>写入</td><td><code>data:write</code></td><td><code>POST /api/v1/data/{'{'}collection{'}'}</code>、<code>/batch</code></td></tr><tr><td>读取</td><td><code>data:read</code></td><td><code>GET /api/v1/data/{'{'}collection{'}'}</code></td></tr><tr><td>删除/索引设置</td><td><code>data:write</code></td><td><code>DELETE /api/v1/data/...</code></td></tr><tr><td>区域搜索</td><td><code>search:read</code></td><td><code>POST {'{'}SEARCH_BASE_URL{'}'}/api/v1/collections/{'{'}collection{'}'}/search</code></td></tr></tbody></table><p>默认 <code>SEARCH_BASE_URL</code> 为 <code>https://meilisearch.1oa.com.cn/documents</code>（天津）。其他区域只替换 Base URL。</p></section>
        <section id="endpoints" className="reference-browser">
          <div className="endpoint-list">
            {query.isLoading && <div className="loading-row"><LoaderCircle className="spin" size={18} />正在读取 OpenAPI</div>}
            {query.isError && <div className="inline-error">OpenAPI 暂时不可用，区域搜索契约仍可浏览。</div>}
            {operations.map((operation) => <EndpointButton key={operation.id} operation={operation} selected={selected?.id === operation.id} onClick={() => setSelectedId(operation.id)} />)}
          </div>
          {selected && <OperationDetail operation={selected} />}
        </section>
      </article>
    </DocsLayout>
  )
}

function EndpointButton({ operation, selected, onClick }: { operation: PublicOperation; selected: boolean; onClick: () => void }) {
  return <button className={selected ? 'endpoint-button selected' : 'endpoint-button'} type="button" onClick={onClick}><span className={methodClass(operation.method)}>{operation.method}</span><span><strong>{operation.summary}</strong><code>{operation.path}</code></span><ChevronRight size={16} /></button>
}

function OperationDetail({ operation }: { operation: PublicOperation }) {
 const url = operation.path.replace('{collection}', 'products').replace('{id}', 'doc-001')
 const isPublicDownload = operation.tag === 'sdk'
  const requestUrl = operation.id === 'regional-search'
    ? 'https://meilisearch.1oa.com.cn/documents' + url
    : 'https://meilisearch.1oa.com.cn' + url
 const code = isPublicDownload
    ? `curl -LO https://meilisearch.1oa.com.cn${url}`
    : `curl -X ${operation.method} ${requestUrl} \\
  -H "Authorization: Bearer $MELIDATA_API_KEY" \\
  -H "Content-Type: application/json"`
  const pythonCode = sdkExample(operation)
  const requestBody = operation.requestBodyExample ?? (operation.id === 'regional-search' ? JSON.stringify({ q: 'keyboard', limit: 10 }, null, 2) : null)
  return <div id="operation" className="operation-detail"><div className="operation-title"><span className={methodClass(operation.method)}>{operation.method}</span><code>{operation.id === 'regional-search' ? `POST https://meilisearch.1oa.com.cn/documents${url}` : operation.path}</code></div><h2>{operation.summary}</h2><p>{operation.description || '使用开放平台 API Key 调用此端点。'}</p><h3>认证与 Scope</h3><p>{isPublicDownload ? '无需认证' : <><code>Authorization: Bearer &lt;api_key&gt;</code>{operation.requiredScope && <> · 需要 <code>{operation.requiredScope}</code></>}</>}</p>{operation.parameters.length > 0 && <><h3>参数</h3><table className="docs-table"><tbody>{operation.parameters.map((parameter) => <tr key={parameter.name}><td><code>{parameter.name}</code></td><td>{parameter.in}</td><td>{parameter.required ? '必填' : '可选'}</td><td>{parameter.description || '-'}</td></tr>)}</tbody></table></>}{requestBody && <><h3>请求体</h3><CodeBlock language="json" code={requestBody} /></>}<h3>请求示例</h3><CodeBlock code={code} /><h3>Python SDK 等价调用</h3><CodeBlock language="python" code={pythonCode} /><h3>响应</h3><table className="docs-table"><tbody>{operation.responses.map((response) => <tr key={response.status}><td><code>{response.status}</code></td><td>{response.description || '响应结果'}{response.example && <CodeBlock language="json" code={response.example} />}</td></tr>)}</tbody></table><p><strong>错误策略：</strong><code>401</code>/<code>403</code> 停止并检查权限；<code>404</code>/<code>422</code> 修正参数；<code>429</code>、<code>5xx</code> 和网络错误有限次数退避重试。</p></div>
}

function sdkExample(operation: PublicOperation): string {
  if (operation.id === 'regional-search') return 'import os\nfrom melidata_sdk import MeliDataClient\n\nclient = MeliDataClient(\n    \"https://meilisearch.1oa.com.cn\",\n    os.environ[\"MELIDATA_API_KEY\"],\n    search_url=\"https://meilisearch.1oa.com.cn/documents\",\n)\nresult = client.search(\"products\", query=\"keyboard\", limit=10)'
  if (operation.tag === 'sdk') return 'curl 下载后执行：pip install ./melidata-sdk-0.1.0.zip'
  if (operation.method === 'POST' && operation.path === '/api/v1/data/{collection}') return 'client.upsert_document(\"products\", {\"id\": \"doc-001\", \"name\": \"Keyboard\"})'
  if (operation.method === 'POST' && operation.path.endsWith('/batch')) return 'client.upsert_documents(\"products\", [{\"id\": \"doc-001\", \"name\": \"Keyboard\"}])'
  if (operation.method === 'GET' && operation.path.endsWith('/{id}')) return 'client.get_document(\"products\", \"doc-001\")'
  if (operation.method === 'GET' && operation.path === '/api/v1/data/{collection}') return 'client.list_documents(\"products\", limit=20, offset=0)'
  if (operation.method === 'DELETE' && operation.path.startsWith('/api/v1/data/')) return 'client.delete_document(\"products\", \"doc-001\")'
  if (operation.method === 'GET' && operation.path === '/api/v1/indexes') return 'client.list_indexes(limit=100, offset=0)'
  if (operation.method === 'DELETE' && operation.path.startsWith('/api/v1/indexes/')) return 'client.delete_index(\"products\")'
  if (operation.path.endsWith('/settings')) return 'client.update_index_settings(\"products\", filterable_attributes=[\"category\"], sortable_attributes=[\"price\"])'
  if (operation.path === '/api/v1/agents/online') return 'client.list_agents()'
  return 'client.request(\"' + operation.method + '\", \"' + operation.path.replace('{collection}', 'products').replace('{id}', 'doc-001') + '\")'
}
