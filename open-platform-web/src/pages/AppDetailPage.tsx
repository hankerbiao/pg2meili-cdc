import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Check, KeyRound, LoaderCircle, Pencil, Plus, RefreshCw, ShieldOff } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { platformApi } from '../api/client'
import type { ApiKeyRecord, ApiKeySecret, AppUpdateInput, KeyCreateInput, PlatformApp, Scope } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { ApiKeySecretDialog } from '../components/ApiKeySecretDialog'
import { ConfirmDialog, Dialog } from '../components/Dialog'
import { formatDate } from './AppsPage'

const allScopes: Array<{ value: Scope; label: string; detail: string }> = [
  { value: 'search:read', label: '搜索只读', detail: '发现区域节点并执行搜索' },
  { value: 'data:read', label: '数据只读', detail: '读取文档与集合' },
  { value: 'data:write', label: '数据写入', detail: '写入、删除与配置索引' },
]

export function AppDetailPage() {
  const { appId = '' } = useParams()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const queryClient = useQueryClient()
  const [editOpen, setEditOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [secret, setSecret] = useState<ApiKeySecret | null>(null)
  const [action, setAction] = useState<{ type: 'rotate' | 'revoke' | 'status'; key?: ApiKeyRecord } | null>(null)
  const app = useQuery({ queryKey: ['app', appId], queryFn: () => platformApi.getApp(appId), enabled: Boolean(appId) })
  const keys = useQuery({ queryKey: ['keys', appId], queryFn: () => platformApi.listKeys(appId), enabled: Boolean(appId) })

  const update = useMutation({ mutationFn: (input: AppUpdateInput) => platformApi.updateApp(appId, input, user?.csrf_token), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['app', appId] }); queryClient.invalidateQueries({ queryKey: ['apps'] }); setEditOpen(false); setAction(null) } })
  const createKey = useMutation({ mutationFn: (input: KeyCreateInput) => platformApi.createKey(appId, input, user?.csrf_token), onSuccess: (value) => { setCreateOpen(false); setSecret(value); queryClient.invalidateQueries({ queryKey: ['keys', appId] }) } })
  const rotate = useMutation({ mutationFn: (id: string) => platformApi.rotateKey(id, user?.csrf_token), onSuccess: (value) => { setAction(null); setSecret(value); queryClient.invalidateQueries({ queryKey: ['keys', appId] }) } })
  const revoke = useMutation({ mutationFn: (id: string) => platformApi.revokeKey(id, user?.csrf_token), onSuccess: () => { setAction(null); queryClient.invalidateQueries({ queryKey: ['keys', appId] }) } })

  if (app.isLoading) return <div className="page-loading"><LoaderCircle className="spin" />正在加载应用</div>
  if (!app.data) return <div className="console-page"><div className="inline-error">应用不存在或加载失败。</div></div>
  const record = app.data
  const actionError = rotate.error ?? revoke.error ?? update.error
  return (
    <div className="console-page">
      <Link className="back-link" to="/console/apps"><ArrowLeft size={16} />所有应用</Link>
      <div className="page-header app-detail-header"><div><div className="app-title-row"><span className="record-icon large"><KeyRound size={20} /></span><div><h1>{record.display_name}</h1><code>{record.app_name}</code></div></div><p>{record.description || '暂无应用描述'}</p></div><div className="header-actions"><button className="button button-secondary" type="button" onClick={() => setEditOpen(true)}><Pencil size={16} />编辑</button><button className="button button-primary" type="button" disabled={record.status !== 'active'} onClick={() => setCreateOpen(true)}><Plus size={17} />创建 API Key</button></div></div>
      <div className="app-meta"><div><span>状态</span><strong><span className={`status-badge ${record.status}`}><i />{record.status === 'active' ? 'Active' : 'Disabled'}</span></strong></div><div><span>负责人</span><strong>{record.owner_itcode}</strong></div><div><span>创建时间</span><strong>{formatDate(record.created_at)}</strong></div><div><span>版本</span><strong>v{record.version}</strong></div><button className={record.status === 'active' ? 'button button-danger subtle' : 'button button-secondary'} type="button" onClick={() => setAction({ type: 'status' })}>{record.status === 'active' ? <><ShieldOff size={16} />禁用应用</> : <><Check size={16} />启用应用</>}</button></div>
      {actionError && <div className="inline-error action-error">{actionError.message}</div>}
      <section className="data-section"><div className="section-heading"><div><h2>API Keys</h2><p>密钥按用途独立授权和轮换。</p></div><span>{keys.data?.length ?? 0} keys</span></div>{keys.isLoading ? <div className="loading-row"><LoaderCircle className="spin" size={18} />正在加载密钥</div> : keys.data?.length ? <div className="table-scroll"><table className="data-table key-table"><thead><tr><th>名称</th><th>密钥标识</th><th>Scopes</th><th>到期时间</th><th>最近使用</th><th>状态</th><th>操作</th></tr></thead><tbody>{keys.data.map((key) => <tr key={key.id}><td><strong>{key.name}</strong></td><td><code>{key.prefix}...{key.last_four}</code></td><td><div className="scope-chips">{key.scopes.map((scope) => <span key={scope}>{scope}</span>)}</div></td><td>{formatDate(key.expires_at)}</td><td>{formatDate(key.last_used_at)}</td><td><span className={`status-badge ${key.status}`}><i />{key.status === 'active' ? 'Active' : 'Revoked'}</span></td><td>{key.status === 'active' ? <div className="table-actions"><button className="icon-button" type="button" title="轮换" aria-label={`轮换 ${key.name}`} onClick={() => setAction({ type: 'rotate', key })}><RefreshCw size={16} /></button><button className="icon-button danger" type="button" title="撤销" aria-label={`撤销 ${key.name}`} onClick={() => setAction({ type: 'revoke', key })}><ShieldOff size={16} /></button></div> : <span className="muted">不可恢复</span>}</td></tr>)}</tbody></table></div> : <div className="empty-state compact"><KeyRound size={26} /><h3>还没有 API Key</h3><p>创建一把最小权限密钥开始接入。</p><button className="button button-primary" type="button" disabled={record.status !== 'active'} onClick={() => setCreateOpen(true)}><Plus size={17} />创建 API Key</button></div>}</section>
      <EditAppDialog app={record} open={editOpen} onOpenChange={setEditOpen} pending={update.isPending} error={update.error?.message} ownerReadonly={!isAdmin} onSubmit={(input) => update.mutate(input)} />
      <CreateKeyDialog open={createOpen} onOpenChange={setCreateOpen} pending={createKey.isPending} error={createKey.error?.message} onSubmit={(input) => createKey.mutate(input)} />
      <ApiKeySecretDialog secrets={secret ? [secret] : []} onClose={() => setSecret(null)} />
      <ConfirmDialog open={action?.type === 'rotate'} onOpenChange={(open) => !open && setAction(null)} title="轮换 API Key" description={`轮换后 ${action?.key?.name ?? ''} 的旧密钥将立即失效，完整新密钥只显示一次。`} confirmLabel="确认轮换" onConfirm={() => action?.key && rotate.mutate(action.key.id)} />
      <ConfirmDialog open={action?.type === 'revoke'} onOpenChange={(open) => !open && setAction(null)} title="撤销 API Key" description={`撤销 ${action?.key?.name ?? ''} 后不可恢复，所有使用该密钥的请求会立即返回 401。`} confirmLabel="确认撤销" danger onConfirm={() => action?.key && revoke.mutate(action.key.id)} />
      <ConfirmDialog open={action?.type === 'status'} onOpenChange={(open) => !open && setAction(null)} title={record.status === 'active' ? '禁用应用' : '启用应用'} description={record.status === 'active' ? '禁用后，该应用下所有 API Key 将立即停止工作。' : '启用后，仍在有效期内且未撤销的 API Key 将恢复工作。'} confirmLabel={record.status === 'active' ? '确认禁用' : '确认启用'} danger={record.status === 'active'} onConfirm={() => update.mutate({ status: record.status === 'active' ? 'disabled' : 'active' })} />
    </div>
  )
}

function EditAppDialog({ app, open, onOpenChange, pending, error, ownerReadonly, onSubmit }: { app: PlatformApp; open: boolean; onOpenChange: (open: boolean) => void; pending: boolean; error?: string; ownerReadonly: boolean; onSubmit: (input: AppUpdateInput) => void }) {
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); const input: AppUpdateInput = { display_name: String(data.get('display_name')), description: String(data.get('description') || '') }; if (!ownerReadonly) input.owner_itcode = String(data.get('owner_itcode')); onSubmit(input) }
  return <Dialog open={open} onOpenChange={onOpenChange} title="编辑应用" description={`应用标识 ${app.app_name} 不可修改。`}><form className="form-grid" onSubmit={submit}><label>显示名称<input name="display_name" required defaultValue={app.display_name} /></label>{ownerReadonly ? <label>负责人 itcode<input value={app.owner_itcode} disabled /></label> : <label>负责人 itcode<input name="owner_itcode" required defaultValue={app.owner_itcode} /></label>}<label className="full-field">描述<textarea name="description" rows={4} defaultValue={app.description ?? ''} /></label>{error && <div className="form-error full-field">{error}</div>}<div className="dialog-actions full-field"><button className="button button-secondary" type="button" onClick={() => onOpenChange(false)}>取消</button><button className="button button-primary" type="submit" disabled={pending}>{pending ? '正在保存' : '保存更改'}</button></div></form></Dialog>
}

function CreateKeyDialog({ open, onOpenChange, pending, error, onSubmit }: { open: boolean; onOpenChange: (open: boolean) => void; pending: boolean; error?: string; onSubmit: (input: KeyCreateInput) => void }) {
  const [scopes, setScopes] = useState<Scope[]>(['search:read'])
  useEffect(() => { if (!open) setScopes(['search:read']) }, [open])
  const defaultExpiry = new Date(Date.now() + 30 * 86400000); defaultExpiry.setMinutes(defaultExpiry.getMinutes() - defaultExpiry.getTimezoneOffset())
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); if (!scopes.length) return; onSubmit({ name: String(data.get('name')), scopes, expires_at: new Date(String(data.get('expires_at'))).toISOString() }) }
  return <Dialog open={open} onOpenChange={onOpenChange} title="创建 API Key" description="按调用场景授予最小权限。完整密钥只显示一次。"><form className="form-stack" onSubmit={submit}><label>Key 名称<input name="name" required maxLength={128} placeholder="production-search" /></label><fieldset><legend>Scopes</legend><div className="scope-options">{allScopes.map((scope) => <label key={scope.value} className={scopes.includes(scope.value) ? 'selected' : ''}><input type="checkbox" checked={scopes.includes(scope.value)} onChange={(event) => setScopes((current) => event.target.checked ? [...current, scope.value] : current.filter((item) => item !== scope.value))} /><span><strong>{scope.label}</strong><small>{scope.detail}</small><code>{scope.value}</code></span></label>)}</div>{!scopes.length && <span className="field-error">至少选择一个 scope</span>}</fieldset><label>到期时间<input type="datetime-local" name="expires_at" required defaultValue={defaultExpiry.toISOString().slice(0, 16)} /></label>{error && <div className="form-error">{error}</div>}<div className="dialog-actions"><button className="button button-secondary" type="button" onClick={() => onOpenChange(false)}>取消</button><button className="button button-primary" type="submit" disabled={pending || !scopes.length}>{pending ? '正在创建' : '创建密钥'}</button></div></form></Dialog>
}
