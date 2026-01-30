import React, { useState } from 'react'
import { search, PRESET_SCENARIOS, SearchRequest, SearchResponse, SearchHit } from '../api'

const DEFAULT_TOKEN = ''

const buildCurl = (baseUrl: string, token: string, body: string): string => {
  const url = `${baseUrl}/search`
  const displayToken = token.trim() || '<YOUR_JWT>'
  let prettyBody = body
  try {
    prettyBody = JSON.stringify(JSON.parse(body), null, 2)
  } catch {
  }
  const safeBody = prettyBody.replace(/'/g, `'\"'\"'`)
  return [
    `curl -X POST "${url}" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -H "Authorization: Bearer ${displayToken}" \\`,
    `  --data-raw '${safeBody}'`,
  ].join('\n')
}

const parseCurlCommand = (cmd: string) => {
  // URL
  const urlMatch = cmd.match(/curl.*?["'](http.*?)["']/) || cmd.match(/\s(http\S+)/)
  const fullUrl = urlMatch ? urlMatch[1] : null
  let baseUrl = null
  if (fullUrl) {
    try {
      const urlObj = new URL(fullUrl)
      baseUrl = urlObj.origin
    } catch {}
  }

  // Token
  const tokenMatch = cmd.match(/Authorization: Bearer\s+([^\s"']+)/)
  const token = tokenMatch ? tokenMatch[1] : null

  // Body
  let body = '{}'
  const dataMarkers = ['--data-raw \'', '--data \'', '-d \'']
  for (const marker of dataMarkers) {
      const idx = cmd.indexOf(marker)
      if (idx !== -1) {
          let rawBody = cmd.slice(idx + marker.length)
          const lastQuote = rawBody.lastIndexOf("'")
          if (lastQuote !== -1) {
              rawBody = rawBody.slice(0, lastQuote)
          }
          // Restore single quotes
          body = rawBody.replace(/'"'"'/g, "'")
          break
      }
  }
  
  return { baseUrl, token, body }
}

const SearchTester: React.FC = () => {
  const [baseUrl, setBaseUrl] = useState('http://10.2.48.121:8091')
  const [token, setToken] = useState(DEFAULT_TOKEN)
  const [selectedScenario, setSelectedScenario] = useState<number>(0)
  const [customRequest, setCustomRequest] = useState<string>(
    JSON.stringify(PRESET_SCENARIOS[0].request, null, 2)
  )
  const [curlText, setCurlText] = useState('')
  const [response, setResponse] = useState<SearchResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // Sync curlText when dependencies change
  React.useEffect(() => {
    setCurlText(buildCurl(baseUrl, token, customRequest))
  }, [baseUrl, token, customRequest])

  const executeSearch = async (request: SearchRequest, overrideBaseUrl?: string, overrideToken?: string) => {
    setLoading(true)
    setError(null)

    try {
      const targetBaseUrl = overrideBaseUrl || baseUrl
      const targetToken = overrideToken || token
      const result = await search(targetBaseUrl, targetToken, request)
      setResponse(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : '未知错误')
      setResponse(null)
    } finally {
      setLoading(false)
    }
  }

  const handleScenarioChange = (index: number) => {
    setSelectedScenario(index)
    setCustomRequest(JSON.stringify(PRESET_SCENARIOS[index].request, null, 2))
    // 自动执行搜索
    executeSearch(PRESET_SCENARIOS[index].request)
  }

  const handleManualSearch = () => {
    try {
      const parsed = parseCurlCommand(curlText)
      // Update state controls if parsed
      if (parsed.baseUrl) setBaseUrl(parsed.baseUrl)
      if (parsed.token) setToken(parsed.token)
      
      const request = JSON.parse(parsed.body)
      executeSearch(request, parsed.baseUrl || baseUrl, parsed.token || token)
    } catch (e) {
      setError('解析 CURL 失败: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  const handleLoadMore = async () => {
    if (!response) return

    setLoading(true)
    setError(null)

    try {
      const currentOffset = response.offset || 0
      const currentLimit = response.limit || 20
      const request: SearchRequest = {
        ...JSON.parse(customRequest),
        offset: currentOffset + currentLimit,
      }
      const result = await search(baseUrl, token, request)
      setResponse({
        ...result,
        hits: [...response.hits, ...result.hits],
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : '未知错误')
    } finally {
      setLoading(false)
    }
  }

  // 解析 Meilisearch 高亮标签 <em>keyword</em>
  const parseHighlight = (text: string): React.ReactNode[] => {
    const parts: React.ReactNode[] = []
    const regex = /(<em>|<\/em>)/g
    let lastIndex = 0
    let match: RegExpExecArray | null

    while ((match = regex.exec(text)) !== null) {
      const beforeText = text.slice(lastIndex, match.index)
      if (beforeText) {
        parts.push(beforeText)
      }
      parts.push(match[0])
      lastIndex = regex.lastIndex
    }

    const remainingText = text.slice(lastIndex)
    if (remainingText) {
      parts.push(remainingText)
    }

    const result: React.ReactNode[] = []
    let highlightBuffer = ''
    let inHighlight = false

    for (const part of parts) {
      if (typeof part === 'string') {
        if (part === '<em>') {
          inHighlight = true
        } else if (part === '</em>') {
          if (highlightBuffer) {
            result.push(<em key={result.length}>{highlightBuffer}</em>)
            highlightBuffer = ''
          }
          inHighlight = false
        } else if (inHighlight) {
          highlightBuffer += part
        } else {
          result.push(part)
        }
      }
    }

    return result
  }

  const renderHit = (hit: SearchHit) => {
    const name = hit._formatted?.name || hit.name
    const summary = hit._formatted?.summary || hit.summary

    return (
      <div key={hit.id} className="hit-card">
        <div className="hit-header">
          <span className="hit-ext-id">{hit.ext_id}</span>
          <span className="hit-id">#{hit.id}</span>
        </div>
        <h3 className="hit-name">
          {parseHighlight(name)}
        </h3>
        <p className="hit-summary">
          {parseHighlight(summary)}
        </p>
        <div className="hit-tags">
          {hit.tags.map((tag, i) => (
            <span key={i} className="tag">{tag}</span>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="search-tester">
      <header className="header">
        <h1>搜索接口测试工具</h1>
        <p>基于 Meilisearch 的测试用例搜索</p>
      </header>

      <div className="main-container">
        {/* 左边 - 预设场景 */}
        <aside className="sidebar">
          <div className="sidebar-title">预设场景</div>
          <div className="scenario-list">
            {PRESET_SCENARIOS.map((scenario, index) => (
              <div
                key={index}
                className={`scenario-item ${selectedScenario === index ? 'active' : ''}`}
                onClick={() => handleScenarioChange(index)}
              >
                <div className="scenario-name">{scenario.name}</div>
                <div className="scenario-desc">{scenario.description}</div>
              </div>
            ))}
          </div>
        </aside>

        {/* 右边 - 配置、请求、结果 */}
        <main className="content">
          {/* 配置区域 */}
          <section className="config-section">
            <h2>配置</h2>
            <div className="config-row">
              <div className="config-field">
                <label>API 地址</label>
                <input
                  type="text"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                />
              </div>
            </div>
            <div className="config-row">
              <div className="config-field">
                <label>JWT Token</label>
                <input
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                />
              </div>
            </div>
          </section>

          {/* 请求参数 */}
          <section className="request-section">
            <div className="section-header">
              <h2>请求参数</h2>
            </div>
            
            <div className="request-body-container">
              <div className="request-detail-panel">
                <div className="request-detail">
                  <pre className="request-info">
                    <strong>POST</strong> {baseUrl}/search
                    {'\n'}
                    <strong>Headers:</strong>
                    {'\n'}  Authorization: Bearer [token]
                    {'\n'}  Content-Type: application/json
                  </pre>
                  <div className="curl-preview">
                    <div className="curl-title">curl 命令 (可编辑)</div>
                    <textarea 
                      className="curl-editor"
                      value={curlText}
                      onChange={(e) => setCurlText(e.target.value)}
                      spellCheck={false}
                    />
                  </div>
                </div>
              </div>
            </div>

            <button
              className="execute-btn"
              onClick={handleManualSearch}
              disabled={loading || !token}
            >
              {loading ? '搜索中...' : '执行搜索'}
            </button>
          </section>

          {/* 错误信息 */}
          {error && (
            <section className="error-section">
              <pre className="error-content">{error}</pre>
            </section>
          )}

          {/* 搜索结果 */}
          {response && (
            <section className="result-section">
              <div className="result-header">
                <h2>搜索结果</h2>
                <div className="result-stats">
                  <span>总数: {response.estimatedTotalHits || response.hits.length}</span>
                  <span>返回: {response.hits.length} 条</span>
                  <span>耗时: {response.processingTimeMs || '-'}ms</span>
                </div>
              </div>
              {response.hits.length === 0 ? (
                <div className="no-results">未找到匹配的测试用例</div>
              ) : (
                <>
                  <div className="hits-list">
                    {response.hits.map(renderHit)}
                  </div>
                  {(response.hits.length < (response.estimatedTotalHits || Infinity)) && (
                    <button
                      className="load-more-btn"
                      onClick={handleLoadMore}
                      disabled={loading}
                    >
                      {loading ? '加载中...' : '加载更多'}
                    </button>
                  )}
                </>
              )}
            </section>
          )}
        </main>
      </div>
    </div>
  )
}

export default SearchTester
