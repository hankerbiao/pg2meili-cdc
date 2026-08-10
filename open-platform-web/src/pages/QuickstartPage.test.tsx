import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { QuickstartPage } from './QuickstartPage'

describe('QuickstartPage', () => {
  it('groups the supporting integration documents with the quickstart flow', () => {
    render(<MemoryRouter initialEntries={['/docs/quickstart']}><QuickstartPage /></MemoryRouter>)

    expect(screen.getByRole('heading', { name: '完善集成' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '快速开始' })).toHaveAttribute('href', '/docs/quickstart')
    const links = screen.getAllByRole('link')
    expect(links.some((link) => link.getAttribute('href') === '/docs/authentication' && link.textContent?.includes('请求头、scope'))).toBe(true)
    expect(links.some((link) => link.getAttribute('href') === '/docs/python-sdk' && link.textContent?.includes('安装、客户端'))).toBe(true)
    expect(links.some((link) => link.getAttribute('href') === '/docs/api-reference' && link.textContent?.includes('浏览端点'))).toBe(true)
  })
})
