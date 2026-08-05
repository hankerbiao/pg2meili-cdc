import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AppWindow, ArrowRight, CirclePlus, LoaderCircle, Plus } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { platformApi } from '../api/client'
import type { ApiKeySecret, AppBootstrapInput, PlatformApp, Scope } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { ApiKeySecretDialog } from '../components/ApiKeySecretDialog'
import { Dialog } from '../components/Dialog'

type AccessProfile = 'standard' | 'backend-only'

const accessProfiles: Array<{
  value: AccessProfile
  label: string
  detail: string
  scopeSummary: string
  keys: Array<{ name: string; scopes: Scope[] }>
}> = [
  {
    value: 'standard',
    label: '标准双密钥（推荐）',
    detail: '同时创建前端搜索只读 Key 和后端数据读写 Key。',
    scopeSummary: 'search:read / data:read + data:write',
    keys: [
      { name: 'frontend-search', scopes: ['search:read'] },
      { name: 'backend-data', scopes: ['data:read', 'data:write'] },
    ],
  },
  {
    value: 'backend-only',
    label: '仅后端读写',
    detail: '不允许浏览器直连搜索，只创建服务端数据读写 Key。',
    scopeSummary: 'data:read + data:write',
    keys: [{ name: 'backend-data', scopes: ['data:read', 'data:write'] }],
  },
]

export function AppsPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const isAdmin = user?.role === 'admin'
  const [dialogOpen, setDialogOpen] = useState(false)
  const [accessProfile, setAccessProfile] = useState<AccessProfile>('standard')
  const [secrets, setSecrets] = useState<ApiKeySecret[]>([])
  const apps = useQuery({ queryKey: ['apps'], queryFn: platformApi.listApps })
  const create = useMutation({
    mutationFn: (input: AppBootstrapInput) => platformApi.bootstrapApp(input, user?.csrf_token),
    onSuccess: (result) => {
      queryClient.setQueryData<PlatformApp[]>(['apps'], (current = []) => [
        result.app,
        ...current.filter((item) => item.id !== result.app.id),
      ])
      setDialogOpen(false)
      setSecrets(result.keys)
      void queryClient.invalidateQueries({ queryKey: ['apps'] })
    },
  })

  const selectedProfile = accessProfiles.find((profile) => profile.value === accessProfile)!
  const defaultExpiry = new Date(Date.now() + 90 * 86400000)
  defaultExpiry.setMinutes(defaultExpiry.getMinutes() - defaultExpiry.getTimezoneOffset())

  function openCreateDialog() {
    create.reset()
    setAccessProfile('standard')
    setDialogOpen(true)
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    // 负责人固定为当前登录人：不再提供 itcode 输入项，前端与后端均强制本人
    create.mutate({
      display_name: String(data.get('display_name')),
      app_name: String(data.get('app_name')),
      owner_itcode: user!.username,
      description: String(data.get('description') || '') || null,
      initial_keys: selectedProfile.keys.map((key) => ({
        ...key,
        expires_at: new Date(String(data.get('expires_at'))).toISOString(),
      })),
    })
  }

  const activeCount = apps.data?.filter((app) => app.status === 'active').length ?? 0
  return (
    <div className="console-page">
      <div className="page-header">
        <div>
          <div className="eyebrow">APPLICATIONS</div>
          <h1>应用与 API Keys</h1>
          <p>每个应用拥有独立的数据命名空间和一组可轮换的访问密钥。</p>
        </div>
        <button className="button button-primary" type="button" onClick={openCreateDialog}>
          <Plus size={17} />新建应用
        </button>
      </div>

      <div className="metric-strip">
        <div><span>应用总数</span><strong>{apps.data?.length ?? 0}</strong></div>
        <div><span>正常运行</span><strong>{activeCount}</strong></div>
        <div><span>已禁用</span><strong>{(apps.data?.length ?? 0) - activeCount}</strong></div>
      </div>

      <section className="data-section">
        <div className="section-heading"><h2>{isAdmin ? '所有应用' : '我的应用'}</h2><span>{apps.data?.length ?? 0} records</span></div>
        {apps.isLoading ? (
          <div className="loading-row"><LoaderCircle className="spin" size={18} />正在加载应用</div>
        ) : apps.isError ? (
          <div className="inline-error">{apps.error.message}</div>
        ) : apps.data?.length ? (
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>应用</th><th>应用标识</th><th>负责人</th><th>状态</th><th>更新时间</th><th aria-label="操作" /></tr></thead>
              <tbody>
                {apps.data.map((app) => (
                  <tr key={app.id}>
                    <td>
                      <Link className="primary-cell" to={`/console/apps/${app.id}`}>
                        <span className="record-icon"><AppWindow size={17} /></span>
                        <span><strong>{app.display_name}</strong><small>{app.description || '暂无描述'}</small></span>
                      </Link>
                    </td>
                    <td><code>{app.app_name}</code></td>
                    <td>{app.owner_itcode}</td>
                    <td><span className={`status-badge ${app.status}`}><i />{{ active: 'Active', disabled: 'Disabled', deleting: 'Deleting', deleted: 'Deleted' }[app.status] ?? 'Unknown'}</span></td>
                    <td>{formatDate(app.updated_at)}</td>
                    <td><Link className="row-action" to={`/console/apps/${app.id}`} aria-label={`打开 ${app.display_name}`}><ArrowRight size={17} /></Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <CirclePlus size={28} />
            <h3>创建第一个应用</h3>
            <p>应用是数据隔离与 API Key 管理的基本边界。</p>
            <button className="button button-primary" type="button" onClick={openCreateDialog}><Plus size={17} />新建应用</button>
          </div>
        )}
      </section>

      <Dialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title="新建应用"
        description="创建应用时按所选方案签发初始 API Key，完整密钥只显示一次。"
      >
        <form className="form-grid" onSubmit={submit}>
          <label>显示名称<input name="display_name" required maxLength={128} placeholder="商品搜索" /></label>
          <label>应用标识<input name="app_name" required pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,63}" placeholder="product_search" /></label>
          <label>Key 到期时间<input type="datetime-local" name="expires_at" required defaultValue={defaultExpiry.toISOString().slice(0, 16)} /></label>
          <fieldset className="full-field">
            <legend>初始 API Key 权限</legend>
            <div className="scope-options access-profile-options">
              {accessProfiles.map((profile) => (
                <label key={profile.value} className={accessProfile === profile.value ? 'selected' : ''}>
                  <input
                    type="radio"
                    name="access_profile"
                    value={profile.value}
                    checked={accessProfile === profile.value}
                    onChange={() => setAccessProfile(profile.value)}
                  />
                  <span>
                    <strong>{profile.label}</strong>
                    <small>{profile.detail}</small>
                    <code>{profile.scopeSummary}</code>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          <label className="full-field">描述<textarea name="description" maxLength={2000} rows={3} placeholder="说明应用的调用方与数据用途" /></label>
          {create.error && <div className="form-error full-field">{create.error.message}</div>}
          <div className="dialog-actions full-field">
            <button className="button button-secondary" type="button" onClick={() => setDialogOpen(false)}>取消</button>
            <button className="button button-primary" type="submit" disabled={create.isPending}>
              {create.isPending ? '正在创建' : '创建应用与 Key'}
            </button>
          </div>
        </form>
      </Dialog>

      <ApiKeySecretDialog secrets={secrets} onClose={() => setSecrets([])} />
    </div>
  )
}

export function formatDate(value: string | null) {
  if (!value) return '从未'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}
