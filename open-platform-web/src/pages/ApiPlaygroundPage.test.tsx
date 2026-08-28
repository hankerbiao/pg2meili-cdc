import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApiPlaygroundPage } from './ApiPlaygroundPage'

vi.mock('../api/useOpenApi', () => ({
  useOpenApiOperations: () => ({
    data: [],
    isLoading: false,
    isError: false,
  }),
}))

describe('ApiPlaygroundPage', () => {
  it('prefills the regional search base URL with the public Agent entrypoint', () => {
    render(<ApiPlaygroundPage />)

    expect(screen.getByLabelText('Base URL')).toHaveValue('https://meilisearch.1oa.com.cn/documents')
  })
})
