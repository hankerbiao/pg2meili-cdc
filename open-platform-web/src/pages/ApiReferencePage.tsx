import { ChevronRight, LoaderCircle } from 'lucide-react'
import { useMemo, useState } from 'react'
import { CodeBlock } from '../components/CodeBlock'
import { DocsLayout } from '../components/DocsLayout'
import { regionalSearchOperation, type PublicOperation } from '../api/openapi'
import { useOpenApiOperations } from '../api/useOpenApi'

const methodClass = (method: string) => `method method-${method.toLowerCase()}`

export function ApiReferencePage() {
  const query = useOpenApiOperations()
  const operations = useMemo(() => [...(query.data ?? []), regionalSearchOperation], [query.data])
  const [selectedId, setSelectedId] = useState('regional-search')
  const selected = operations.find((item) => item.id === selectedId) ?? operations[0]

  return (
    <DocsLayout toc={[{ href: '#endpoints', label: '端点列表' }, { href: '#operation', label: '请求详情' }]}>
      <article className="doc-article reference-article">
        <div className="eyebrow">API REFERENCE</div>
        <h1>调用方 API</h1>
        <p className="lead">端点详情来自当前 MeliData OpenAPI，并补充区域搜索契约。管理员和内部同步接口不会在此公开。</p>
        <section id="endpoints" className="reference-browser">
          <div className="endpoint-list">
            {query.isLoading && <div className="loading-row"><LoaderCircle className="spin" size={18} />正在读取 OpenAPI</div>}
            {query.isError && <div className="inline-error">OpenAPI 暂时不可用，区域搜索契约仍可浏览。</div>}
            {operations.map((operation) => <EndpointButton key={operation.id} operation={operation} selected={selected?.id === operation.id} onClick={() => setSelectedId(operation.id)} />)}
          </div>
          {selected && <OperationDetail operation={selected} />}
        </section>
      </article>
    </DocsLayout>
  )
}

function EndpointButton({ operation, selected, onClick }: { operation: PublicOperation; selected: boolean; onClick: () => void }) {
  return <button className={selected ? 'endpoint-button selected' : 'endpoint-button'} type="button" onClick={onClick}><span className={methodClass(operation.method)}>{operation.method}</span><span><strong>{operation.summary}</strong><code>{operation.path}</code></span><ChevronRight size={16} /></button>
}

function OperationDetail({ operation }: { operation: PublicOperation }) {
  const url = operation.path.replace('{collection}', 'products').replace('{id}', 'doc-001')
  const isPublicDownload = operation.tag === 'sdk'
  const code = isPublicDownload
    ? `curl -LO https://meilisearch.1oa.com.cn${url}`
    : `curl -X ${operation.method} https://meilisearch.1oa.com.cn${url} \\
  -H "Authorization: Bearer $MELIDATA_API_KEY" \\
  -H "Content-Type: application/json"`
  return <div id="operation" className="operation-detail"><div className="operation-title"><span className={methodClass(operation.method)}>{operation.method}</span><code>{operation.path}</code></div><h2>{operation.summary}</h2><p>{operation.description || '使用开放平台 API Key 调用此端点。'}</p><h3>认证</h3><p>{isPublicDownload ? '无需认证' : <code>Authorization: Bearer &lt;api_key&gt;</code>}</p><h3>请求示例</h3><CodeBlock code={code} /></div>
}
