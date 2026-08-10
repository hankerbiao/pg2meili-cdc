import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { PythonSdkPage } from './PythonSdkPage'


describe('PythonSdkPage', () => {
  it('documents dedicated and generic APIs and exposes the SDK download', () => {
    render(<MemoryRouter><PythonSdkPage /></MemoryRouter>)

    expect(screen.getByRole('button', { name: /下载 Python SDK/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '常用独立接口' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '通用 request 接口' })).toBeInTheDocument()
    expect(screen.getByText('upsert_documents()')).toBeInTheDocument()
    expect(screen.getByText('AsyncMeliDataClient', { selector: 'code' })).toBeInTheDocument()
  })
})
