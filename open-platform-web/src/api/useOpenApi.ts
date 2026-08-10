import { useQuery } from '@tanstack/react-query'
import { extractPublicOperations } from './openapi'

/** 加载并解析 MeliData OpenAPI 文档（调试台与参考页共用，统一缓存与错误处理）。 */
export function useOpenApiOperations() {
  return useQuery({
    queryKey: ['openapi-document'],
    queryFn: async () => {
      const response = await fetch('/openapi.json')
      if (!response.ok) throw new Error('无法加载 OpenAPI 描述')
      return extractPublicOperations(await response.json())
    },
  })
}
