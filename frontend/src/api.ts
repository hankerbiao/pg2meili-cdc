// 搜索 API 类型定义
export interface SearchRequest {
  q?: string
  offset?: number
  limit?: number
  filter?: string | string[]
  attributesToHighlight?: string[]
}

export interface SearchHit {
  id: number
  ext_id: string
  name: string
  summary: string
  tags: string[]
  _formatted?: {
    name?: string
    summary?: string
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

// 预设搜索场景
export interface PresetScenario {
  name: string
  description: string
  request: SearchRequest
}

export const PRESET_SCENARIOS: PresetScenario[] = [
  {
    name: '简单关键字搜索',
    description: '使用基础关键字进行搜索，查找包含"电源"的测试用例',
    request: { q: '电源' }
  },
  {
    name: '高亮搜索',
    description: '搜索并返回高亮结果，突出显示匹配的关键字',
    request: { q: '电源', attributesToHighlight: ['*'] }
  },
  {
    name: '分页搜索',
    description: '分页获取搜索结果，每页5条',
    request: { q: '电源', offset: 0, limit: 5 }
  },
  {
    name: '多标签过滤',
    description: '搜索包含"关机"的用例，过滤标签为"AMD"或"Intel"',
    request: { q: '关机', filter: ['tags = "AMD" OR tags = "Intel"'] }
  },
  {
    name: '空搜索获取全部',
    description: '不指定关键字，获取最近的测试用例',
    request: { limit: 10 }
  }
]

// API 调用函数
export async function search(
  baseUrl: string,
  token: string,
  request: SearchRequest
): Promise<SearchResponse> {
  const response = await fetch(`${baseUrl}/search`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`HTTP ${response.status}: ${errorText}`)
  }

  return response.json()
}

// 高亮文本渲染
export function renderHighlightedText(
  text: string | undefined,
  highlightedText: string | undefined
): string {
  if (highlightedText) {
    return highlightedText.replace(/<em>|<\/em>/g, '**')
  }
  return text || ''
}