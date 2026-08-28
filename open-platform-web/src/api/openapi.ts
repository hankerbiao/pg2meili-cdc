export interface OpenApiParameter {
  name: string
  in: 'path' | 'query' | 'header'
  required: boolean
  description?: string
  example?: unknown
}

export interface ApiResponseInfo {
  status: string
  description: string
  example?: string | null
}

export interface PublicOperation {
  id: string
  method: string
  path: string
  summary: string
  description: string
  tag: string
  requiredScope: string | null
  parameters: OpenApiParameter[]
  requestBodyExample: string | null
  responses: ApiResponseInfo[]
}

interface OpenApiParameterRaw {
  name: string
  in: 'path' | 'query' | 'header'
  required?: boolean
  description?: string
  example?: unknown
  schema?: OpenApiSchema
}

interface OpenApiSchema {
  type?: string
  format?: string
  properties?: Record<string, OpenApiSchema>
  items?: OpenApiSchema
  example?: unknown
  default?: unknown
  enum?: unknown[]
  $ref?: string
}

interface OpenApiOperation {
  operationId?: string
  summary?: string
  description?: string
  tags?: string[]
  parameters?: OpenApiParameterRaw[]
  requestBody?: { content?: Record<string, { schema?: OpenApiSchema; example?: unknown }> }
  responses?: Record<string, { description?: string; content?: Record<string, { schema?: OpenApiSchema; example?: unknown }> }>
}

interface OpenApiDocument {
  paths?: Record<string, Record<string, OpenApiOperation>>
  components?: { schemas?: Record<string, OpenApiSchema> }
}

const allowedTags = new Set(['generic-data', 'indexes', 'agents', 'sdk'])
const methods = new Set(['get', 'post', 'put', 'patch', 'delete'])

function scopeForOperation(path: string, method: string): string | null {
  if (path.startsWith('/api/v1/agents/online')) return 'search:read'
  if (path.startsWith('/api/v1/data/')) return method === 'get' ? 'data:read' : 'data:write'
  if (path.startsWith('/api/v1/indexes')) return method === 'get' ? 'data:read' : 'data:write'
  return null
}

// 需要排除的路径前缀（与 agent_guide.py 保持同步）
const excludedPathPrefixes = [
  '/api/v1/open-platform/',
  '/api/v1/auth/',
  '/api/v1/internal/',
]

// 需要排除的路径（精确匹配）
const excludedPathExact = new Set([
  '/api/v1/agents/register',
  '/api/v1/agents/cleanup-confirmations',
])

function resolveSchema(ref: string | undefined, doc: OpenApiDocument): OpenApiSchema | undefined {
  if (!ref || !ref.startsWith('#/')) return undefined
  const parts = ref.slice(2).split('/')
  let current: unknown = doc
  for (const part of parts) {
    if (current && typeof current === 'object') current = (current as Record<string, unknown>)[part]
    else return undefined
  }
  return current as OpenApiSchema | undefined
}

function sampleFromSchema(schema: OpenApiSchema | undefined, doc: OpenApiDocument): unknown {
  if (!schema) return null
  if (schema.$ref) return sampleFromSchema(resolveSchema(schema.$ref, doc), doc)
  if (schema.example !== undefined) return schema.example
  if (schema.default !== undefined) return schema.default
  switch (schema.type) {
    case 'object': {
      const obj: Record<string, unknown> = {}
      for (const [key, prop] of Object.entries(schema.properties ?? {})) {
        obj[key] = sampleFromSchema(prop, doc)
      }
      return obj
    }
    case 'array':
      return schema.items ? [sampleFromSchema(schema.items, doc)] : []
    case 'integer':
    case 'number':
      return 0
    case 'boolean':
      return true
    case 'string':
      if (schema.format === 'date-time') return '2024-01-01T00:00:00Z'
      if (schema.format === 'date') return '2024-01-01'
      if (schema.enum && schema.enum.length > 0) return schema.enum[0]
      return 'string'
    default:
      return null
  }
}

export function extractPublicOperations(document: OpenApiDocument): PublicOperation[] {
  const operations: PublicOperation[] = []
  for (const [path, pathItem] of Object.entries(document.paths ?? {})) {
    // 跳过排除的路径前缀
    if (excludedPathPrefixes.some(prefix => path.startsWith(prefix))) continue
    // 跳过排除的精确路径
    if (excludedPathExact.has(path)) continue

    for (const [method, operation] of Object.entries(pathItem)) {
      if (!methods.has(method) || !operation || typeof operation !== 'object') continue
      const tag = operation.tags?.find((item) => allowedTags.has(item))
      if (!tag) continue
      const parameters: OpenApiParameter[] = (operation.parameters ?? [])
        .filter((item) => item.in === 'path' || item.in === 'query')
        .map((item) => ({ name: item.name, in: item.in, required: Boolean(item.required), description: item.description }))
      const jsonContent = operation.requestBody?.content?.['application/json']
      let requestBodyExample: string | null = null
      if (jsonContent) {
        const example = jsonContent.example ?? sampleFromSchema(jsonContent.schema, document)
        if (example !== null && example !== undefined) requestBodyExample = JSON.stringify(example, null, 2)
      }
      const responses: ApiResponseInfo[] = Object.entries(operation.responses ?? {}).map(([status, resp]) => ({
        status,
        description: resp?.description ?? '',
        example: (() => {
          const content = resp?.content?.['application/json']
          if (!content) return null
          const value = content.example ?? sampleFromSchema(content.schema, document)
          return value === null || value === undefined ? null : JSON.stringify(value, null, 2)
        })(),
      }))
      operations.push({
        id: operation.operationId ?? `${method}-${path}`,
        method: method.toUpperCase(),
        path,
        summary: operation.summary ?? path,
        description: operation.description ?? '',
        tag,
        requiredScope: scopeForOperation(path, method),
        parameters,
        requestBodyExample,
        responses,
      })
    }
  }
  return operations.sort((a, b) => a.path.localeCompare(b.path) || a.method.localeCompare(b.method))
}

export const regionalSearchOperation: PublicOperation = {
  id: 'regional-search',
  method: 'POST',
  path: '/api/v1/collections/{collection}/search',
  summary: '在区域节点执行搜索',
  description: '使用具有 search:read scope 的 API Key 调用就近的区域搜索节点。',
  tag: 'search',
  requiredScope: 'search:read',
  parameters: [{ name: 'collection', in: 'path', required: true, description: '目标集合名称' }],
  requestBodyExample: JSON.stringify({ q: 'keyboard', limit: 10, show_ranking_score: true }, null, 2),
  responses: [
    { status: '200', description: '搜索结果', example: JSON.stringify({ hits: [], estimatedTotalHits: 0 }, null, 2) },
    { status: '400', description: '请求参数错误', example: null },
    { status: '401', description: 'API Key 无效或缺少 search:read scope', example: null },
  ],
}

/** 公网天津区域 Agent 的默认搜索入口。 */
export const DEFAULT_REGIONAL_SEARCH_BASE_URL = 'https://meilisearch.1oa.com.cn/documents'

export const PLATFORM_TAG_LABELS: Record<string, string> = {
  'generic-data': '数据',
  indexes: '索引',
  agents: 'Agent',
  sdk: 'SDK',
  search: '搜索',
}
