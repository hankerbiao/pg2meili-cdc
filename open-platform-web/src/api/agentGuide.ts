// AI Agent 集成指南类型定义
// 对应后端 agent_guide.py 的 schema_version 1.0

export interface AgentGuide {
  schema_version: string
  service: {
    name: string
    version: string
    purpose: string
  }
  usage_policy: {
    mode: 'reference_only'
    direct_agent_execution: boolean
    authorization_required_for_real_requests: boolean
    instruction: string
  }
  links: {
    openapi: string
    human_docs: string
    llms: string
    python_sdk_download: string
  }
  endpoints: {
    data_base_url: string
    search_base_url: string
    search_path_template: string
    search_url_rule: string
    default_region: string
  }
  architecture: {
    write_path: Array<{
      order: number
      component: string
      purpose: string
      endpoint?: string
    }>
    search_path: Array<{
      order: number
      component: string
      purpose: string
      endpoint?: string
    }>
  }
  authentication: {
    scheme: string
    header: string
    scopes: Record<string, {
      description: string
      typical_users: string[]
    }>
    key_requirements: string[]
  }
  workflows: Array<{
    id: string
    title: string
    steps: string[]
    required_scopes: string[]
  }>
  operations: Array<{
    operation_id: string
    method: string
    path: string
    summary: string
    description: string
    required_scopes: string[]
    openapi_ref: string | null
  }>
  examples: Array<{
    language: string
    title: string
    description: string
    code: string
  }>
  non_targets: Array<{
    category: string
    paths: string[]
    reason: string
  }>
}
