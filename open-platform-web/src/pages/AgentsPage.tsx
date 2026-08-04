import { useQuery } from '@tanstack/react-query'
import { LoaderCircle, RefreshCw, Server } from 'lucide-react'
import { platformApi } from '../api/client'
import type { AgentNode } from '../api/types'
import { formatDate } from './AppsPage'

export function AgentsPage() {
  const agents = useQuery({ queryKey: ['agents'], queryFn: platformApi.listAgents })

  const onlineCount = agents.data?.filter((agent: AgentNode) => agent.status === 'online').length ?? 0
  const offlineCount = (agents.data?.length ?? 0) - onlineCount
  const regionCount = new Set(agents.data?.map((agent: AgentNode) => agent.region)).size

  return (
    <div className="console-page">
      <div className="page-header">
        <div>
          <div className="eyebrow">AGENT NODES</div>
          <h1>代理节点</h1>
          <p>各区域部署的 meilisearch-sync-service 代理节点注册与健康状态。</p>
        </div>
        <button
          className="button button-secondary"
          type="button"
          onClick={() => void agents.refetch()}
          disabled={agents.isFetching}
        >
          <RefreshCw size={17} className={agents.isFetching ? 'spin' : ''} />刷新
        </button>
      </div>

      <div className="metric-strip">
        <div><span>节点总数</span><strong>{agents.data?.length ?? 0}</strong></div>
        <div><span>在线</span><strong>{onlineCount}</strong></div>
        <div><span>离线</span><strong>{offlineCount}</strong></div>
      </div>

      <section className="data-section">
        <div className="section-heading"><h2>所有节点</h2><span>{regionCount} regions · {agents.data?.length ?? 0} records</span></div>
        {agents.isLoading ? (
          <div className="loading-row"><LoaderCircle className="spin" size={18} />正在加载代理节点</div>
        ) : agents.isError ? (
          <div className="inline-error">{agents.error.message}</div>
        ) : agents.data?.length ? (
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>节点</th><th>主机名</th><th>区域</th><th>版本</th><th>状态</th><th>最近心跳</th><th>注册时间</th></tr></thead>
              <tbody>
                {agents.data.map((agent) => (
                  <tr key={agent.id}>
                    <td>
                      <span className="primary-cell">
                        <span className="record-icon"><Server size={17} /></span>
                        <span><strong>{agent.id}</strong><small>{agent.base_url}</small></span>
                      </span>
                    </td>
                    <td>{agent.hostname || '—'}</td>
                    <td>{agent.region}</td>
                    <td>{agent.version || '—'}</td>
                    <td><span className={`status-badge ${agent.status}`}><i />{agent.status === 'online' ? 'Online' : 'Offline'}</span></td>
                    <td>{formatDate(agent.last_seen_at)}</td>
                    <td>{formatDate(agent.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <Server size={28} />
            <h3>暂无注册节点</h3>
            <p>区域代理启动后会自动注册到此处。</p>
          </div>
        )}
      </section>
    </div>
  )
}
