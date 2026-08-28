import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Check, Database, KeyRound, LoaderCircle, Pencil, Plus, RefreshCw, ShieldOff, Trash2, X } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { platformApi } from '../api/client'
import type { ApiKeyRecord, ApiKeySecret, AppUpdateInput, CollectionDetail, CollectionSettingsInput, KeyCreateInput, PlatformApp, Scope } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { ApiKeySecretDialog } from '../components/ApiKeySecretDialog'
import { ConfirmDialog, Dialog } from '../components/Dialog'
import { formatDate } from './AppsPage'

const keyProfiles: Array<{ value: 'backend' | 'frontend'; label: string; detail: string; scopes: Scope[] }> = [
  { value: 'backend', label: '后端完整访问', detail: '读写文档、管理索引并搜索文档，仅限服务端保存。', scopes: ['data:read', 'data:write', 'search:read'] },
  { value: 'frontend', label: '前端搜索只读', detail: '仅可搜索本应用文档，可安全提供给浏览器。', scopes: ['search:read'] },
]

export function AppDetailPage() {
  const { appId = '' } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const queryClient = useQueryClient()
  const [editOpen, setEditOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [secret, setSecret] = useState<ApiKeySecret | null>(null)
  const [action, setAction] = useState<{ type: 'rotate' | 'revoke' | 'status' | 'delete'; key?: ApiKeyRecord } | null>(null)
  const app = useQuery({ queryKey: ['app', appId], queryFn: () => platformApi.getApp(appId), enabled: Boolean(appId) })
  const keys = useQuery({ queryKey: ['keys', appId], queryFn: () => platformApi.listKeys(appId), enabled: Boolean(appId) })
  const collections = useQuery({ queryKey: ['collections', appId], queryFn: () => platformApi.listCollections(appId), enabled: Boolean(appId) })
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [activeCollection, setActiveCollection] = useState<CollectionDetail | null>(null)
  const updateSettings = useMutation({
    mutationFn: (input: { collection: string } & CollectionSettingsInput) =>
      platformApi.updateCollectionSettings(
        appId,
        input.collection,
        input,
        user?.csrf_token,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['collections', appId] })
      setSettingsOpen(false)
      setActiveCollection(null)
    },
  })

  const update = useMutation({ mutationFn: (input: AppUpdateInput) => platformApi.updateApp(appId, input, user?.csrf_token), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['app', appId] }); queryClient.invalidateQueries({ queryKey: ['apps'] }); setEditOpen(false); setAction(null) } })
  const createKey = useMutation({ mutationFn: (input: KeyCreateInput) => platformApi.createKey(appId, input, user?.csrf_token), onSuccess: (value) => { setCreateOpen(false); setSecret(value); queryClient.invalidateQueries({ queryKey: ['keys', appId] }) } })
  const rotate = useMutation({ mutationFn: (id: string) => platformApi.rotateKey(id, user?.csrf_token), onSuccess: (value) => { setAction(null); setSecret(value); queryClient.invalidateQueries({ queryKey: ['keys', appId] }) } })
  const revoke = useMutation({ mutationFn: (id: string) => platformApi.revokeKey(id, user?.csrf_token), onSuccess: () => { setAction(null); queryClient.invalidateQueries({ queryKey: ['keys', appId] }) } })
  const remove = useMutation({ mutationFn: () => platformApi.deleteApp(appId, user?.csrf_token), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['apps'] }); navigate('/console/apps') } })
  const openSettings = (c: CollectionDetail) => { setActiveCollection(c); setSettingsOpen(true) }

  if (app.isLoading) return <div className="page-loading"><LoaderCircle className="spin" />正在加载应用</div>
  if (!app.data) return <div className="console-page"><div className="inline-error">应用不存在或加载失败。</div></div>
  const record = app.data
  const actionError = rotate.error ?? revoke.error ?? update.error ?? remove.error
  return (
    <div className="console-page">
      <Link className="back-link" to="/console/apps"><ArrowLeft size={16} />所有应用</Link>
      <div className="page-header app-detail-header"><div><div className="app-title-row"><span className="record-icon large"><KeyRound size={20} /></span><div><h1>{record.display_name}</h1><code>{record.app_name}</code></div></div><p>{record.description || '暂无应用描述'}</p></div><div className="header-actions"><button className="button button-secondary" type="button" onClick={() => setEditOpen(true)}><Pencil size={16} />编辑</button><button className="button button-primary" type="button" disabled={record.status !== 'active'} onClick={() => setCreateOpen(true)}><Plus size={17} />创建 API Key</button></div></div>
      <div className="app-meta"><div><span>状态</span><strong><span className={`status-badge ${record.status}`}><i />{{ active: 'Active', disabled: 'Disabled', deleting: 'Deleting', deleted: 'Deleted' }[record.status] ?? 'Unknown'}</span></strong></div><div><span>负责人</span><strong>{record.owner_itcode}</strong></div><div><span>创建时间</span><strong>{formatDate(record.created_at)}</strong></div><div><span>版本</span><strong>v{record.version}</strong></div><button className={record.status === 'active' ? 'button button-danger subtle' : 'button button-secondary'} type="button" disabled={record.status === 'deleting' || record.status === 'deleted'} onClick={() => setAction({ type: 'status' })}>{record.status === 'active' ? <><ShieldOff size={16} />禁用应用</> : <><Check size={16} />启用应用</>}</button><button className="button button-danger subtle" type="button" disabled={record.status === 'deleted'} onClick={() => setAction({ type: 'delete' })}><Trash2 size={16} />{record.status === 'deleting' ? '继续删除' : '删除应用'}</button></div>
      {actionError && <div className="inline-error action-error">{actionError.message}</div>}
      <section className="data-section"><div className="section-heading"><div><h2>API Keys</h2><p>密钥按用途独立授权和轮换。</p></div><span>{keys.data?.length ?? 0} keys</span></div>{keys.isLoading ? <div className="loading-row"><LoaderCircle className="spin" size={18} />正在加载密钥</div> : keys.data?.length ? <div className="table-scroll"><table className="data-table key-table"><thead><tr><th>名称</th><th>密钥标识</th><th>Scopes</th><th>到期时间</th><th>最近使用</th><th>状态</th><th>操作</th></tr></thead><tbody>{keys.data.map((key) => <tr key={key.id}><td><strong>{key.name}</strong></td><td><code>{key.prefix}...{key.last_four}</code></td><td><div className="scope-chips">{key.scopes.map((scope) => <span key={scope}>{scope}</span>)}</div></td><td>{formatDate(key.expires_at)}</td><td>{formatDate(key.last_used_at)}</td><td><span className={`status-badge ${key.status}`}><i />{key.status === 'active' ? 'Active' : 'Revoked'}</span></td><td>{key.status === 'active' ? <div className="table-actions"><button className="icon-button" type="button" title="轮换" aria-label={`轮换 ${key.name}`} onClick={() => setAction({ type: 'rotate', key })}><RefreshCw size={16} /></button><button className="icon-button danger" type="button" title="撤销" aria-label={`撤销 ${key.name}`} onClick={() => setAction({ type: 'revoke', key })}><ShieldOff size={16} /></button></div> : <span className="muted">不可恢复</span>}</td></tr>)}</tbody></table></div> : <div className="empty-state compact"><KeyRound size={26} /><h3>还没有 API Key</h3><p>创建一把最小权限密钥开始接入。</p><button className="button button-primary" type="button" disabled={record.status !== 'active'} onClick={() => setCreateOpen(true)}><Plus size={17} />创建 API Key</button></div>}</section>
      <CollectionsSection collections={collections.data ?? []} isLoading={collections.isLoading} onConfigure={openSettings} />
      <EditAppDialog app={record} open={editOpen} onOpenChange={setEditOpen} pending={update.isPending} error={update.error?.message} ownerReadonly={!isAdmin} onSubmit={(input) => update.mutate(input)} />
      <CreateKeyDialog open={createOpen} onOpenChange={setCreateOpen} pending={createKey.isPending} error={createKey.error?.message} onSubmit={(input) => createKey.mutate(input)} />
      <ApiKeySecretDialog secrets={secret ? [secret] : []} onClose={() => setSecret(null)} />
      <ConfirmDialog open={action?.type === 'rotate'} onOpenChange={(open) => !open && setAction(null)} title="轮换 API Key" description={`轮换后 ${action?.key?.name ?? ''} 的旧密钥将立即失效，完整新密钥只显示一次。`} confirmLabel="确认轮换" onConfirm={() => action?.key && rotate.mutate(action.key.id)} />
      <ConfirmDialog open={action?.type === 'revoke'} onOpenChange={(open) => !open && setAction(null)} title="撤销 API Key" description={`撤销 ${action?.key?.name ?? ''} 后不可恢复，所有使用该密钥的请求会立即返回 401。`} confirmLabel="确认撤销" danger onConfirm={() => action?.key && revoke.mutate(action.key.id)} />
      <ConfirmDialog open={action?.type === 'status'} onOpenChange={(open) => !open && setAction(null)} title={record.status === 'active' ? '禁用应用' : '启用应用'} description={record.status === 'active' ? '禁用后，该应用下所有 API Key 将立即停止工作。' : '启用后，仍在有效期内且未撤销的 API Key 将恢复工作。'} confirmLabel={record.status === 'active' ? '确认禁用' : '确认启用'} danger={record.status === 'active'} onConfirm={() => update.mutate({ status: record.status === 'active' ? 'disabled' : 'active' })} />
      <ConfirmDialog open={action?.type === 'delete'} onOpenChange={(open) => !open && setAction(null)} title={record.status === 'deleting' ? '继续删除应用' : '删除应用'} description={`删除 ${record.display_name} 将撤销全部 API Key，删除其 Meilisearch 索引并回收独立数据库 schema，此操作不可恢复。`} confirmLabel={record.status === 'deleting' ? '继续删除' : '确认删除'} danger pending={remove.isPending} onConfirm={() => remove.mutate()} />
      <CollectionSettingsDialog collection={activeCollection} open={settingsOpen} onOpenChange={setSettingsOpen} pending={updateSettings.isPending} error={updateSettings.error?.message} onSubmit={(input) => activeCollection && updateSettings.mutate({ collection: activeCollection.collection, ...input })} />
    </div>
  )
}

function EditAppDialog({ app, open, onOpenChange, pending, error, ownerReadonly, onSubmit }: { app: PlatformApp; open: boolean; onOpenChange: (open: boolean) => void; pending: boolean; error?: string; ownerReadonly: boolean; onSubmit: (input: AppUpdateInput) => void }) {
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); const input: AppUpdateInput = { display_name: String(data.get('display_name')), description: String(data.get('description') || '') }; if (!ownerReadonly) input.owner_itcode = String(data.get('owner_itcode')); onSubmit(input) }
  return <Dialog open={open} onOpenChange={onOpenChange} title="编辑应用" description={`应用标识 ${app.app_name} 不可修改。`}><form className="form-grid" onSubmit={submit}><label>显示名称<input name="display_name" required defaultValue={app.display_name} /></label>{ownerReadonly ? <label>负责人 itcode<input value={app.owner_itcode} disabled /></label> : <label>负责人 itcode<input name="owner_itcode" required defaultValue={app.owner_itcode} /></label>}<label className="full-field">描述<textarea name="description" rows={4} defaultValue={app.description ?? ''} /></label>{error && <div className="form-error full-field">{error}</div>}<div className="dialog-actions full-field"><button className="button button-secondary" type="button" onClick={() => onOpenChange(false)}>取消</button><button className="button button-primary" type="submit" disabled={pending}>{pending ? '正在保存' : '保存更改'}</button></div></form></Dialog>
}

function CreateKeyDialog({ open, onOpenChange, pending, error, onSubmit }: { open: boolean; onOpenChange: (open: boolean) => void; pending: boolean; error?: string; onSubmit: (input: KeyCreateInput) => void }) {
  const [profile, setProfile] = useState<'backend' | 'frontend'>('backend')
  useEffect(() => { if (!open) setProfile('backend') }, [open])
  const defaultExpiry = new Date(Date.now() + 30 * 86400000); defaultExpiry.setMinutes(defaultExpiry.getMinutes() - defaultExpiry.getTimezoneOffset())
  const maxExpiry = new Date(); const maxExpiryMonth = maxExpiry.getMonth(); maxExpiry.setFullYear(maxExpiry.getFullYear() + 100); if (maxExpiry.getMonth() !== maxExpiryMonth) maxExpiry.setDate(0); maxExpiry.setMinutes(maxExpiry.getMinutes() - maxExpiry.getTimezoneOffset())
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); const selected = keyProfiles.find((item) => item.value === profile)!; onSubmit({ name: String(data.get('name')), scopes: selected.scopes, expires_at: new Date(String(data.get('expires_at'))).toISOString() }) }
  return <Dialog open={open} onOpenChange={onOpenChange} title="创建 API Key" description="选择调用方类型，系统会授予固定的最小权限。完整密钥只显示一次。"><form className="form-stack" onSubmit={submit}><label>Key 名称<input name="name" required maxLength={128} placeholder="backend-production" /></label><fieldset><legend>调用方类型</legend><div className="scope-options">{keyProfiles.map((item) => <label key={item.value} className={profile === item.value ? 'selected' : ''}><input type="radio" name="key_profile" checked={profile === item.value} onChange={() => setProfile(item.value)} /><span><strong>{item.label}</strong><small>{item.detail}</small><code>{item.scopes.join(' + ')}</code></span></label>)}</div></fieldset><label>到期时间<input type="datetime-local" name="expires_at" required defaultValue={defaultExpiry.toISOString().slice(0, 16)} max={maxExpiry.toISOString().slice(0, 16)} /></label>{error && <div className="form-error">{error}</div>}<div className="dialog-actions"><button className="button button-secondary" type="button" onClick={() => onOpenChange(false)}>取消</button><button className="button button-primary" type="submit" disabled={pending}>{pending ? '正在创建' : '创建密钥'}</button></div></form></Dialog>
}

const FIELD_NAME_PATTERN = /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$/

function FieldPicker({ title, tag, fields, selected, onChange, allowUnset = false, unsetLabel }: { title: string; tag: string; fields: string[]; selected: string[] | null; onChange: (value: string[] | null) => void; allowUnset?: boolean; unsetLabel?: string }) {
  const [custom, setCustom] = useState('')
  const [error, setError] = useState('')
  const value = selected ?? []
  const customSelected = value.filter((field) => !fields.includes(field))
  const allSelected = Array.from(new Set([...value, ...fields]))
  const unset = allowUnset && selected === null
  const toggle = (field: string) => {
    if (selected === null) { onChange([field]); return }
    onChange(value.includes(field) ? value.filter((x) => x !== field) : [...value, field])
  }
  const addCustom = () => {
    const field = custom.trim()
    if (!field) return
    if (!FIELD_NAME_PATTERN.test(field)) { setError('字段名需以字母 / 数字 / 下划线开头，仅可含字母、数字、_ . -，最长 128 字符'); return }
    if (value.includes(field) || fields.includes(field)) { setError(`字段 "${field}" 已存在`); return }
    onChange([...value, field]); setCustom(''); setError('')
  }
  return (
    <fieldset className="field-panel">
      <div className="field-panel-head">
        <div className="field-panel-title">{title}<code>{tag}</code></div>
        <span className={`field-count-badge${unset ? ' unset' : ''}`}>{unset ? '默认' : `${value.length} 已选`}</span>
        <span className="field-quick-actions">
          <button type="button" onClick={() => onChange(allSelected)} disabled={!unset && allSelected.length === value.length}>全选</button>
          <button type="button" onClick={() => onChange([])} disabled={!value.length}>清空</button>
          {allowUnset && <button type="button" onClick={() => onChange(null)} disabled={unset}>{unsetLabel ?? '恢复默认'}</button>}
        </span>
      </div>
      <div className="field-chips">
        {fields.map((field) => (
          <button key={field} type="button" className={`field-chip${!unset && value.includes(field) ? ' selected' : ''}`} onClick={() => toggle(field)}>
            {!unset && value.includes(field) && <Check size={12} strokeWidth={3} />}{field}
          </button>
        ))}
        {customSelected.map((field) => (
          <span key={field} className="field-chip selected custom">
            {field}
            <button type="button" className="chip-remove" aria-label={`移除 ${field}`} onClick={() => toggle(field)}><X size={11} /></button>
          </span>
        ))}
        {unset ? <span className="field-hint">{unsetLabel ?? '未配置（跟随默认）'}；点击字段即开始限定</span> : (!fields.length && !customSelected.length ? <span className="field-hint">暂无已发现字段，写入文档后自动发现；也可手动添加</span> : null)}
      </div>
      <div className="add-field-row">
        <input value={custom} placeholder="手动添加字段名，回车确认" onChange={(event) => { setCustom(event.target.value); setError('') }} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); addCustom() } }} />
        <button type="button" className="button button-secondary compact" onClick={addCustom} disabled={!custom.trim()}>添加</button>
      </div>
      {error && <span className="field-error">{error}</span>}
    </fieldset>
  )
}

function CollectionsSection({ collections, isLoading, onConfigure }: { collections: CollectionDetail[]; isLoading: boolean; onConfigure: (collection: CollectionDetail) => void }) {
  return (
    <section className="data-section">
      <div className="section-heading"><div><h2>集合</h2><p>应用下的数据集合，可配置可过滤 / 可排序字段。</p></div><span>{collections.length} collections</span></div>
      {isLoading ? (
        <div className="loading-row"><LoaderCircle className="spin" size={18} />正在加载集合</div>
      ) : collections.length ? (
        <div className="table-scroll"><table className="data-table"><thead><tr><th>集合</th><th>文档数</th><th>可过滤</th><th>可排序</th><th>更新时间</th><th>操作</th></tr></thead><tbody>
          {collections.map((collection) => (
            <tr key={collection.collection}>
              <td><code>{collection.collection}</code></td>
              <td>{collection.doc_count}</td>
              <td>{collection.filterable_attributes.length ? <div className="scope-chips">{collection.filterable_attributes.map((field) => <span key={field}>{field}</span>)}</div> : <span className="muted">—</span>}</td>
              <td>{collection.sortable_attributes.length ? <div className="scope-chips">{collection.sortable_attributes.map((field) => <span key={field}>{field}</span>)}</div> : <span className="muted">—</span>}</td>
              <td>{formatDate(collection.updated_at)}</td>
              <td><button className="button button-secondary subtle" type="button" onClick={() => onConfigure(collection)}>配置</button></td>
            </tr>
          ))}
        </tbody></table></div>
      ) : (
        <div className="empty-state compact"><Database size={26} /><h3>还没有集合</h3><p>通过 API 写入文档后，集合会出现在这里。</p></div>
      )}
    </section>
  )
}

function CollectionSettingsDialog({ collection, open, onOpenChange, pending, error, onSubmit }: { collection: CollectionDetail | null; open: boolean; onOpenChange: (open: boolean) => void; pending: boolean; error?: string; onSubmit: (input: CollectionSettingsInput) => void }) {
  const [filterable, setFilterable] = useState<string[]>([])
  const [sortable, setSortable] = useState<string[]>([])
  const [searchable, setSearchable] = useState<string[] | null>(null)
  const [displayed, setDisplayed] = useState<string[] | null>(null)
  const [distinct, setDistinct] = useState<string | null>(null)
  const [typo, setTypo] = useState<boolean | null>(null)
  const [pagination, setPagination] = useState<number | null>(null)
  const [faceting, setFaceting] = useState<number | null>(null)
  useEffect(() => {
    if (collection) {
      setFilterable(collection.filterable_attributes)
      setSortable(collection.sortable_attributes)
      setSearchable(collection.searchable_attributes)
      setDisplayed(collection.displayed_attributes)
      setDistinct(collection.distinct_attribute)
      setTypo(collection.typo_tolerance_enabled)
      setPagination(collection.pagination_max_total_hits)
      setFaceting(collection.faceting_max_values_per_facet)
    }
  }, [collection, open])
  if (!collection) return null
  const eq = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)
  const changed = !eq(filterable, collection.filterable_attributes) || !eq(sortable, collection.sortable_attributes) ||
    !eq(searchable, collection.searchable_attributes) || !eq(displayed, collection.displayed_attributes) ||
    !eq(distinct, collection.distinct_attribute) || !eq(typo, collection.typo_tolerance_enabled) ||
    !eq(pagination, collection.pagination_max_total_hits) || !eq(faceting, collection.faceting_max_values_per_facet)
  const advancedCount = [searchable, displayed, distinct, typo, pagination, faceting].filter((v) => v !== null && v !== undefined).length
  const distinctOptions = Array.from(new Set([...collection.fields, ...(distinct ? [distinct] : [])]))
  const submit = () => onSubmit({
    filterableAttributes: filterable,
    sortableAttributes: sortable,
    searchableAttributes: searchable,
    displayedAttributes: displayed,
    distinctAttribute: distinct,
    typoToleranceEnabled: typo,
    paginationMaxTotalHits: pagination,
    facetingMaxValuesPerFacet: faceting,
  })
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={`配置集合 · ${collection.collection}`} description="选择需要在搜索中过滤 / 排序的字段，保存后下发至 Meilisearch 索引。">
      <div className="form-stack">
        <div className="collection-meta">
          <div><span>文档数</span><strong>{collection.doc_count.toLocaleString()}</strong></div>
          <div><span>已发现字段</span><strong>{collection.fields.length}</strong></div>
          <div><span>最近更新</span><strong>{formatDate(collection.updated_at)}</strong></div>
        </div>
        <FieldPicker title="可过滤字段" tag="filterable" fields={collection.fields} selected={filterable} onChange={(value) => setFilterable(value ?? [])} />
        <FieldPicker title="可排序字段" tag="sortable" fields={collection.fields} selected={sortable} onChange={(value) => setSortable(value ?? [])} />
        <details className="advanced-settings">
          <summary>高级配置{advancedCount > 0 ? <span className="field-count-badge">{advancedCount} 已配置</span> : <span className="muted">未配置</span>}</summary>
          <div className="advanced-body">
            <FieldPicker title="可搜索字段" tag="searchableAttributes" fields={collection.fields} selected={searchable} onChange={setSearchable} allowUnset unsetLabel="全部字段可搜索" />
            <FieldPicker title="返回字段白名单" tag="displayedAttributes" fields={collection.fields} selected={displayed} onChange={setDisplayed} allowUnset unsetLabel="返回全部字段" />
            <div className="setting-grid">
              <label>去重字段<select value={distinct ?? ''} onChange={(event) => setDistinct(event.target.value || null)}><option value="">不启用</option>{distinctOptions.map((field) => <option key={field} value={field}>{field}</option>)}</select></label>
              <label>错字容错<select value={typo === null ? '' : String(typo)} onChange={(event) => setTypo(event.target.value === '' ? null : event.target.value === 'true')}><option value="">默认（开启）</option><option value="true">开启</option><option value="false">关闭</option></select></label>
              <label>分页上限 <code>maxTotalHits</code><input type="number" min={1} max={1000000} placeholder="默认 1000" value={pagination ?? ''} onChange={(event) => setPagination(event.target.value === '' ? null : Number(event.target.value))} /></label>
              <label>分面上限 <code>maxValuesPerFacet</code><input type="number" min={1} max={1000000} placeholder="默认 100" value={faceting ?? ''} onChange={(event) => setFaceting(event.target.value === '' ? null : Number(event.target.value))} /></label>
            </div>
          </div>
        </details>
        <p className="settings-tip">可过滤 / 可排序为覆盖语义（保存即生效）；高级配置项未配置时保持 Meilisearch 默认。全部保存为期望态并异步下发，Kafka 不可用时不会回滚已保存的配置。</p>
        {error && <div className="form-error">{error}</div>}
        <div className="dialog-actions">
          <button className="button button-secondary" type="button" onClick={() => onOpenChange(false)}>取消</button>
          <button className="button button-primary" type="button" disabled={pending || !changed} onClick={submit}>{pending ? '正在保存' : '保存配置'}</button>
        </div>
      </div>
    </Dialog>
  )
}
