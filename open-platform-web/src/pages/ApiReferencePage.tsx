import { ExternalLink, LoaderCircle, Search, ShieldAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import { CodeBlock } from '../components/CodeBlock'
import { DocsLayout } from '../components/DocsLayout'
import {
  DEFAULT_REGIONAL_SEARCH_BASE_URL,
  PLATFORM_TAG_LABELS,
  regionalSearchOperation,
  type PublicOperation,
} from '../api/openapi'
import { useOpenApiOperations } from '../api/useOpenApi'

const DATA_API_BASE_URL = 'https://meilisearch.1oa.com.cn'
const methodClass = (method: string) => `method method-${method.toLowerCase()}`
const tagLabel = (tag: string) => tag === 'search' ? '区域搜索' : PLATFORM_TAG_LABELS[tag] ?? tag

function samplePath(operation: PublicOperation) {
  return operation.path
    .replace('{collection}', 'products')
    .replace('{id}', 'sku-001')
}

function sampleValue(name: string, example?: unknown) {
  if (example !== undefined && example !== null) return String(example)
  if (name === 'collection') return 'products'
  if (name === 'id') return 'sku-001'
  if (name === 'region') return 'shanghai'
  if (name === 'limit') return '20'
  if (name === 'offset') return '0'
  return 'example'
}

function requestUrl(operation: PublicOperation) {
  const baseUrl = operation.id === 'regional-search' ? DEFAULT_REGIONAL_SEARCH_BASE_URL : DATA_API_BASE_URL
  const params = operation.parameters
    .filter((parameter) => parameter.in === 'query')
    .map((parameter) => `${encodeURIComponent(parameter.name)}=${encodeURIComponent(sampleValue(parameter.name, parameter.example))}`)
  return `${baseUrl}${samplePath(operation)}${params.length ? `?${params.join('&')}` : ''}`
}

function curlExample(operation: PublicOperation) {
  const lines = [
    `curl --fail-with-body -X ${operation.method} \\`,
    `  "${requestUrl(operation)}" \\`,
    '  -H "Authorization: Bearer $MELIDATA_API_KEY"',
  ]
  if (operation.requestBodyExample || operation.id === 'regional-search') {
    lines[2] += ' \\'
    lines.push('  -H "Content-Type: application/json" \\', '  --data-binary @request.json')
  }
  return lines.join('\n')
}

export function ApiReferencePage() {
  const query = useOpenApiOperations()
  const operations = useMemo(
    () => [...(query.data ?? []).filter((operation) => operation.tag !== 'sdk'), regionalSearchOperation],
    [query.data],
  )
  const [selectedId, setSelectedId] = useState('regional-search')
  const [searchText, setSearchText] = useState('')
  const [methodFilter, setMethodFilter] = useState('ALL')
  const filteredOperations = useMemo(() => {
    const needle = searchText.trim().toLocaleLowerCase()
    return operations.filter((operation) => {
      if (methodFilter !== 'ALL' && operation.method !== methodFilter) return false
      if (!needle) return true
      return [operation.summary, operation.path, operation.description, operation.requiredScope]
        .some((value) => value?.toLocaleLowerCase().includes(needle))
    })
  }, [methodFilter, operations, searchText])
  const groups = useMemo(() => {
    const result = new Map<string, PublicOperation[]>()
    for (const operation of filteredOperations) {
      const group = result.get(operation.tag) ?? []
      group.push(operation)
      result.set(operation.tag, group)
    }
    return [...result.entries()]
  }, [filteredOperations])
  const selected = filteredOperations.find((operation) => operation.id === selectedId) ?? filteredOperations[0]

  return (
    <DocsLayout toc={[
      { href: '#basics', label: '地址与认证' },
      { href: '#endpoints', label: '查找接口' },
      { href: '#operation', label: '请求详情' },
      { href: '#errors', label: '错误处理' },
    ]}>
      <article className="doc-article reference-article">
        <div className="eyebrow">API REFERENCE</div>
        <h1>API 参考</h1>
        <p className="lead">按接口查看请求路径、权限范围、参数、请求体和响应示例。所有示例均使用 cURL，可直接改写为你的服务端语言。</p>

        <section id="basics" className="reference-basics">
          <h2>地址与认证</h2>
          <div className="reference-base-grid">
            <div className="reference-base-card">
              <span>数据与索引 API</span>
              <code>{DATA_API_BASE_URL}</code>
              <small>写入、读取文档和索引操作</small>
            </div>
            <div className="reference-base-card">
              <span>区域搜索 API</span>
              <code>{DEFAULT_REGIONAL_SEARCH_BASE_URL}</code>
              <small>天津默认入口；其他区域使用对应 Agent 地址</small>
            </div>
          </div>
          <div className="callout reference-auth-callout">
            <ShieldAlert size={18} />
            <span>请求使用 <code>Authorization: Bearer $MELIDATA_API_KEY</code>。按接口所需 scope 授权：<code>data:read</code>、<code>data:write</code> 或 <code>search:read</code>。请在服务端保存 Key，不要放入浏览器代码。</span>
          </div>
          <p className="reference-openapi-link">完整机器可读定义：<a href="/openapi.json" target="_blank" rel="noreferrer">OpenAPI JSON <ExternalLink size={14} /></a></p>
        </section>

        <section id="endpoints" className="reference-endpoints-section">
          <div className="reference-section-heading">
            <div><h2>查找接口</h2><p>按名称、路径或权限搜索，再选择接口查看详情。</p></div>
            <span className="reference-count">{filteredOperations.length} 个接口</span>
          </div>
          <div className="reference-browser">
            <div className="endpoint-list">
              <div className="reference-toolbar">
                <label className="reference-search">
                  <Search size={16} aria-hidden="true" />
                  <input aria-label="搜索 API" value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="搜索名称、路径或 scope" />
                </label>
                <label className="reference-method-filter">
                  <span>方法</span>
                  <select aria-label="按 HTTP 方法筛选" value={methodFilter} onChange={(event) => setMethodFilter(event.target.value)}>
                    <option value="ALL">全部</option>
                    {[...new Set(operations.map((operation) => operation.method))].sort().map((method) => <option key={method} value={method}>{method}</option>)}
                  </select>
                </label>
              </div>
              {query.isLoading && <div className="loading-row"><LoaderCircle className="spin" size={18} />正在读取 OpenAPI</div>}
              {query.isError && <div className="inline-error">OpenAPI 暂时不可用，区域搜索接口仍可浏览。</div>}
              {!query.isLoading && groups.length === 0 && <div className="reference-empty">没有匹配的接口。试试其他关键词或 HTTP 方法。</div>}
              {groups.map(([tag, items]) => (
                <section className="endpoint-group" key={tag} aria-label={`${tagLabel(tag)}接口`}>
                  <h3 className="endpoint-group-label">{tagLabel(tag)} <span>{items.length}</span></h3>
                  {items.map((operation) => <EndpointButton key={operation.id} operation={operation} selected={selected?.id === operation.id} onClick={() => setSelectedId(operation.id)} />)}
                </section>
              ))}
            </div>
            {selected ? <OperationDetail operation={selected} /> : <div className="operation-detail reference-empty-detail">选择一个接口查看请求说明。</div>}
          </div>
        </section>

        <section id="errors" className="reference-errors">
          <h2>常见错误处理</h2>
          <div className="reference-error-grid">
            <div><code>401 / 403</code><span>检查 Key 是否有效，以及是否包含接口要求的 scope。</span></div>
            <div><code>404 / 422</code><span>检查集合名、文档 ID、查询参数和请求体格式。</span></div>
            <div><code>429 / 5xx</code><span>遵循 Retry-After；无该响应头时使用有限次数的退避重试。</span></div>
          </div>
        </section>
      </article>
    </DocsLayout>
  )
}

function EndpointButton({ operation, selected, onClick }: { operation: PublicOperation; selected: boolean; onClick: () => void }) {
  return (
    <button className={selected ? 'endpoint-button selected' : 'endpoint-button'} type="button" aria-pressed={selected} onClick={onClick}>
      <span className={methodClass(operation.method)}>{operation.method}</span>
      <span className="endpoint-meta"><strong>{operation.summary}</strong><code>{operation.path}</code></span>
    </button>
  )
}

function OperationDetail({ operation }: { operation: PublicOperation }) {
  const body = operation.requestBodyExample ?? (operation.id === 'regional-search' ? JSON.stringify({ q: 'keyboard', limit: 10 }, null, 2) : null)
  return (
    <div id="operation" className="operation-detail">
      <div className="operation-detail-heading">
        <span className={methodClass(operation.method)}>{operation.method}</span>
        <span className="operation-tag">{tagLabel(operation.tag)}</span>
      </div>
      <h2>{operation.summary}</h2>
      <p className="operation-description">{operation.description || '接口说明请以请求参数和响应定义为准。'}</p>

      <div className="operation-meta-grid">
        <div><span>请求地址</span><code>{requestUrl(operation)}</code></div>
        <div><span>权限范围</span><code>{operation.requiredScope ?? '以服务端鉴权策略为准'}</code></div>
      </div>

      <section className="operation-doc-section">
        <h3>请求参数</h3>
        {operation.parameters.length ? (
          <div className="table-scroll"><table className="docs-table reference-params-table"><thead><tr><th>名称</th><th>位置</th><th>要求</th><th>示例</th><th>说明</th></tr></thead><tbody>
            {operation.parameters.map((parameter) => <tr key={`${parameter.in}-${parameter.name}`}><td><code>{parameter.name}</code></td><td>{parameter.in === 'path' ? '路径' : '查询'}</td><td>{parameter.required ? '必填' : '可选'}</td><td><code>{sampleValue(parameter.name, parameter.example)}</code></td><td>{parameter.description || '—'}</td></tr>)}
          </tbody></table></div>
        ) : <p className="reference-muted">此接口没有额外的路径或查询参数。</p>}
      </section>

      {body && <section className="operation-doc-section"><h3>请求体示例</h3><CodeBlock language="json" code={body} /><p className="reference-muted">保存为 <code>request.json</code>，供下面的 cURL 示例读取。</p></section>}

      <section className="operation-doc-section"><h3>cURL 请求示例</h3><CodeBlock language="bash" code={curlExample(operation)} /></section>

      <section className="operation-doc-section">
        <h3>响应</h3>
        {operation.responses.length ? <div className="reference-responses">
          {operation.responses.map((response) => <details className="reference-response" key={response.status} open={response.status.startsWith('2')}>
            <summary><code className={`response-status response-${response.status[0]}xx`}>{response.status}</code><span>{response.description || '响应结果'}</span></summary>
            {response.example && <CodeBlock language="json" code={response.example} />}
          </details>)}
        </div> : <p className="reference-muted">响应格式以服务端返回为准。</p>}
      </section>
    </div>
  )
}
