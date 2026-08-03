import { useEffect, useState } from 'react'
import { search } from '../api'
import type { SearchHit, SearchRequest, SearchResponse } from '../api'
import { buildSearchCurl, renderHighlight } from '../searchUtils'

const DEFAULT_API_KEY = import.meta.env.VITE_DEFAULT_API_KEY ?? ''
const DEFAULT_BASE_URL = import.meta.env.VITE_DEFAULT_SEARCH_BASE_URL?.trim() || 'http://127.0.0.1:8091'
const AGENTS_API_BASE = import.meta.env.VITE_AGENTS_API_BASE?.trim() || window.location.origin
const AGENTS_ENDPOINT = `${AGENTS_API_BASE.replace(/\/$/, '')}/api/v1/agents/online`

interface OnlineAgent {
  id?: string
  ip: string
  port: number
  hostname?: string
  base_url?: string
  region?: string
  status?: string
  weight?: number
}

const formatAgentBaseUrl = (agent: OnlineAgent) =>
  agent.base_url?.trim().replace(/\/$/, '') || `http://${agent.ip}:${agent.port}`

const BrowserSearchPage = () => {
  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE_URL)
  const [apiKey, setApiKey] = useState(DEFAULT_API_KEY)
  const [query, setQuery] = useState('电源')
  const [filter, setFilter] = useState('')
  const [highlight, setHighlight] = useState(false)
  const [collection, setCollection] = useState('testcases')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [response, setResponse] = useState<SearchResponse | null>(null)
  const [showCurl, setShowCurl] = useState(false)
  const [agents, setAgents] = useState<OnlineAgent[]>([])
  const [agentsLoading, setAgentsLoading] = useState(false)
  const [agentsError, setAgentsError] = useState<string | null>(null)
  const [autoSelectBaseUrl, setAutoSelectBaseUrl] = useState(true)

  useEffect(() => {
    if (!apiKey.trim()) return
    const controller = new AbortController()
    const loadAgents = async () => {
      setAgentsLoading(true)
      setAgentsError(null)
      try {
        const response = await fetch(AGENTS_ENDPOINT, {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${apiKey}`,
          },
          signal: controller.signal,
        })
        if (!response.ok) {
          const errorText = await response.text()
          throw new Error(`HTTP ${response.status}: ${errorText}`)
        }
        const payload = await response.json() as { data?: OnlineAgent[] } | OnlineAgent[]
        const list = Array.isArray(payload) ? payload : payload.data ?? []
        setAgents(list)
        if (list.length > 0 && autoSelectBaseUrl) {
          const nextBaseUrl = formatAgentBaseUrl(list[0])
          setBaseUrl(nextBaseUrl)
        }
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') return
        setAgentsError(e instanceof Error ? e.message : '获取在线节点失败')
      } finally {
        setAgentsLoading(false)
      }
    }
    loadAgents()
    return () => controller.abort()
  }, [autoSelectBaseUrl, apiKey])

  const buildRequest = (): SearchRequest => {
    const trimmedQuery = query.trim()
    const trimmedFilter = filter.trim()
    const trimmedCollection = collection.trim()
    return {
      ...(trimmedQuery && { q: trimmedQuery }),
      ...(highlight && { attributesToHighlight: ['*'] }),
      attributesToCrop: ['content'],
      cropLength: 60,
      ...(trimmedFilter && { filter: [trimmedFilter] }),
      ...(trimmedCollection && { collection: trimmedCollection }),
    }
  }

  const handleSearch = async () => {
    setError(null)
    setLoading(true)
    try {
      const result = await search(baseUrl, apiKey, buildRequest())
      setResponse(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : '未知错误')
      setResponse(null)
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  const renderHit = (hit: SearchHit) => {
    const name =
      hit._formatted?.name ||
      hit.name ||
      hit._formatted?.title ||
      hit.title ||
      hit.author ||
      ''
    const summary =
      hit._formatted?.summary ||
      hit.summary ||
      ''
    const description = summary || hit._formatted?.content || hit.content
    const rawUrl = typeof hit.ext_id === 'string' ? hit.ext_id : ''
    const displayUrl = rawUrl && rawUrl.startsWith('http')
      ? rawUrl
      : `test-case-repository > ${rawUrl || hit.id}`
    
    return (
      <div key={hit.id} className="browser-hit">
        <div className="browser-hit-header">
           <div className="browser-hit-icon">
             <span>📄</span>
           </div>
           <div className="browser-hit-meta">
             <div className="browser-hit-site-name">测试用例仓库</div>
             <div className="browser-hit-url">{displayUrl}</div>
           </div>
        </div>
        <div className="browser-hit-title">
            {renderHighlight(name, highlight)}
        </div>
        {description && (
          <div className="browser-hit-summary">
              {renderHighlight(description, highlight)}
          </div>
        )}
        {hit.author && (
          <div className="browser-hit-summary">
              作者：{hit.author}
          </div>
        )}
        <div className="browser-hit-tags">
            {hit.tags?.map(tag => (
                <span key={tag} className="browser-tag">{tag}</span>
            ))}
        </div>
      </div>
    )
  }

  const baseUrlInList = agents.some(agent => formatAgentBaseUrl(agent) === baseUrl)

  return (
    <div className="browser-page">
      <div className="browser-topbar">
        <div className="browser-tab active">测试用例（Mock）</div>
        <div className="browser-actions">
          <select
            className="browser-config-input"
            value={baseUrl}
            onChange={(e) => {
              setAutoSelectBaseUrl(false)
              setBaseUrl(e.target.value)
            }}
          >
            {!agentsLoading && !baseUrlInList && baseUrl && (
              <option value={baseUrl}>{`当前地址: ${baseUrl}`}</option>
            )}
            {agentsLoading && (
              <option value={baseUrl}>加载中...</option>
            )}
            {!agentsLoading && agents.length === 0 && (
              <option value={baseUrl}>
                {agentsError ? '加载失败' : '暂无在线节点'}
              </option>
            )}
            {agents.map((agent) => {
              const url = formatAgentBaseUrl(agent)
              const nodeLabel = agent.hostname
                ? `${agent.hostname} (${agent.ip}:${agent.port})`
                : `${agent.ip}:${agent.port}`
              const label = agent.region ? `${nodeLabel} · ${agent.region}` : nodeLabel
              return (
                <option key={agent.id || url} value={url}>
                  {label}
                </option>
              )
            })}
          </select>
        </div>
      </div>
      <div className="browser-toolbar">
        <input
          className="browser-address-bar"
          placeholder="输入搜索关键字，例如：电源"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          className="browser-go-btn"
          onClick={handleSearch}
          disabled={loading || !apiKey}
        >
          {loading ? '搜索中...' : '搜索'}
        </button>
      </div>
      <div className="browser-subbar">
        <div className="browser-subfield">
          <span>Collection</span>
          <input
            className="browser-sub-input"
            placeholder='例如：shared_docs'
            value={collection}
            onChange={(e) => setCollection(e.target.value)}
            onKeyDown={handleKeyDown}
          />
        </div>
        <div className="browser-subfield">
          <span>过滤条件</span>
          <input
            className="browser-sub-input"
            placeholder='例如：lab = "BMC"'
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            onKeyDown={handleKeyDown}
          />
        </div>
        <div className="browser-subfield">
          <label className="browser-checkbox">
            <input
              type="checkbox"
              checked={highlight}
              onChange={(e) => setHighlight(e.target.checked)}
            />
            高亮匹配
          </label>
        </div>
        <div className="browser-subfield">
          <span>API Key</span>
          <input
            className="browser-sub-input"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </div>
        <button 
          className="browser-text-btn" 
          onClick={() => setShowCurl(!showCurl)}
          title="显示 cURL 命令"
        >
          {showCurl ? '隐藏 cURL' : 'cURL'}
        </button>
      </div>
      {showCurl && (
        <div className="browser-curl-box">
            <pre>{buildSearchCurl(baseUrl, apiKey, buildRequest())}</pre>
        </div>
      )}
      <div className="browser-content">
        {error && (
          <div className="browser-error">
            {error}
          </div>
        )}
        {response && (
          <div className="browser-results">
            <div className="browser-results-header">
              找到约 {response.estimatedTotalHits ?? response.hits.length} 条结果
              {response.processingTimeMs && (
                  <span style={{marginLeft: 10, fontSize: 12, color: '#9aa0a6'}}>
                      ({response.processingTimeMs} ms)
                  </span>
              )}
            </div>
            <div className="browser-hits">
              {response.hits.map(renderHit)}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default BrowserSearchPage
