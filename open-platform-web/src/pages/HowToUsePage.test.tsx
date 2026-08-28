import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { HowToUsePage } from './HowToUsePage'

describe('HowToUsePage', () => {
  it('renders the six-step onboarding flow and its key links', () => {
    render(<MemoryRouter initialEntries={['/docs/how-to-use']}><HowToUsePage /></MemoryRouter>)

    expect(screen.getByRole('heading', { name: '从需求评估到上线部署' })).toBeInTheDocument()
    expect(screen.getByText('了解什么是 MeliData 服务')).toBeInTheDocument()
    expect(screen.getByText('部署时填写 API Key')).toBeInTheDocument()
    expect(screen.getAllByRole('article')).toHaveLength(7)
    expect(screen.getByRole('link', { name: /打开控制台/ })).toHaveAttribute('href', '/console/apps')
    expect(screen.getByRole('link', { name: /打开 AI Agent 指南/ })).toHaveAttribute('href', '/docs/agent-guide')
  })
})
