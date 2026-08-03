import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Filter, LoaderCircle, RotateCcw } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { platformApi } from '../api/client'
import { formatDate } from './AppsPage'

const pageSize = 50

export function AuditPage() {
  const [offset, setOffset] = useState(0)
  const [filters, setFilters] = useState({ app_id: '', action: '', from_time: '', to_time: '' })
  const apps = useQuery({ queryKey: ['apps'], queryFn: platformApi.listApps })
  const params = useMemo(() => { const value = new URLSearchParams({ offset: String(offset), limit: String(pageSize) }); Object.entries(filters).forEach(([key, item]) => { if (item) value.set(key, key.endsWith('_time') ? new Date(item).toISOString() : item) }); return value }, [filters, offset])
  const logs = useQuery({ queryKey: ['audit', params.toString()], queryFn: () => platformApi.listAuditLogs(params) })

  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); setOffset(0); setFilters({ app_id: String(data.get('app_id') || ''), action: String(data.get('action') || ''), from_time: String(data.get('from_time') || ''), to_time: String(data.get('to_time') || '') }) }
  function reset(form: HTMLFormElement) { form.reset(); setOffset(0); setFilters({ app_id: '', action: '', from_time: '', to_time: '' }) }

  return <div className="console-page"><div className="page-header"><div><div className="eyebrow">AUDIT LOG</div><h1>审计日志</h1><p>查看管理员会话、应用变更与 API Key 生命周期操作。</p></div></div><form className="filter-bar" onSubmit={submit}><label>应用<select name="app_id"><option value="">全部应用</option>{apps.data?.map((app) => <option key={app.id} value={app.id}>{app.display_name}</option>)}</select></label><label>动作<select name="action"><option value="">全部动作</option><option value="session.login">登录</option><option value="session.logout">退出</option><option value="app.create">创建应用</option><option value="app.update">更新应用</option><option value="key.create">创建 Key</option><option value="key.rotate">轮换 Key</option><option value="key.revoke">撤销 Key</option></select></label><label>开始时间<input name="from_time" type="datetime-local" /></label><label>结束时间<input name="to_time" type="datetime-local" /></label><div className="filter-actions"><button className="button button-secondary" type="button" onClick={(event) => reset(event.currentTarget.form!)}><RotateCcw size={15} />重置</button><button className="button button-primary" type="submit"><Filter size={15} />筛选</button></div></form><section className="data-section"><div className="section-heading"><h2>操作记录</h2><span>offset {offset}</span></div>{logs.isLoading ? <div className="loading-row"><LoaderCircle className="spin" size={18} />正在加载审计记录</div> : logs.isError ? <div className="inline-error">{logs.error.message}</div> : logs.data?.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>时间</th><th>操作者</th><th>动作</th><th>目标类型</th><th>目标</th><th>来源 IP</th></tr></thead><tbody>{logs.data.map((log) => <tr key={log.id}><td>{formatDate(log.created_at)}</td><td><strong>{log.actor}</strong></td><td><code>{log.action}</code></td><td>{log.target_type}</td><td><code>{log.target_id || '-'}</code></td><td>{log.source_ip || '-'}</td></tr>)}</tbody></table></div> : <div className="empty-state compact"><Filter size={26} /><h3>没有匹配的记录</h3><p>调整筛选条件后重试。</p></div>}<div className="pagination"><button className="button button-secondary" type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}><ChevronLeft size={16} />上一页</button><span>第 {Math.floor(offset / pageSize) + 1} 页</span><button className="button button-secondary" type="button" disabled={(logs.data?.length ?? 0) < pageSize} onClick={() => setOffset(offset + pageSize)}>下一页<ChevronRight size={16} /></button></div></section></div>
}
