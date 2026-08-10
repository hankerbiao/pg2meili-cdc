import { AlertCircle, PackageCheck } from 'lucide-react'
import { CodeBlock } from '../components/CodeBlock'
import { DocsLayout } from '../components/DocsLayout'
import { SdkDownloadButton } from '../components/SdkDownloadButton'

const SDK_DOWNLOAD_URL = '/api/v1/sdk/python/download'

const installCode = `# 下载后直接安装源码包
pip install ./melidata-sdk-0.1.0.zip`

const clientCode = `import os
from melidata_sdk import MeliDataClient

client = MeliDataClient(
    "https://meilisearch.1oa.com.cn",
    os.environ["MELIDATA_API_KEY"],
    region="shanghai",
)

client.upsert_document(
    "products",
    {"id": "sku-001", "name": "Mechanical Keyboard", "price": 699},
)

document = client.get_document("products", "sku-001")
result = client.search("products", query="keyboard", limit=10)

for hit in result.hits:
    print(hit["id"], hit.get("name"))

client.close()`

const batchCode = `result = client.upsert_documents(
    "products",
    [
        {"id": "sku-001", "name": "Keyboard"},
        {"id": "sku-002", "name": "Mouse"},
    ],
)

documents = client.list_documents("products", limit=20, offset=0)
client.update_index_settings(
    "products",
    filterable_attributes=["category", "in_stock"],
    sortable_attributes=["price", "created_at"],
)
result = client.search(
    "products",
    query="keyboard",
    filter="in_stock = true",
    attributes_to_highlight=["name"],
    raw_parameters={"facets": ["category"]},
)`

const genericCode = `data = client.request(
    "POST",
    "/api/v1/data/products",
    params={"source": "catalog-import"},
    json={"id": "sku-003", "name": "Monitor"},
    headers={"X-Request-ID": "catalog-20260730"},
)

# 返回值已经解包 ApiResponse.data
print(data)`

const asyncCode = `import os
from melidata_sdk import AsyncMeliDataClient

async with AsyncMeliDataClient(
    "https://meilisearch.1oa.com.cn",
    os.environ["MELIDATA_API_KEY"],
    region="shanghai",
) as client:
    await client.upsert_documents("products", documents)
    result = await client.search("products", query="monitor")
    raw = await client.request("GET", "/api/v1/indexes")`

const errorCode = `from melidata_sdk import RateLimitError, MeliDataError

try:
    result = client.search("products", query="keyboard")
except RateLimitError as error:
    print(error.retry_after, error.request_id)
except MeliDataError as error:
    print(error.code, error.status_code, error.request_id)`

const keysCode = `import os
from melidata_sdk import MeliDataClient

# 后端服务：需要读写数据
data_client = MeliDataClient(
    "https://meilisearch.1oa.com.cn",
    os.environ["MELIDATA_DATA_KEY"],          # scope: data:read, data:write
)

# 前端 / 只读场景：只需搜索能力（绝不授予写权限）
search_client = MeliDataClient(
    "https://meilisearch.1oa.com.cn",
    os.environ["MELIDATA_SEARCH_KEY"],        # scope: search:read
    search_url="https://meilisearch.1oa.com.cn", # 固定走搜索 Agent
)

# 不同 Key 调用不同 scope 的方法
data_client.upsert_document("products", {"id": "sku-001", "name": "Keyboard"})
result = search_client.search("products", query="keyboard")`

const searchDetailCode = `# filter 表达式：字段 + 比较 + AND / OR（需先声明 filterable_attributes）
result = search_client.search(
    "products",
    query="keyboard",
    filter='category = "electronics" AND price >= 100',
    attributes_to_highlight=["name", "description"],
)

# raw_parameters 透传 Meilisearch 原生参数（后端为透明代理）
result = search_client.search(
    "products",
    query="keyboard",
    raw_parameters={
        "sort": ["price:asc"],
        "facets": ["category", "brand"],
        "attributesToSearchOn": ["name", "description"],
    },
)

# 读取结果：hits / 总数 / 耗时 / 请求追踪 / 分面计数
print(result.hits)                  # 命中文档列表
print(result.estimated_total_hits)  # 近似总数
print(result.processing_time_ms)    # 服务端耗时 (ms)
print(result.meta.request_id)       # 请求追踪 ID
print(result.raw.get("facetDistribution"))  # 分面计数（raw 兜底）`

const e2eCode = `import os, time, uuid
from melidata_sdk import MeliDataClient

data_client = MeliDataClient("https://meilisearch.1oa.com.cn", os.environ["MELIDATA_DATA_KEY"])
search_client = MeliDataClient(
    "https://meilisearch.1oa.com.cn",
    os.environ["MELIDATA_SEARCH_KEY"],
    search_url="https://meilisearch.1oa.com.cn",
)

doc_id = f"doc-{uuid.uuid4().hex[:8]}"
data_client.upsert_document("articles", {
    "id": doc_id,
    "title": "Power management guide",
    "status": "published",
})
assert data_client.get_document("articles", doc_id)["title"] == "Power management guide"

# 搜索经 CDC 异步同步：写入后稍等再查，带重试
for attempt in range(10):
    r = search_client.search(
        "articles",
        query="Power",
        filter='status = "published"',
        attributes_to_highlight=["title"],
    )
    if any(h["id"] == doc_id for h in r.hits):
        break
    time.sleep(2)
print("matched:", r.hits)`

export function PythonSdkPage() {
  return (
    <DocsLayout toc={[
      { href: '#install', label: '下载与安装' },
      { href: '#client', label: '初始化客户端' },
      { href: '#methods', label: '常用接口' },
      { href: '#generic', label: '通用请求' },
      { href: '#async', label: '异步客户端' },
      { href: '#errors', label: '错误与重试' },
      { href: '#keys', label: 'API Key 与权限' },
      { href: '#search', label: '搜索能力详解' },
      { href: '#e2e', label: '端到端示例' },
    ]}>
      <article className="doc-article">
        <div className="eyebrow">PYTHON SDK</div>
        <h1>用 Python 接入 MeliData</h1>
        <p className="lead">官方 SDK 封装数据、索引、Agent 发现与区域搜索，并保留通用请求接口以调用后续新增的控制面 API。</p>

        <div className="sdk-download">
          <div><PackageCheck size={22} /><span><strong>melidata-sdk 0.1.0</strong><small>Python 3.10+ · 源码 ZIP · httpx</small></span></div>
          <SdkDownloadButton url={SDK_DOWNLOAD_URL} fallbackName="melidata-sdk-0.1.0.zip">下载 Python SDK</SdkDownloadButton>
        </div>

        <section id="install">
          <span className="step-number">01</span><h2>下载与安装</h2>
          <p>点击上方按钮获取可安装源码包，在应用的虚拟环境中执行：</p>
          <CodeBlock code={installCode} />
        </section>

        <section id="client">
          <span className="step-number">02</span><h2>初始化客户端</h2>
          <p><code>base_url</code> 指向 MeliData 后端，API Key 建议由 <code>MELIDATA_API_KEY</code> 环境变量注入。设置 <code>region</code> 后，搜索会自动发现并选择同区域在线 Agent。</p>
          <CodeBlock language="python" code={clientCode} />
        </section>

        <section id="methods">
          <span className="step-number">03</span><h2>常用独立接口</h2>
          <p>同步与异步客户端提供同一组业务方法，返回值保留文档和搜索结果中的自定义字段。</p>
          <table className="docs-table sdk-methods">
            <thead><tr><th>功能</th><th>SDK 方法</th><th>scope</th></tr></thead>
            <tbody>
              <tr><td>写入与批量写入</td><td><code>upsert_document()</code><br /><code>upsert_documents()</code></td><td><code>data:write</code></td></tr>
              <tr><td>读取与分页</td><td><code>get_document()</code><br /><code>list_documents()</code></td><td><code>data:read</code></td></tr>
              <tr><td>删除文档</td><td><code>delete_document()</code></td><td><code>data:write</code></td></tr>
              <tr><td>索引管理</td><td><code>list_indexes()</code><br /><code>update_index_settings()</code><br /><code>delete_index()</code></td><td><code>data:read</code><br /><code>data:write</code></td></tr>
              <tr><td>Agent 与搜索</td><td><code>list_agents()</code><br /><code>search()</code></td><td><code>search:read</code></td></tr>
            </tbody>
          </table>
          <CodeBlock language="python" code={batchCode} />
        </section>

        <section id="generic">
          <span className="step-number">04</span><h2>通用 request 接口</h2>
          <p>尚未封装为专用方法的控制面端点可通过 <code>request()</code> 调用。它复用 Bearer 鉴权、超时、重试、统一错误映射，并直接返回响应中的 <code>data</code>。</p>
          <CodeBlock language="python" code={genericCode} />
          <div className="callout"><AlertCircle size={18} /><span><code>path</code> 必须以一个 <code>/</code> 开头且不能是完整 URL；<code>Authorization</code> 和 <code>User-Agent</code> 由 SDK 管理，不允许覆盖。</span></div>
        </section>

        <section id="async">
          <span className="step-number">05</span><h2>异步客户端</h2>
          <p><code>AsyncMeliDataClient</code> 提供相同业务接口，所有网络方法使用 <code>await</code>，并支持异步上下文管理器自动关闭连接。</p>
          <CodeBlock language="python" code={asyncCode} />
        </section>

        <section id="errors">
          <span className="step-number">06</span><h2>错误与重试</h2>
          <p>所有 SDK 异常继承自 <code>MeliDataError</code>。默认对可重试请求额外尝试两次，并遵循服务端 <code>Retry-After</code>；认证、权限、校验和未找到错误不会重试。</p>
          <CodeBlock language="python" code={errorCode} />
        </section>

        <section id="keys">
          <span className="step-number">07</span><h2>API Key 与权限模型</h2>
          <p>每个应用可创建多个 API Key，按 <code>scope</code> 精确授权。SDK 方法会在请求时校验所需 scope，缺失权限会返回 <code>PermissionDeniedError</code>。遵循最小授权原则：只给业务必需的 scope。</p>
          <table className="docs-table sdk-methods">
            <thead><tr><th>scope</th><th>允许的操作</th><th>典型使用方</th></tr></thead>
            <tbody>
              <tr><td><code>data:read</code></td><td>读取文档、列举索引、列举 Agent</td><td>后台任务、只读报表</td></tr>
              <tr><td><code>data:write</code></td><td>写入 / 批量写入 / 删除文档、更新索引设置</td><td>数据管道、管理后台</td></tr>
              <tr><td><code>search:read</code></td><td>发起搜索请求（仅搜索 Agent）</td><td>前端页面、C 端查询</td></tr>
            </tbody>
          </table>
          <p>前端不应持有 <code>data:write</code>。推荐为「数据写入」与「前端搜索」分别创建 Key，前端只注入 <code>search:read</code> 的 Key，即使泄露也只暴露查询能力。</p>
          <CodeBlock language="python" code={keysCode} />
          <div className="callout"><AlertCircle size={18} /><span>在开放平台「应用与密钥」中创建 Key 时可勾选 scope；Key 的明文仅在创建时展示一次，遗失需吊销后重新生成。</span></div>
        </section>

        <section id="search">
          <span className="step-number">08</span><h2>搜索能力详解</h2>
          <p><code>search()</code> 通过搜索 Agent 执行，支持两种模式：传入 <code>search_url</code> 固定打到指定 Agent；不传则按 <code>region</code> 从 <code>list_agents()</code> 自动发现并故障转移。后端对请求体是 Meilisearch 透明代理，因此除以下原生参数外，任何 Meilisearch 搜索参数都可通过 <code>raw_parameters</code> 透传。</p>
          <table className="docs-table sdk-methods">
            <thead><tr><th>功能</th><th>SDK 参数</th></tr></thead>
            <tbody>
              <tr><td>关键词</td><td><code>query</code></td></tr>
              <tr><td>分页</td><td><code>offset</code> / <code>limit</code></td></tr>
              <tr><td>字段过滤</td><td><code>filter</code>（Meilisearch filter 表达式，需先声明 <code>filterable_attributes</code>）</td></tr>
              <tr><td>返回字段</td><td><code>attributes_to_retrieve</code></td></tr>
              <tr><td>高亮 / 裁剪</td><td><code>attributes_to_highlight</code> / <code>attributes_to_crop</code> + <code>crop_length</code></td></tr>
              <tr><td>相关度评分</td><td><code>show_ranking_score</code></td></tr>
              <tr><td>排序 / 分面 / 搜索字段 / 向量</td><td><code>raw_parameters={'{'}sort, facets, attributesToSearchOn, vector, ...{'}'}</code></td></tr>
            </tbody>
          </table>
          <CodeBlock language="python" code={searchDetailCode} />
          <p><code>SearchResult</code> 包含 <code>hits</code>（命中文档列表）、<code>estimated_total_hits</code>（近似总数）、<code>processing_time_ms</code>（服务端耗时）、<code>meta.request_id</code>（请求追踪）；分面计数等未 typed 暴露的字段可从 <code>raw</code> 取。当前搜索为单索引语义，跨索引联邦检索需后端规划 <code>multi_search</code>。</p>
        </section>

        <section id="e2e">
          <span className="step-number">09</span><h2>端到端快速示例</h2>
          <p>完整链路：用 data Key 写入文档，<code>get_document()</code> 读回校验，再用 search Key 发起搜索。写入经 CDC 异步同步至搜索索引，故搜索侧需等待几秒——SDK 默认不内置轮询，应用层可加重试。</p>
          <CodeBlock language="python" code={e2eCode} />
          <div className="callout"><AlertCircle size={18} /><span>搜索命中依赖 CDC 同步延迟（通常数秒内）。在测试或强一致场景，可在写入后轮询搜索直到命中，再进入断言。生产链路应接受最终一致。</span></div>
        </section>
      </article>
    </DocsLayout>
  )
}
