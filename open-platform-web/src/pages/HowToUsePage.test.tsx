import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { HowToUsePage } from './HowToUsePage'

describe('HowToUsePage', () => {
  it('renders the onboarding overview with roles, flow, steps and key cautions', () => {
    render(<MemoryRouter initialEntries={['/docs/how-to-use']}><HowToUsePage /></MemoryRouter>)

    expect(screen.getByRole('heading', { name: '从申请 Key 到搜索成功' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '谁做什么' })).toBeInTheDocument()
    expect(screen.getByText('开通人（管理员或获授权同事）')).toBeInTheDocument()
    expect(screen.getByText('业务开发者', { selector: 'td' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '接入流程一览' })).toBeInTheDocument()
    expect(screen.getByText('开通应用')).toBeInTheDocument()
    expect(screen.getByText('创建并交付 API Key')).toBeInTheDocument()
    expect(screen.getByText('搜索验证')).toBeInTheDocument()
    expect(screen.getByText('了解什么是 MeliData 服务')).toBeInTheDocument()
    expect(screen.getByText('部署时填写 API Key')).toBeInTheDocument()
    expect(screen.getAllByRole('article')).toHaveLength(7)
    expect(screen.getByRole('link', { name: /打开控制台/ })).toHaveAttribute('href', '/console/apps')
    expect(screen.getByRole('link', { name: /打开 AI Agent 指南/ })).toHaveAttribute('href', '/docs/agent-guide')
    expect(screen.getByText(/API Key 只在创建时展示一次/)).toBeInTheDocument()
    expect(screen.getByText(/写入成功只代表中心数据源已保存/)).toBeInTheDocument()
  })
})
