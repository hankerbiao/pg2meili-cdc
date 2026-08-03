export interface SearchRequest {
  q?: string
  offset?: number
  limit?: number
  filter?: string | string[]
  attributesToHighlight?: string[]
  attributesToRetrieve?: string[]
  attributesToCrop?: string[]
  cropLength?: number
  collection?: string
  showRankingScore?: boolean
}

export interface SearchHit {
  id: number | string
  ext_id?: string
  name?: string
  title?: string
  summary?: string
  content?: string
  author?: string
  tags?: string[]
  _formatted?: {
    name?: string
    summary?: string
    title?: string
    content?: string
    [key: string]: string | undefined
  }
}

export interface SearchResponse {
  hits: SearchHit[]
  offset?: number
  limit?: number
  estimatedTotalHits?: number
  processingTimeMs?: number
}

interface ApiEnvelope<T> {
  data: T
  message: string
}

export type DocumentData = Record<string, unknown> & { id: string | number }

async function apiRequest<T>(url: string, apiKey: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...init.headers,
    },
  })
  return parseApiResponse<T>(response)
}

const apiUrl = (baseUrl: string, path: string) => `${baseUrl.replace(/\/$/, '')}${path}`

async function parseApiResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get('content-type') || ''
  const isJson = contentType.includes('application/json')
  if (!response.ok) {
    if (isJson) {
      const payload = await response.json() as Partial<ApiEnvelope<unknown>>
      const message = typeof payload?.message === 'string'
        ? payload.message
        : `HTTP ${response.status}`
      throw new Error(message)
    }
    const errorText = await response.text()
    throw new Error(`HTTP ${response.status}: ${errorText}`)
  }

  if (!isJson) {
    return undefined as T
  }

  const payload = await response.json() as ApiEnvelope<T> | T
  if (payload && typeof payload === 'object' && 'data' in payload && 'message' in payload) {
    return (payload as ApiEnvelope<T>).data
  }
  return payload as T
}

export interface PresetScenario {
  name: string
  description: string
  request: SearchRequest
}

export const PRESET_SCENARIOS: PresetScenario[] = [
  {
    name: '简单关键字搜索',
    description: '使用基础关键字进行搜索，查找包含"电源"的测试用例',
    request: { q: '电源', collection: 'shared_docs' }
  },
  {
    name: '高亮搜索',
    description: '搜索并返回高亮结果，突出显示匹配的关键字',
    request: { q: '电源', attributesToHighlight: ['*'], collection: 'shared_docs' }
  },
  {
    name: '分页搜索',
    description: '分页获取搜索结果，每页5条',
    request: { q: '电源', offset: 0, limit: 5, collection: 'shared_docs' }
  },
  {
    name: '多标签过滤',
    description: '搜索包含"关机"的用例，过滤标签为"AMD"或"Intel"',
    request: { q: '关机', filter: ['tags = "AMD" OR tags = "Intel"'], collection: 'shared_docs' }
  },
  {
    name: '空搜索获取全部',
    description: '不指定关键字，获取最近的测试用例',
    request: { limit: 10, collection: 'shared_docs' }
  }
]

export async function search(
  baseUrl: string,
  apiKey: string,
  request: SearchRequest
): Promise<SearchResponse> {
  const { collection, showRankingScore, ...rest } = request
  const payload = {
    ...rest,
    showRankingScore: showRankingScore ?? true,
  }
  const url = new URL(apiUrl(baseUrl, '/search'))
  if (collection?.trim()) url.searchParams.set('collection', collection.trim())

  return apiRequest<SearchResponse>(url.toString(), apiKey, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export interface DocumentResponse {
  status: string
  id: string
  collection: string
}

export async function createDocument(
  baseUrl: string,
  apiKey: string,
  collection: string,
  payload: DocumentData
): Promise<DocumentResponse> {
  return apiRequest<DocumentResponse>(apiUrl(baseUrl, `/api/v1/data/${encodeURIComponent(collection)}`), apiKey, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getDocument(
  baseUrl: string,
  apiKey: string,
  collection: string,
  id: string | number
): Promise<DocumentData> {
  return apiRequest<DocumentData>(apiUrl(baseUrl, `/api/v1/data/${encodeURIComponent(collection)}/${encodeURIComponent(String(id))}`), apiKey)
}

export async function deleteDocument(
  baseUrl: string,
  apiKey: string,
  collection: string,
  id: string | number
): Promise<DocumentResponse> {
  return apiRequest<DocumentResponse>(apiUrl(baseUrl, `/api/v1/data/${encodeURIComponent(collection)}/${encodeURIComponent(String(id))}`), apiKey, {
    method: 'DELETE',
  })
}

export async function listDocuments(
  baseUrl: string,
  apiKey: string,
  collection: string,
  limit: number = 20,
  offset: number = 0
): Promise<DocumentData[]> {
  const path = `/api/v1/data/${encodeURIComponent(collection)}?limit=${limit}&offset=${offset}`
  return apiRequest<DocumentData[]>(apiUrl(baseUrl, path), apiKey)
}

export async function listIndexes(
  baseUrl: string,
  apiKey: string,
  limit: number = 100,
  offset: number = 0
): Promise<string[]> {
  return apiRequest<string[]>(apiUrl(baseUrl, `/api/v1/index/indexes?limit=${limit}&offset=${offset}`), apiKey)
}

export interface DeleteIndexResponse {
  status: string
  collection: string
  deleted_count: number
}

export async function deleteIndex(
  baseUrl: string,
  apiKey: string,
  collection: string
): Promise<DeleteIndexResponse> {
  return apiRequest<DeleteIndexResponse>(apiUrl(baseUrl, `/api/v1/index/indexes/${encodeURIComponent(collection)}`), apiKey, {
    method: 'DELETE',
  })
}
