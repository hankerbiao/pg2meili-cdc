import { Activity, ArrowRight, Braces, CheckCircle2, KeyRound, PackageCheck, Search, ShieldCheck, UploadCloud } from 'lucide-react'
import { Link } from 'react-router-dom'
import { CodeBlock } from '../components/CodeBlock'
import { CodeExamples } from '../components/CodeExamples'
import { DocsLayout } from '../components/DocsLayout'
import { SdkDownloadButton } from '../components/SdkDownloadButton'

const curlWrite = `curl -X POST https://meilisearch.1oa.com.cn/api/v1/data/products \\
  -H "Authorization: Bearer $MELIDATA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"id":"sku-001","name":"Mechanical Keyboard","price":699}'`

const curlSearch = `curl -X POST https://meilisearch.1oa.com.cn/documents \\
  -H "Authorization: Bearer $MELIDATA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"q":"keyboard","limit":10,"showRankingScore":true}'`

const writeExamples = {
  curl: curlWrite,
  python: `import os
from melidata_sdk import MeliDataClient

client = MeliDataClient("https://meilisearch.1oa.com.cn", os.environ["MELIDATA_API_KEY"])
client.upsert_document("products", {"id": "sku-001", "name": "Mechanical Keyboard", "price": 699})`,
  javascript: `const response = await fetch(
  "https://meilisearch.1oa.com.cn/api/v1/data/products",
  {
    method: "POST",
    headers: {
      Authorization: \`Bearer \${process.env.MELIDATA_API_KEY}\`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ id: "sku-001", name: "Mechanical Keyboard", price: 699 }),
  },
)
if (!response.ok) throw new Error(await response.text())`,
}

const searchExamples = {
  curl: curlSearch,
  python: `import os
from melidata_sdk import MeliDataClient

BASE_URL = "https://meilisearch.1oa.com.cn"
SEARCH_URL = "https://meilisearch.1oa.com.cn/documents"

client = MeliDataClient(BASE_URL, os.environ["MELIDATA_API_KEY"], search_url=SEARCH_URL)
result = client.search("products", query="keyboard", limit=10, show_ranking_score=True)`,
  javascript: `const response = await fetch(
  "https://meilisearch.1oa.com.cn/documents",
  {
    method: "POST",
    headers: {
      Authorization: \`Bearer \${process.env.MELIDATA_API_KEY}\`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ q: "keyboard", limit: 10, showRankingScore: true }),
  },
)
if (!response.ok) throw new Error(await response.text())`,
}

export function QuickstartPage() {
  return (
    <DocsLayout toc={[{ href: '#create-key', label: '获取 API Key' }, { href: '#write', label: '写入数据' }, { href: '#search', label: '区域搜索' }, { href: '#guides', label: '集成文档' }]}>
      <article className="doc-article">
        <div className="eyebrow">QUICKSTART</div>
        <h1>用一把 Key，连接数据与搜索</h1>
        <p className="lead">MeliData 使用开放平台 API Key 统一保护数据写入、读取与区域搜索。完整密钥只在创建或轮换时显示一次。</p>
        <div className="sdk-download compact-download">
          <div><PackageCheck size={22} /><span><strong>官方 Python SDK</strong><small>封装数据、索引与区域搜索接口</small></span></div>
          <SdkDownloadButton url="/api/v1/sdk/python/download" fallbackName="melidata-sdk-0.1.0.zip">下载 SDK</SdkDownloadButton>
        </div>
        <div className="quick-facts">
          <div><KeyRound /><strong>Bearer 鉴权</strong><span>请求头保持标准格式</span></div>
          <div><UploadCloud /><strong>统一数据 API</strong><span>JSON 文档直接写入</span></div>
          <div><Search /><strong>就近搜索</strong><span>区域节点低延迟查询</span></div>
        </div>

        <section id="create-key">
          <span className="step-number">01</span><h2>获取 API Key</h2>
          <p>管理员创建应用时默认获得前端搜索只读和后端完整访问两把独立 Key，也可以选择仅创建后端完整访问 Key。后端 Key 包含数据读写与搜索权限；前端 Key 仅可搜索。之后仍可为不同调用方创建更多 Key。密钥格式固定为：</p>
          <CodeBlock language="text" code="ud_live_ak_0123456789abcdef.<256-bit-random-secret>" />
          <div className="callout"><CheckCircle2 size={18} /><span>将密钥保存到服务端密钥管理系统，并通过 <code>MELIDATA_API_KEY</code> 环境变量注入。</span></div>
        </section>

        <section id="write">
          <span className="step-number">02</span><h2>写入第一条数据</h2>
          <p>使用具有 <code>data:write</code> scope 的 Key 写入任意 JSON 文档。<code>collection</code> 会与应用身份共同形成隔离边界。</p>
          <CodeExamples examples={writeExamples} />
        </section>

        <section id="search">
          <span className="step-number">03</span><h2>从区域节点搜索</h2>
          <p>使用 <code>search:read</code> scope 调用区域搜索 API。搜索节点会验证同一把 API Key，并仅访问该应用的索引。</p>
          <CodeExamples examples={searchExamples} />
        </section>

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
