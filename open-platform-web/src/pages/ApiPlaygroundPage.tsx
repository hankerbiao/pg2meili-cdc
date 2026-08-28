import { AlertTriangle, LoaderCircle, Send } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { CodeBlock } from '../components/CodeBlock'
import {
  DEFAULT_REGIONAL_SEARCH_BASE_URL,
  PLATFORM_TAG_LABELS,
  regionalSearchOperation,
  type ApiResponseInfo,
  type PublicOperation,
} from '../api/openapi'
import { useOpenApiOperations } from '../api/useOpenApi'

const methodClass = (method: string) => `method method-${method.toLowerCase()}`

// 调试台不提供 Agent、SDK 接口的调试（注册/下载类操作无需在此暴露）
const HIDDEN_PLAYGROUND_TAGS = new Set(['agents', 'sdk'])

function extractPathParams(path: string): string[] {
  return [...path.matchAll(/\{([^}]+)\}/g)].map((match) => match[1])
}

function buildRequestUrl(
  baseUrl: string,
  path: string,
  pathParams: string[],
  pathValues: Record<string, string>,
  queryParams: string[],
  queryValues: Record<string, string>,
): string {
  let fullPath = path
  for (const param of pathParams) {
    fullPath = fullPath.replace(`{${param}}`, encodeURIComponent(pathValues[param] ?? ''))
  }
  const queryPairs: string[] = []
  queryParams.forEach((name) => {
    const value = queryValues[name]?.trim()
    if (value) queryPairs.push(`${name}=${encodeURIComponent(value)}`)
  })
  const base = baseUrl.replace(/\/+$/, '')
  return `${base}${fullPath}${queryPairs.length ? `?${queryPairs.join('&')}` : ''}`
}

interface SendResult {
  status: number
  statusText: string
  duration: number
  headers: string
  body: string
  ok: boolean
  isNetworkError: boolean
}

function statusClass(result: SendResult): string {
  if (result.isNetworkError) return 'status-error'
  if (result.status >= 500) return 'status-5xx'
  if (result.status >= 400) return 'status-4xx'
  if (result.status >= 200 && result.status < 300) return 'status-2xx'
  return 'status-other'
}

export function ApiPlaygroundPage() {
  const query = useOpenApiOperations()
  const operations = useMemo(
    () => [...(query.data ?? []).filter((item) => !HIDDEN_PLAYGROUND_TAGS.has(item.tag)), regionalSearchOperation],
    [query.data],
  )
  const [selectedId, setSelectedId] = useState('regional-search')
  const selected: PublicOperation =
    operations.find((item) => item.id === selectedId) ?? operations[0] ?? regionalSearchOperation

  const sameOriginBaseUrl = typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8080'
  const [regionalSearchBaseUrl, setRegionalSearchBaseUrl] = useState(DEFAULT_REGIONAL_SEARCH_BASE_URL)
  const [apiKey, setApiKey] = useState('')
  const [pathValues, setPathValues] = useState<Record<string, string>>({})
  const [queryValues, setQueryValues] = useState<Record<string, string>>({})
  const [bodyText, setBodyText] = useState(selected.requestBodyExample ?? '')
  const [result, setResult] = useState<SendResult | null>(null)
  const [sending, setSending] = useState(false)

  const pathParams = useMemo(() => extractPathParams(selected.path), [selected.path])
  const queryParams = useMemo(() => selected.parameters.filter((item) => item.in === 'query'), [selected.parameters])
  const hasBody = ['POST', 'PUT', 'PATCH'].includes(selected.method)
  const baseUrl = selected.id === regionalSearchOperation.id ? regionalSearchBaseUrl : sameOriginBaseUrl

  useEffect(() => {
    setPathValues({})
    setQueryValues({})
    setBodyText(selected.requestBodyExample ?? '')
    setResult(null)
  }, [selected.id, selected.requestBodyExample])

  const grouped = useMemo(() => {
    const map = new Map<string, PublicOperation[]>()
    for (const operation of operations) {
      const list = map.get(operation.tag) ?? []
      list.push(operation)
      map.set(operation.tag, list)
    }
    return [...map.entries()]
  }, [operations])

  async function send() {
    const url = buildRequestUrl(baseUrl, selected.path, pathParams, pathValues, queryParams.map((p) => p.name), queryValues)
    setSending(true)
    setResult(null)
    const start = performance.now()
    try {
      const headers = new Headers()
      const trimmedKey = apiKey.trim()
      if (trimmedKey) headers.set('Authorization', `Bearer ${trimmedKey}`)
      const init: RequestInit = { method: selected.method, headers, credentials: 'omit' }
      if (hasBody && bodyText.trim()) {
        headers.set('Content-Type', 'application/json')
        init.body = bodyText
      }
      const response = await fetch(url, init)
      const duration = performance.now() - start
      const text = await response.text()
      let pretty = text
      try {
        pretty = JSON.stringify(JSON.parse(text), null, 2)
      } catch {
        pretty = text
      }
      const headerLines = [...response.headers.entries()].map(([key, value]) => `${key}: ${value}`).join('\n')
      setResult({
        status: response.status,
        statusText: response.statusText,
        duration,
        headers: headerLines,
        body: pretty,
        ok: response.ok,
        isNetworkError: false,
      })
    } catch (error) {
      const duration = performance.now() - start
      setResult({
        status: 0,
        statusText: '网络错误',
        duration,
        headers: '',
        body: String(error instanceof Error ? error.message : error),
        ok: false,
        isNetworkError: true,
      })
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="playground">
      <header className="playground-header">
        <div className="eyebrow">API PLAYGROUND</div>
        <h1>API 调试台</h1>
        <p className="lead">直接调用 MeliData 业务 API（数据与索引接口）。粘贴你的 API Key，填写参数后发送，实时查看响应。</p>
      </header>

      <div className="playground-warning" role="note">
        <AlertTriangle size={18} />
        <p>
          <strong>真实写入提示：</strong>调试台发出的请求会<strong>真实调用线上 API 并写入数据库</strong>（创建 / 更新 / 删除文档、删除索引、修改索引设置等），
          操作不可回滚。请使用测试数据（例如临时 collection）进行验证，谨慎操作。
        </p>
      </div>

      <div className="playground-grid">
        <aside className="playground-endpoints">
          {query.isLoading && (
            <div className="loading-row">
              <LoaderCircle className="spin" size={18} />正在读取 OpenAPI
            </div>
          )}
          {query.isError && <div className="inline-error">OpenAPI 暂时不可用，仅区域搜索可调试。</div>}
          {grouped.map(([tag, list]) => (
            <div key={tag} className="endpoint-group">
              <div className="endpoint-group-label">{PLATFORM_TAG_LABELS[tag] ?? tag}</div>
              {list.map((operation) => (
                <button
                  key={operation.id}
                  type="button"
                  className={selected.id === operation.id ? 'endpoint-button selected' : 'endpoint-button'}
                  onClick={() => setSelectedId(operation.id)}
                >
                  <span className={methodClass(operation.method)}>{operation.method}</span>
                  <span className="endpoint-meta">
                    <strong>{operation.summary}</strong>
                    <code>{operation.path}</code>
                  </span>
                </button>
              ))}
            </div>
          ))}
        </aside>

        <section className="playground-panel">
          <div className="operation-title">
            <span className={methodClass(selected.method)}>{selected.method}</span>
            <code>{selected.path}</code>
          </div>
          <h2>{selected.summary}</h2>
          <p className="operation-desc">{selected.description || '使用开放平台 API Key 调用此端点。'}</p>

          <div className="request-form">
            <label className="field">
              <span className="field-label">Base URL{selected.id === regionalSearchOperation.id ? '（区域节点）' : ''}</span>
              <input
                className="text-input"
                type="url"
                value={baseUrl}
                onChange={(event) => setRegionalSearchBaseUrl(event.target.value)}
                readOnly={selected.id !== regionalSearchOperation.id}
                aria-label="Base URL"
              />
            </label>

            <label className="field">
              <span className="field-label">API Key（Authorization: Bearer）</span>
              <input
                className="text-input"
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder="ud_live_ak_..."
              />
            </label>

            {pathParams.length > 0 && (
              <div className="param-block">
                <div className="param-block-title">路径参数</div>
                {pathParams.map((param) => (
                  <label key={param} className="field inline">
                    <span className="field-label">
                      <code>{param}</code>
                    </span>
                    <input
                      className="text-input"
                      value={pathValues[param] ?? ''}
                      onChange={(event) => setPathValues((prev) => ({ ...prev, [param]: event.target.value }))}
                      placeholder={param}
                    />
                  </label>
                ))}
              </div>
            )}

            {queryParams.length > 0 && (
              <div className="param-block">
                <div className="param-block-title">查询参数</div>
                {queryParams.map((param) => (
                  <label key={param.name} className="field inline">
                    <span className="field-label">
                      <code>{param.name}</code>
                      {param.required && <em className="required">必填</em>}
                      {param.description && <small>{param.description}</small>}
                    </span>
                    <input
                      className="text-input"
                      value={queryValues[param.name] ?? ''}
                      onChange={(event) => setQueryValues((prev) => ({ ...prev, [param.name]: event.target.value }))}
                      placeholder={param.name}
                    />
                  </label>
                ))}
              </div>
            )}

            {hasBody && (
              <label className="field">
                <span className="field-label">请求体（JSON）</span>
                <textarea
                  className="body-input"
                  rows={12}
                  value={bodyText}
                  onChange={(event) => setBodyText(event.target.value)}
                  spellCheck={false}
                />
              </label>
            )}

            <button className="button button-primary send-button" type="button" onClick={send} disabled={sending}>
              {sending ? <LoaderCircle className="spin" size={16} /> : <Send size={16} />}
              {sending ? '发送中…' : '发送请求'}
            </button>
          </div>

          <div className="response-area">
            <h3>响应</h3>
            {!result && <div className="response-empty">尚未发送请求。</div>}
            {result && (
              <>
                <div className={`response-status ${statusClass(result)}`}>
                  <span className="status-code">
                    {result.isNetworkError ? 'ERR' : result.status}
                    {result.statusText ? ` ${result.statusText}` : ''}
                  </span>
                  <span className="status-duration">{Math.round(result.duration)} ms</span>
                </div>

                {result.headers && (
                  <div className="response-section">
                    <div className="response-section-title">响应头</div>
                    <CodeBlock code={result.headers} language="http" />
                  </div>
                )}

                <div className="response-section">
                  <div className="response-section-title">响应体</div>
                  <CodeBlock code={result.body} language="json" />
                </div>

                {selected.responses.length > 0 && <ResponseDocs responses={selected.responses} />}
              </>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}

function ResponseDocs({ responses }: { responses: ApiResponseInfo[] }) {
  return (
    <div className="response-section">
      <div className="response-section-title">状态码说明</div>
      <ul className="response-docs">
        {responses.map((item) => (
          <li key={item.status}>
            <code className={`doc-status doc-${item.status[0]}xx`}>{item.status}</code>
            <span>{item.description}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
