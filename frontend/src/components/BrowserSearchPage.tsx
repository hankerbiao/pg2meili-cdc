import React, { useState } from 'react'
import { search, SearchRequest, SearchResponse, SearchHit } from '../api'

const DEFAULT_TOKEN =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcHBfbmFtZSI6Im15YXBwIiwic2NvcGVzIjpbXSwiZXhwIjoyMDg0OTI3MzAwfQ.XeQ_PTo1WqIRBn6jY3vqxETD61PwJUUAHpsTfSHH_Ok'

const BrowserSearchPage: React.FC = () => {
  const [baseUrl, setBaseUrl] = useState('http://10.2.48.121:8091')
  const [token, setToken] = useState(DEFAULT_TOKEN)
  const [query, setQuery] = useState('电源')
  const [filter, setFilter] = useState('')
  const [highlight, setHighlight] = useState(false)
  const [collection, setCollection] = useState('testcases')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [response, setResponse] = useState<SearchResponse | null>(null)
  const [showCurl, setShowCurl] = useState(false)

  const buildCurl = (): string => {
    let url = `${baseUrl.replace(/\/$/, '')}/search`
    const displayToken = token.trim() || '<YOUR_JWT>'
    
    const req: SearchRequest = {}
    if (query.trim()) req.q = query.trim()
    if (highlight) req.attributesToHighlight = ['*']
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
    const name = hit._formatted?.name || hit.name || ''
    const summary = hit._formatted?.summary || hit.summary || ''
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
        <div className="browser-hit-summary">
            {parseHighlight(summary, highlight)}
        </div>
        <div className="browser-hit-tags">
            {hit.tags?.map(tag => (
                <span key={tag} className="browser-tag">{tag}</span>
            ))}
        </div>
      </div>
    )
  }

  return (
    <div className="browser-page">
      <div className="browser-topbar">
        <div className="browser-tabs">
          <div className="browser-tab active">测试用例（Mock）</div>
          <div className="browser-tab">Bug 信息（Mock）</div>
        </div>
        <div className="browser-actions">
          <input
            className="browser-config-input"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="Search API Base URL"
          />
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
            placeholder='例如：testcases'
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
