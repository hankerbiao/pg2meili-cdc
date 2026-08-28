import { Activity, ArrowRight, Braces, Database, KeyRound, PackageCheck, Search, ShieldCheck, UploadCloud } from 'lucide-react'
import { Link } from 'react-router-dom'
import { CodeBlock } from '../components/CodeBlock'
import { CodeExamples } from '../components/CodeExamples'
import { DocsLayout } from '../components/DocsLayout'
import { SdkDownloadButton } from '../components/SdkDownloadButton'

const variablesCode = `MELIDATA_BASE_URL=https://meilisearch.1oa.com.cn
SEARCH_BASE_URL=https://meilisearch.1oa.com.cn/documents
MELIDATA_API_KEY=<由用户提供的 API Key>
COLLECTION=products`

const curlWrite = `curl --fail-with-body -X POST "$MELIDATA_BASE_URL/api/v1/data/$COLLECTION" \\
  -H "Authorization: Bearer $MELIDATA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"id":"sku-001","name":"Mechanical Keyboard","price":699}'`

const pythonWrite = `import os
from melidata_sdk import MeliDataClient

with MeliDataClient(os.environ["MELIDATA_BASE_URL"], os.environ["MELIDATA_API_KEY"]) as client:
    result = client.upsert_document(os.environ.get("COLLECTION", "products"), {"id": "sku-001", "name": "Mechanical Keyboard", "price": 699})
    print(result)`

const writeExamples = { curl: curlWrite, python: pythonWrite }
const curlSearch = `curl --fail-with-body -X POST "$SEARCH_BASE_URL/api/v1/collections/$COLLECTION/search" \\
  -H "Authorization: Bearer $MELIDATA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"q":"keyboard","limit":10,"showRankingScore":true}'`

const pythonSearch = `import os
from melidata_sdk import MeliDataClient

with MeliDataClient(os.environ["MELIDATA_BASE_URL"], os.environ["MELIDATA_API_KEY"], search_url=os.environ["SEARCH_BASE_URL"]) as client:
    # SDK 自动追加 /api/v1/collections/{collection}/search
    result = client.search("products", query="keyboard", limit=10, show_ranking_score=True)
    print(result.hits)`

const searchExamples = { curl: curlSearch, python: pythonSearch }

const curlBatch = `curl --fail-with-body -X POST "$MELIDATA_BASE_URL/api/v1/data/$COLLECTION/batch" \
  -H "Authorization: Bearer $MELIDATA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"items":[{"id":"sku-001","name":"Keyboard"},{"id":"sku-002","name":"Mouse"}]}'`

const curlCrud = `# 读取单条文档
curl --fail-with-body "$MELIDATA_BASE_URL/api/v1/data/$COLLECTION/sku-001" \
  -H "Authorization: Bearer $MELIDATA_API_KEY"

# 分页列出文档
curl --fail-with-body "$MELIDATA_BASE_URL/api/v1/data/$COLLECTION?limit=20&offset=0" \
  -H "Authorization: Bearer $MELIDATA_API_KEY"

# 删除文档（软删除）
curl --fail-with-body -X DELETE "$MELIDATA_BASE_URL/api/v1/data/$COLLECTION/sku-001" \
  -H "Authorization: Bearer $MELIDATA_API_KEY"`

const pollCode = `import os
import time
from melidata_sdk import MeliDataClient

COLLECTION = os.environ.get("COLLECTION", "products")
with MeliDataClient(os.environ["MELIDATA_BASE_URL"], os.environ["MELIDATA_API_KEY"], search_url=os.environ["SEARCH_BASE_URL"]) as client:
    for attempt in range(6):
        result = client.search(COLLECTION, query="keyboard")
        if any(hit.get("id") == "sku-001" for hit in result.hits):
            break
        time.sleep(2 ** attempt)
    else:
        raise RuntimeError("数据已写入中心服务，但尚未同步到目标区域")`

export function QuickstartPage() {
  return (
    <DocsLayout toc={[{ href: '#instructions', label: 'AI 使用规则' }, { href: '#variables', label: '配置变量' }, { href: '#write', label: '写入数据' }, { href: '#crud', label: '读取与删除' }, { href: '#search', label: '区域搜索' }, { href: '#consistency', label: '同步等待' }, { href: '#errors', label: '错误处理' }]}>
      <article className="doc-article">
        <div className="eyebrow">AI AGENT QUICKSTART</div>
        <h1>用 MeliData 完成写入、读取与区域搜索</h1>
        <p className="lead">本页是给 AI Agent 读取的业务集成契约。AI 可以生成代码；只有在用户明确授权并提供 API Key 后，才可以执行实际验证请求。</p>
        <div className="sdk-download compact-download">
          <div><PackageCheck size={22} /><span><strong>官方 Python SDK</strong><small>封装数据、索引与区域搜索接口</small></span></div>
          <SdkDownloadButton url="/api/v1/sdk/python/download" fallbackName="melidata-sdk-0.1.0.zip">下载 SDK</SdkDownloadButton>
        </div>
        <div className="quick-facts">
          <div><KeyRound /><strong>Bearer 鉴权</strong><span>请求头保持标准格式</span></div>
          <div><UploadCloud /><strong>统一数据 API</strong><span>JSON 文档直接写入</span></div>
          <div><Search /><strong>就近搜索</strong><span>区域节点低延迟查询</span></div>
        </div>

        <section id="instructions"><h2>AI 使用规则</h2><CodeBlock language="instructions" code={'MUST: 使用用户提供的 API Key，通过 Authorization: Bearer <api_key> 发送。\nMUST: 业务写入、读取和删除经过 /api/v1/data/...。\nMUST: 搜索经过区域 Agent，不直接写入或查询 Meilisearch。\nMUST: 用户明确授权后才执行真实请求，否则只生成代码。\nMUST: 本页与 /agent-guide.json 或 /openapi.json 不一致时，以机器可读契约为准。\nDO NOT: 创建、申请或猜测 API Key。\nDO NOT: 将 API Key 写入前端源码、日志、仓库或长期记忆。'} /></section>
        <section id="variables"><h2>配置变量</h2><p><code>MELIDATA_BASE_URL</code> 用于数据 API 和 Agent 发现；<code>SEARCH_BASE_URL</code> 是区域搜索公网 Base URL，默认是天津服务器。</p><CodeBlock language="dotenv" code={variablesCode} /></section>

        <section id="write">
          <span className="step-number">01</span><h2>写入数据</h2>
          <p>使用 <code>data:write</code> 调用 <code>POST /api/v1/data/{'{'}collection{'}'}</code>。文档必须包含非空字符串 <code>id</code>，其他字段可自由扩展。</p>
          <CodeExamples examples={writeExamples} />
          <h3>批量写入</h3><p><code>POST /api/v1/data/{'{'}collection{'}'}/batch</code> 的 <code>items</code> 不能为空且每个 <code>id</code> 必须唯一。</p><CodeBlock language="bash" code={curlBatch} />
          <div className="callout"><Database size={18} /><span>写入成功只代表中心数据源已接受，不代表区域搜索已经可见。</span></div>
        </section>

        <section id="crud"><span className="step-number">02</span><h2>读取与删除</h2><p>读取需要 <code>data:read</code>，删除文档需要 <code>data:write</code>；删除是软删除。</p><CodeBlock language="bash" code={curlCrud} /></section>

        <section id="search">
          <span className="step-number">03</span><h2>区域搜索</h2>
          <p><code>SEARCH_BASE_URL=https://meilisearch.1oa.com.cn/documents</code> 是天津默认入口。<code>/documents</code> 是 Nginx 反向代理前缀，不是完整搜索请求。实际 HTTP 请求为：</p><CodeBlock language="text" code="POST {SEARCH_BASE_URL}/api/v1/collections/{collection}/search" /><p>其他区域只替换 <code>SEARCH_BASE_URL</code> 为在线 Agent 的完整公网 Base URL，路径、请求体、Bearer Key 和 <code>search:read</code> 保持不变。</p>
          <CodeExamples examples={searchExamples} />
        </section>

        <section id="consistency"><span className="step-number">04</span><h2>等待区域同步</h2><p>数据经过 PostgreSQL、Outbox、Debezium、Kafka、区域 Agent 和 Meilisearch 异步传播。刚写入后搜索为空不代表写入失败。</p><CodeBlock language="python" code={'import time\n\n' + pollCode} /></section>
        <section id="errors"><h2>错误处理</h2><table className="docs-table"><thead><tr><th>状态</th><th>处理</th></tr></thead><tbody><tr><td><code>401</code>/<code>403</code></td><td>停止，检查 Key 或 scope</td></tr><tr><td><code>404</code>/<code>422</code></td><td>修正集合、文档 ID 或请求体</td></tr><tr><td><code>409</code></td><td>停止写入，检查应用是否正在删除（<code>APP_DELETING</code>）</td></tr><tr><td><code>413</code></td><td>缩小请求体或批量大小（<code>REQUEST_BODY_TOO_LARGE</code>）</td></tr><tr><td><code>429</code></td><td>按 Retry-After 或退避重试</td></tr><tr><td><code>5xx</code>/<code>网络错误</code></td><td>有限次数退避重试并保留 request ID</td></tr></tbody></table></section>

        <section id="guides" className="next-section">
          <h2>完善集成</h2>
          <p>快速开始将认证、SDK 和 API 契约汇集在同一组导航中；按你的接入方式继续深入。</p>
          <div className="next-links integration-links">
            <Link to="/docs/authentication"><ShieldCheck size={18} /><span><strong>认证与权限</strong><small>请求头、scope 与安全实践</small></span><ArrowRight size={18} /></Link>
            <Link to="/docs/python-sdk"><PackageCheck size={18} /><span><strong>Python SDK</strong><small>安装、客户端与常用接口</small></span><ArrowRight size={18} /></Link>
            <Link to="/docs/api-reference"><Braces size={18} /><span><strong>API Reference</strong><small>浏览端点与请求契约</small></span><ArrowRight size={18} /></Link>
            <Link to="/docs/runtime-architecture"><Activity size={18} /><span><strong>区域搜索与同步</strong><small>理解 Agent、CDC 与搜索状态</small></span><ArrowRight size={18} /></Link>
          </div>
        </section>
      </article>
    </DocsLayout>
  )
}
