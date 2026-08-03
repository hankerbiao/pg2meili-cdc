import { describe, expect, it } from 'vitest'
import { extractPublicOperations } from './openapi'

describe('extractPublicOperations', () => {
  it('keeps caller APIs and excludes management/internal APIs', () => {
    const operations = extractPublicOperations({
      paths: {
        '/api/v1/data/{collection}': { post: { operationId: 'write', summary: '写入', tags: ['generic-data'] } },
        '/api/v1/indexes': { get: { operationId: 'indexes', summary: '索引', tags: ['indexes'] } },
        '/api/v1/sdk/python/download': { get: { operationId: 'python-sdk', summary: '下载 SDK', tags: ['sdk'] } },
        '/api/v1/open-platform/apps': { get: { operationId: 'apps', tags: ['open-platform'] } },
        '/api/v1/internal/api-keys/snapshot': { get: { operationId: 'snapshot', tags: ['internal'] } },
      },
    })
    expect(operations.map((item) => item.id)).toEqual(['write', 'indexes', 'python-sdk'])
  })
})
