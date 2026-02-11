import React, { useEffect, useMemo, useState } from 'react'
import { search, SearchRequest, SearchResponse, SearchHit } from '../api'

const DEFAULT_TOKEN =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcHBfbmFtZSI6ImxpYmlhbyIsInNjb3BlcyI6WyJzZWFyY2g6cmVhZCJdLCJleHAiOjE4MDE1MjYzOTcsImlhdCI6MTc3MDc4ODk3NiwianRpIjoiMTBhNDhjYmEtMmRkZC00M2Y4LTg4OTgtOGY3ZWFlYzI3MDljIn0.Bf2E51dWPIbgsJlAjkBvzZV7pn2oKUJjg70r8Holr1M'
const DEFAULT_BASE_URL = 'http://10.32.129.188:8091'
// 默认从当前页面的后端域名获取在线代理列表
const AGENTS_API_BASE = 'http://10.32.129.188:8080'

interface OnlineAgent {
  ip: string
  port: number
  hostname?: string
}

const BrowserSearchPage: React.FC = () => {
  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE_URL)
  const [token, setToken] = useState(DEFAULT_TOKEN)
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

  const agentsEndpoint = useMemo(() => {
    const base =
      AGENTS_API_BASE ||
      (typeof window !== 'undefined' ? window.location.origin : '')
    const normalized = base.replace(/\/$/, '')
    return `${normalized}/api/v1/agents/online`
  }, [])

  const formatAgentBaseUrl = (agent: OnlineAgent) => `http://${agent.ip}:${agent.port}`

  useEffect(() => {
    if (!token.trim()) return
    const controller = new AbortController()
    const loadAgents = async () => {
      setAgentsLoading(true)
      setAgentsError(null)
      try {
        const response = await fetch(agentsEndpoint, {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${token}`,
          },
          signal: controller.signal,
        })
        if (!response.ok) {
          const errorText = await response.text()
          throw new Error(`HTTP ${response.status}: ${errorText}`)
        }
        const payload = await response.json() as any
        const list: OnlineAgent[] = Array.isArray(payload?.data)
          ? payload.data
          : (Array.isArray(payload) ? payload : [])
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
  }, [agentsEndpoint, autoSelectBaseUrl, token])

  const buildCurl = (): string => {
    let url = `${baseUrl.replace(/\/$/, '')}/search`
    const displayToken = token.trim() || '<YOUR_JWT>'
    
    const req: SearchRequest = {}
    if (query.trim()) req.q = query.trim()
    if (highlight) req.attributesToHighlight = ['*']
    req.attributesToCrop = ['content']
    req.cropLength = 60
    if (filter.trim()) req.filter = [filter.trim()]
    if (collection.trim()) req.collection = collection.trim()

    const { collection: coll, ...body } = req
    if (coll) {
      const encoded = encodeURIComponent(coll)
      const sep = url.includes('?') ? '&' : '?'
      url = `${url}${sep}collection=${encoded}`
    }

    let prettyBody = JSON.stringify(body, null, 2)
    const safeBody = prettyBody.replace(/'/g, `'\"'\"'`)
    
    return [
      `curl -X POST "${url}" \\`,
      `  -H "Content-Type: application/json" \\`,
      `  -H "Authorization: Bearer ${displayToken}" \\`,
      `  --data-raw '${safeBody}'`,
    ].join('\n')
  }

  const handleSearch = async () => {
    setError(null)
    setLoading(true)
    try {
      const req: SearchRequest = {}
      if (query.trim()) {
        req.q = query.trim()
      }
      if (highlight) {
        req.attributesToHighlight = ['*']
      }
      req.attributesToCrop = ['content']
      req.cropLength = 60
      if (filter.trim()) {
        req.filter = [filter.trim()]
      }
      if (collection.trim()) {
        req.collection = collection.trim()
      }
      const result = await search(baseUrl, token, req)
      setResponse(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : '未知错误')
      setResponse(null)
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  // Parse highlighting tags <em>...</em>
  const parseHighlight = (text: string, enableHighlight: boolean): React.ReactNode[] => {
    if (!text) return []
    const parts: React.ReactNode[] = []
    // Match <em>content</em> lazily
    const regex = /<em>(.*?)<\/em>/g
    let lastIndex = 0
    let match: RegExpExecArray | null

    while ((match = regex.exec(text)) !== null) {
      // Text before match
      const beforeText = text.slice(lastIndex, match.index)
      if (beforeText) {
        parts.push(beforeText)
      }
      // Content inside <em>
      const content = match[1] // group 1
      if (enableHighlight) {
        parts.push(<em key={match.index}>{content}</em>)
      } else {
        parts.push(content)
      }
      lastIndex = regex.lastIndex
    }
    // Remaining text
    const remaining = text.slice(lastIndex)
    if (remaining) {
      parts.push(remaining)
    }
    return parts.length > 0 ? parts : [text]
  }

  const renderHit = (hit: SearchHit) => {
    const name =
      hit._formatted?.name ||
      hit.name ||
      hit._formatted?.title ||
      (hit as any).title ||
      (hit as any).author ||
      ''
    const summary =
      hit._formatted?.summary ||
      hit.summary ||
      ''
    const content =
      (hit as any)._formatted?.content ||
      (hit as any).content ||
      ''
    const rawUrl = typeof hit.ext_id === 'string' ? hit.ext_id : ''
    // Mocking a domain for visual purpose if ext_id is just a path or ID
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
            {parseHighlight(name, highlight)}
        </div>
        {summary && (
          <div className="browser-hit-summary">
              {parseHighlight(summary, highlight)}
          </div>
        )}
        {!summary && content && (
          <div className="browser-hit-summary">
              {parseHighlight(content, highlight)}
          </div>
        )}
        {(hit as any).author && (
          <div className="browser-hit-summary">
              作者：{(hit as any).author}
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
        <div className="browser-tabs">
          <div className="browser-tab active">测试用例（Mock）</div>
          <div className="browser-tab">Bug 信息（Mock）</div>
        </div>
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
              const label = agent.hostname
                ? `${agent.hostname} (${agent.ip}:${agent.port})`
                : `${agent.ip}:${agent.port}`
              return (
                <option key={url} value={url}>
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
          disabled={loading || !token}
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
          <span>JWT</span>
          <input
            className="browser-sub-input"
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
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
            <pre>{buildCurl()}</pre>
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
