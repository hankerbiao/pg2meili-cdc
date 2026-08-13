import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiReferencePage } from './ApiReferencePage'

vi.mock('../api/useOpenApi', () => ({
  useOpenApiOperations: () => ({
    data: [{
      id: 'write',
      method: 'POST',
      path: '/api/v1/data/{collection}',
      summary: '写入文档',
      description: '写入业务文档',
      tag: 'generic-data',
      requiredScope: 'data:write',
      parameters: [{ name: 'collection', in: 'path', required: true, description: '集合名' }],
      requestBodyExample: '{"id":"doc-001"}',
      responses: [{ status: '200', description: '成功', example: '{"id":"doc-001"}' }],
    }],
    isLoading: false,
    isError: false,
  }),
}))

describe('ApiReferencePage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders the regional search contract with parameters, SDK call, response, and scope', () => {
    render(<MemoryRouter><ApiReferencePage /></MemoryRouter>)

    expect(screen.getByText('POST https://meilisearch.1oa.com.cn/documents/api/v1/collections/products/search')).toBeInTheDocument()
    expect(screen.getAllByText('search:read', { selector: 'code' }).length).toBeGreaterThan(0)
    expect(screen.getByText(/search_url=\"https:\/\/meilisearch\.1oa\.com\.cn\/documents/)).toBeInTheDocument()
    expect(screen.getByText('请求体')).toBeInTheDocument()
    expect(screen.getByText('响应')).toBeInTheDocument()
    expect(screen.getByText(/搜索结果/)).toBeInTheDocument()
  })
})
