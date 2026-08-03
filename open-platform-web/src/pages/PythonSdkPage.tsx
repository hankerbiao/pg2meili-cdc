import { AlertCircle, PackageCheck } from 'lucide-react'
import { CodeBlock } from '../components/CodeBlock'
import { DocsLayout } from '../components/DocsLayout'
import { SdkDownloadButton } from '../components/SdkDownloadButton'

const SDK_DOWNLOAD_URL = '/api/v1/sdk/python/download'

const installCode = `# 下载后直接安装源码包
pip install ./unidata-sdk-0.1.0.zip`

const clientCode = `import os
from unidata_sdk import UniDataClient

client = UniDataClient(
    "https://unidata.example.com",
    os.environ["UNIDATA_API_KEY"],
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
from unidata_sdk import AsyncUniDataClient

async with AsyncUniDataClient(
    "https://unidata.example.com",
    os.environ["UNIDATA_API_KEY"],
    region="shanghai",
) as client:
    await client.upsert_documents("products", documents)
    result = await client.search("products", query="monitor")
    raw = await client.request("GET", "/api/v1/indexes")`

const errorCode = `from unidata_sdk import RateLimitError, UniDataError

try:
    result = client.search("products", query="keyboard")
except RateLimitError as error:
    print(error.retry_after, error.request_id)
except UniDataError as error:
    print(error.code, error.status_code, error.request_id)`

export function PythonSdkPage() {
  return (
    <DocsLayout toc={[
      { href: '#install', label: '下载与安装' },
      { href: '#client', label: '初始化客户端' },
      { href: '#methods', label: '常用接口' },
      { href: '#generic', label: '通用请求' },
      { href: '#async', label: '异步客户端' },
      { href: '#errors', label: '错误与重试' },
    ]}>
      <article className="doc-article">
        <div className="eyebrow">PYTHON SDK</div>
        <h1>用 Python 接入 UniData</h1>
        <p className="lead">官方 SDK 封装数据、索引、Agent 发现与区域搜索，并保留通用请求接口以调用后续新增的控制面 API。</p>

        <div className="sdk-download">
          <div><PackageCheck size={22} /><span><strong>unidata-sdk 0.1.0</strong><small>Python 3.10+ · 源码 ZIP · httpx</small></span></div>
          <SdkDownloadButton url={SDK_DOWNLOAD_URL} fallbackName="unidata-sdk-0.1.0.zip">下载 Python SDK</SdkDownloadButton>
        </div>

        <section id="install">
          <span className="step-number">01</span><h2>下载与安装</h2>
          <p>点击上方按钮获取可安装源码包，在应用的虚拟环境中执行：</p>
          <CodeBlock code={installCode} />
        </section>

        <section id="client">
          <span className="step-number">02</span><h2>初始化客户端</h2>
          <p><code>base_url</code> 指向 UniData 后端，API Key 建议由 <code>UNIDATA_API_KEY</code> 环境变量注入。设置 <code>region</code> 后，搜索会自动发现并选择同区域在线 Agent。</p>
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
          <p><code>AsyncUniDataClient</code> 提供相同业务接口，所有网络方法使用 <code>await</code>，并支持异步上下文管理器自动关闭连接。</p>
          <CodeBlock language="python" code={asyncCode} />
        </section>

        <section id="errors">
          <span className="step-number">06</span><h2>错误与重试</h2>
          <p>所有 SDK 异常继承自 <code>UniDataError</code>。默认对可重试请求额外尝试两次，并遵循服务端 <code>Retry-After</code>；认证、权限、校验和未找到错误不会重试。</p>
          <CodeBlock language="python" code={errorCode} />
        </section>
      </article>
    </DocsLayout>
  )
}
