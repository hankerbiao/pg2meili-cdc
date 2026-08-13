import { Activity, AlertCircle, ArrowRight, CheckCircle2, Database, KeyRound, Search, Server, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { CodeBlock } from '../components/CodeBlock'
import { DocsLayout } from '../components/DocsLayout'

const discoverAgentCode = `curl -sS "https://meilisearch.1oa.com.cn/api/v1/agents/online?region=shanghai" \
  -H "Authorization: Bearer $MELIDATA_SEARCH_KEY"`

const searchCode = `curl -X POST "https://meilisearch.1oa.com.cn/documents/api/v1/collections/products/search" \
  -H "Authorization: Bearer $MELIDATA_SEARCH_KEY" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: storefront-search-001" \
  -d '{
    "q": "keyboard",
    "limit": 10,
    "filter": "in_stock = true",
    "attributesToHighlight": ["name"]
  }'`

const responseCode = `{
  "data": {
    "hits": [{ "id": "sku-001", "name": "Mechanical Keyboard" }],
    "estimatedTotalHits": 1,
    "processingTimeMs": 3
  },
  "meta": {
    "request_id": "storefront-search-001",
    "region": "shanghai",
    "duration_ms": 8
  },
  "error": null
}`

const pollCode = `for attempt in range(10):
    result = search_client.search("products", query="keyboard")
    if any(hit["id"] == document_id for hit in result.hits):
        break
    time.sleep(2)
else:
    raise TimeoutError("Document has not reached the regional search index")`

const runtimeSteps = [
  { icon: KeyRound, title: '发现区域节点', detail: '调用 GET /api/v1/agents/online，可带 region 参数。仅返回健康且未超出心跳 TTL 的节点。' },
  { icon: Search, title: '提交搜索', detail: '向 POST https://meilisearch.1oa.com.cn/documents/api/v1/collections/{collection}/search 发起请求，并携带同一把 API Key。' },
  { icon: ShieldCheck, title: '本地鉴权与隔离', detail: '区域 Agent 从本地 Key 注册表校验 search:read，按 app_id + collection 派生专属索引 UID。' },
  { icon: Server, title: '代理至 Meilisearch', detail: 'Agent 将搜索参数透传到目标索引；Meilisearch 服务凭证始终只保留在 Agent 侧。' },
]

export function RuntimeArchitecturePage() {
  return (
    <DocsLayout toc={[
      { href: '#topology', label: '运行拓扑' },
      { href: '#search-flow', label: '搜索如何执行' },
      { href: '#sync-state', label: '同步与可见性' },
      { href: '#reliability', label: '可靠性与隔离' },
      { href: '#troubleshooting', label: '排障参考' },
    ]}>
      <article className="doc-article runtime-article">
        <div className="eyebrow">RUNTIME ARCHITECTURE</div>
        <h1>区域搜索与同步运行机制</h1>
        <p className="lead">本页说明 MeliData 的 Go 区域 Agent 如何处理搜索、维护 Key 状态并将写入数据同步到 Meilisearch。它用于理解运行状态与排查搜索结果，不是管理接口。</p>

        <div className="callout">
          <Activity size={18} />
          <span>数据写入成功表示已由主数据服务接受；搜索命中取决于 CDC 同步到目标区域索引，属于最终一致性链路。</span>
        </div>

        <section id="topology">
          <h2>运行拓扑</h2>
          <p>业务应用只与 MeliData API 和已发现的区域 Agent 交互。Go Agent 位于区域侧，负责搜索代理和索引同步，不向调用方公开 Meilisearch 的服务凭证。</p>
          <ol className="runtime-topology">
            <li><span>01</span><div><strong>业务应用</strong><small>写入文档、发现区域节点并发起搜索。</small></div></li>
            <li><span>02</span><div><strong>MeliData API</strong><small>保存文档与索引配置，维护应用及 API Key 生命周期。</small></div></li>
            <li><span>03</span><div><strong>PostgreSQL / Outbox / Debezium / Kafka</strong><small>将文档、索引命令和 Key 状态变更异步传递到各区域。</small></div></li>
            <li><span>04</span><div><strong>Go 区域 Agent</strong><small>消费事件、维护本地 Key 注册表、同步索引并代理搜索。</small></div></li>
            <li><span>05</span><div><strong>Meilisearch</strong><small>执行单个应用专属索引上的检索。</small></div></li>
          </ol>
        </section>

        <section id="search-flow">
          <h2>搜索如何执行</h2>
          <p>区域搜索 Base URL 为 <code>https://meilisearch.1oa.com.cn/documents</code>，实际请求为 <code>POST https://meilisearch.1oa.com.cn/documents/api/v1/collections/{'{'}collection{'}'}/search</code>。调用方使用具有 <code>search:read</code> 的同一把 Key 发起请求。</p>
          <div className="callout"><Search size={18} /><span>默认地址 <code>https://meilisearch.1oa.com.cn/documents</code> 是天津服务器的搜索入口。若要使用其他区域的 Agent，请先获取在线 Agent 的地址，再将请求 URL 替换为该地址；鉴权、请求参数和调用方式保持不变，仅 URL 不同。</span></div>
          <div className="runtime-steps">
            {runtimeSteps.map(({ icon: Icon, title, detail }) => <div key={title}><Icon size={20} /><strong>{title}</strong><span>{detail}</span></div>)}
          </div>
          <h3>1. 发现在线 Agent</h3>
          <CodeBlock language="bash" code={discoverAgentCode} />
          <h3>2. 向区域 Agent 搜索</h3>
          <CodeBlock language="bash" code={searchCode} />
          <p>请求体使用 Meilisearch 搜索参数。Agent 限制请求体大小并校验集合名称；上游请求或网络失败会被映射为稳定的 API 错误响应。搜索响应不会被共享缓存。</p>
          <h3>3. 读取统一响应元数据</h3>
          <CodeBlock language="json" code={responseCode} />
          <p><code>data</code> 保留 Meilisearch 搜索结果，<code>meta.request_id</code> 用于跨服务追踪，<code>meta.region</code> 表示实际处理区域，<code>meta.duration_ms</code> 是 Agent 端总耗时。</p>
        </section>

        <section id="sync-state">
          <h2>同步与搜索可见性</h2>
          <p>文档写入与索引更新不会在调用线程中直接请求 Meilisearch。中心服务先提交主数据与 Outbox，Debezium 将变更送入 Kafka；各区域 Go Agent 消费事件后执行文档写入、删除或索引配置更新，并等待 Meilisearch 任务完成。</p>
          <div className="sync-state-grid">
            <div><Database size={20} /><strong>文档事件</strong><span>按应用与 collection 定位索引，移除租户及内部字段后写入或删除文档。</span></div>
            <div><Activity size={20} /><strong>索引命令</strong><span>过滤、排序等设置由命令事件异步下发到区域索引。</span></div>
            <div><KeyRound size={20} /><strong>Key 生命周期</strong><span>创建、吊销与权限变更同步到区域本地注册表，搜索不需每次回查中心服务。</span></div>
          </div>
          <div className="callout warning">
            <AlertCircle size={18} />
            <span>刚写入的数据可能暂未出现在搜索结果中。测试、导入校验或强依赖命中的业务应等待 CDC 同步完成并带退避重试。</span>
          </div>
          <CodeBlock language="python" code={pollCode} />
        </section>

        <section id="reliability">
          <h2>可靠性与租户隔离</h2>
          <table className="docs-table">
            <thead><tr><th>机制</th><th>运行方式</th><th>对调用方的意义</th></tr></thead>
            <tbody>
              <tr><td>索引隔离</td><td>Agent 以 <code>app_id + collection</code> 派生索引 UID。</td><td>同名 collection 不会跨应用读取或检索。</td></tr>
              <tr><td>权限一致性</td><td>Agent 仅接受本地注册表中的有效 Key，注册表不可用时拒绝请求。</td><td>权限检查不会在区域故障时降级为放行。</td></tr>
              <tr><td>事件顺序保护</td><td>使用应用 epoch 和文档 revision 拒绝过期事件。</td><td>延迟或乱序消息不会覆盖较新的数据状态。</td></tr>
              <tr><td>失败处理</td><td>暂时性错误重试且不提交 Kafka offset；无效事件进入 DLQ。</td><td>可恢复问题不会悄然丢失，异常事件可单独处置。</td></tr>
              <tr><td>节点健康</td><td>中心服务通过 Agent <code>GET /health</code> 与心跳 TTL 判断在线状态。</td><td>节点发现接口只返回可用区域节点。</td></tr>
            </tbody>
          </table>
        </section>

        <section id="troubleshooting">
          <h2>排障参考</h2>
          <div className="troubleshooting-list">
            <div><strong>没有可用搜索节点</strong><span>检查 <code>GET /api/v1/agents/online</code> 的 region 条件和节点健康状态；可在控制台的“代理节点”查看最近心跳。</span></div>
            <div><strong>返回权限错误</strong><span>确认 API Key 仍有效，且包含 <code>search:read</code>；数据读写权限不会自动授予搜索权限。</span></div>
            <div><strong>写入后未搜索到</strong><span>先通过数据 API 读取确认写入成功，再等待 CDC/Kafka 和 Meilisearch 任务完成，使用带退避的轮询验证。</span></div>
            <div><strong>区域搜索失败</strong><span>记录 <code>meta.request_id</code>、<code>meta.region</code> 和错误码；它们可将问题定位到具体 Agent 与上游请求。</span></div>
          </div>
          <div className="next-links integration-links">
            <Link to="/docs/api-reference"><Search size={18} /><span><strong>API Reference</strong><small>区域搜索请求与数据接口契约</small></span><ArrowRight size={18} /></Link>
            <Link to="/docs/python-sdk"><CheckCircle2 size={18} /><span><strong>Python SDK</strong><small>Agent 发现、搜索与应用层重试</small></span><ArrowRight size={18} /></Link>
          </div>
        </section>
      </article>
    </DocsLayout>
  )
}
