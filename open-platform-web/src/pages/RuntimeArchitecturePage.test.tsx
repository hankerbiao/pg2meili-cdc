import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { RuntimeArchitecturePage } from './RuntimeArchitecturePage'

describe('RuntimeArchitecturePage', () => {
  it('documents the regional search proxy, asynchronous synchronization, and response tracing', () => {
    render(<MemoryRouter><RuntimeArchitecturePage /></MemoryRouter>)

    expect(screen.getByRole('heading', { name: '区域搜索与同步运行机制' })).toBeInTheDocument()
    expect(screen.getAllByText(/POST https:\/\/meilisearch\.1oa\.com\.cn\/documents\/api\/v1\/collections\//).length).toBeGreaterThan(0)
    expect(screen.getByText(/默认地址.*天津服务器/)).toBeInTheDocument()
    expect(screen.getByText(/仅 URL 不同/)).toBeInTheDocument()
    expect(screen.getAllByText('search:read', { selector: 'code' }).length).toBeGreaterThan(0)
    expect(screen.getByText('app_id + collection', { selector: 'code' })).toBeInTheDocument()
    expect(screen.getAllByText('meta.request_id', { selector: 'code' }).length).toBeGreaterThan(0)
    expect(screen.getByText(/CDC 同步到目标区域索引/)).toBeInTheDocument()
    expect(screen.getByText(/最终一致性/)).toBeInTheDocument()
  })
})
