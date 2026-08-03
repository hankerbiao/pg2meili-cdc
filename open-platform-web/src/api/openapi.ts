export interface PublicOperation {
  id: string
  method: string
  path: string
  summary: string
  description: string
  tag: string
}

interface OpenApiOperation {
  operationId?: string
  summary?: string
  description?: string
  tags?: string[]
}

interface OpenApiDocument {
  paths?: Record<string, Record<string, OpenApiOperation>>
}

const allowedTags = new Set(['generic-data', 'indexes', 'agents', 'sdk'])
const methods = new Set(['get', 'post', 'put', 'patch', 'delete'])

export function extractPublicOperations(document: OpenApiDocument): PublicOperation[] {
  const operations: PublicOperation[] = []
  for (const [path, pathItem] of Object.entries(document.paths ?? {})) {
    for (const [method, operation] of Object.entries(pathItem)) {
      if (!methods.has(method) || !operation || typeof operation !== 'object') continue
      const tag = operation.tags?.find((item) => allowedTags.has(item))
      if (!tag) continue
      operations.push({
        id: operation.operationId ?? `${method}-${path}`,
        method: method.toUpperCase(),
        path,
        summary: operation.summary ?? path,
        description: operation.description ?? '',
        tag,
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
}
