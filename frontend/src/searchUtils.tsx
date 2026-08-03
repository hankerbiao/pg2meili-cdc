import type { ReactNode } from 'react'
import type { SearchRequest } from './api'

export interface ParsedSearchCurl {
  baseUrl: string | null
  apiKey: string | null
  request: SearchRequest
}

export function buildSearchUrl(baseUrl: string, collection?: string): string {
  const url = `${baseUrl.replace(/\/$/, '')}/search`
  return collection?.trim()
    ? `${url}?collection=${encodeURIComponent(collection.trim())}`
    : url
}

export function buildSearchCurl(
  baseUrl: string,
  apiKey: string,
  request: SearchRequest | string,
): string {
  let body: unknown = request
  if (typeof request === 'string') {
    try {
      body = JSON.parse(request) as SearchRequest
    } catch {
      body = request
    }
  }

  let collection: string | undefined
  if (body && typeof body === 'object' && !Array.isArray(body)) {
    const { collection: requestCollection, ...payload } = body as SearchRequest
    collection = requestCollection
    body = { showRankingScore: true, ...payload }
  }

  const serialized = typeof body === 'string' ? body : JSON.stringify(body, null, 2)
  const escapedBody = serialized.replace(/'/g, `'\"'\"'`)
  return [
    `curl -X POST "${buildSearchUrl(baseUrl, collection)}" \\`,
    '  -H "Content-Type: application/json" \\',
    `  -H "Authorization: Bearer ${apiKey.trim() || '<YOUR_API_KEY>'}" \\`,
    `  --data-raw '${escapedBody}'`,
  ].join('\n')
}

export function parseSearchCurl(command: string): ParsedSearchCurl {
  const urlMatch = command.match(/curl.*?["'](http.*?)["']/) || command.match(/\s(http\S+)/)
  let url: URL | null = null
  try {
    if (urlMatch) url = new URL(urlMatch[1])
  } catch {
    throw new Error('cURL 中的 URL 无效')
  }

  const marker = ['--data-raw \'', '--data \'', '-d \''].find((item) => command.includes(item))
  let body = '{}'
  if (marker) {
    const rawBody = command.slice(command.indexOf(marker) + marker.length)
    const end = rawBody.lastIndexOf("'")
    body = (end === -1 ? rawBody : rawBody.slice(0, end)).replace(/'"'"'/g, "'")
  }

  const parsedBody: unknown = JSON.parse(body)
  if (!parsedBody || typeof parsedBody !== 'object' || Array.isArray(parsedBody)) {
    throw new Error('搜索请求体必须是 JSON 对象')
  }
  const request = { ...parsedBody } as SearchRequest
  const collection = url?.searchParams.get('collection')
  if (collection) request.collection = collection

  return {
    baseUrl: url?.origin ?? null,
    apiKey: command.match(/Authorization: Bearer\s+([^\s"']+)/)?.[1] ?? null,
    request,
  }
}

export function renderHighlight(text?: string, enabled = true): ReactNode {
  if (!text) return null

  return text.split(/(<em>.*?<\/em>)/g).map((part, index) => {
    const match = part.match(/^<em>(.*?)<\/em>$/)
    if (!match) return part
    return enabled ? <em key={index}>{match[1]}</em> : match[1]
  })
}
