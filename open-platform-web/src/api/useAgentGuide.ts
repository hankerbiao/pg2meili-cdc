import { useQuery } from '@tanstack/react-query'
import type { AgentGuide } from './agentGuide'

const AGENT_GUIDE_KEY = ['agent-guide'] as const

async function fetchAgentGuide(): Promise<AgentGuide> {
  const response = await fetch('/agent-guide.json')
  if (!response.ok) {
    throw new Error(
      `Agent Guide 加载失败 (${response.status})。`
    )
  }
  const data: AgentGuide = await response.json()

  // 基本结构校验
  if (!data.schema_version || !data.service || !data.operations) {
    throw new Error('Agent Guide 数据格式异常')
  }

  return data
}

export function useAgentGuide() {
  return useQuery({
    queryKey: AGENT_GUIDE_KEY,
    queryFn: fetchAgentGuide,
    staleTime: 5 * 60 * 1000, // 5 分钟
    retry: 2,
  })
}