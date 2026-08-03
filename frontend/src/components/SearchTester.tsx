import { useEffect, useState } from 'react'
import { search, PRESET_SCENARIOS } from '../api'
import type { SearchHit, SearchRequest, SearchResponse } from '../api'
import { buildSearchCurl, parseSearchCurl, renderHighlight } from '../searchUtils'

const DEFAULT_API_KEY = import.meta.env.VITE_DEFAULT_API_KEY ?? ''

const SearchTester = () => {
  const [baseUrl, setBaseUrl] = useState('http://127.0.0.1:8091')
  const [apiKey, setApiKey] = useState(DEFAULT_API_KEY)
  const [selectedScenario, setSelectedScenario] = useState(0)
  const [request, setRequest] = useState<SearchRequest>(PRESET_SCENARIOS[0].request)
  const [curlText, setCurlText] = useState('')
  const [response, setResponse] = useState<SearchResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const collection = request.collection ?? ''

  useEffect(() => {
    setCurlText(buildSearchCurl(baseUrl, apiKey, request))
  }, [baseUrl, apiKey, request])

  const executeSearch = async (request: SearchRequest, overrideBaseUrl?: string, overrideApiKey?: string) => {
    setLoading(true)
    setError(null)

    try {
      const result = await search(overrideBaseUrl || baseUrl, overrideApiKey || apiKey, request)
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
    const req = PRESET_SCENARIOS[index].request
    setRequest(req)
    executeSearch(req)
  }

  const updateCollection = (value: string) => {
    const collection = value.trim()
    setRequest((current) => {
      const next = { ...current }
      if (collection) next.collection = collection
      else delete next.collection
      return next
    })
  }

  const handleManualSearch = () => {
    try {
      const parsed = parseSearchCurl(curlText)
      if (parsed.baseUrl) setBaseUrl(parsed.baseUrl)
      if (parsed.apiKey) setApiKey(parsed.apiKey)

      setRequest(parsed.request)
      executeSearch(parsed.request, parsed.baseUrl || baseUrl, parsed.apiKey || apiKey)
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
      const nextRequest: SearchRequest = {
        ...request,
        offset: currentOffset + currentLimit,
      }
      const result = await search(baseUrl, apiKey, nextRequest)
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
          {renderHighlight(name)}
        </h3>
        <p className="hit-summary">
          {renderHighlight(summary)}
        </p>
        <div className="hit-tags">
          {(hit.tags || []).map((tag, i) => (
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

        <main className="content">
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
                <label>API Key</label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                />
              </div>
            </div>
            <div className="config-row">
              <div className="config-field">
                <label>Collection</label>
                <input
                  type="text"
                  value={collection}
                  onChange={(event) => updateCollection(event.target.value)}
                />
              </div>
            </div>
          </section>

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
                    {'\n'}  Authorization: Bearer [api_key]
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
              disabled={loading || !apiKey}
            >
              {loading ? '搜索中...' : '执行搜索'}
            </button>
          </section>

          {error && (
            <section className="error-section">
              <pre className="error-content">{error}</pre>
            </section>
          )}

          {response && (
            <section className="result-section">
              <div className="result-header">
                <h2>搜索结果</h2>
                <div className="result-stats">
                  <span>总数: {response.estimatedTotalHits ?? response.hits.length}</span>
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
                  {response.hits.length < (response.estimatedTotalHits ?? Infinity) && (
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
