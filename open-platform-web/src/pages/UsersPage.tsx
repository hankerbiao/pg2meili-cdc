import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle, RefreshCw, Search, UserX, UserCheck } from 'lucide-react'
import { platformApi } from '../api/client'
import type { PlatformUser } from '../api/types'
import { useAuth } from '../auth/AuthContext'

function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('zh-CN', { hour12: false })
}

export function UsersPage() {
  const { user } = useAuth()
  const csrf = user?.csrf_token
  const queryClient = useQueryClient()
  const [keyword, setKeyword] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'disabled'>('all')

  const params = new URLSearchParams()
  if (keyword.trim()) params.set('keyword', keyword.trim())
  if (statusFilter !== 'all') params.set('user_status', statusFilter)

  const users = useQuery({
    queryKey: ['users', keyword.trim(), statusFilter],
    queryFn: () => platformApi.listUsers(params),
  })

  const setStatus = useMutation({
    mutationFn: ({ itcode, target }: { itcode: string; target: 'active' | 'disabled' }) =>
      platformApi.setUserStatus(itcode, target, csrf),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })

  const rows = users.data?.items ?? []
  const adminCount = rows.filter((u) => u.role === 'admin').length
  const disabledCount = rows.filter((u) => u.status === 'disabled').length

  return (
    <div className="console-page">
      <div className="page-header">
        <div>
          <div className="eyebrow">USER MANAGEMENT</div>
          <h1>用户管理</h1>
          <p>查看开放平台已注册用户（管理员与 OA 单点登录员工），可启用 / 禁用账号。禁用后该用户无法登录控制台，其名下应用与 API Key 一并停用。</p>
        </div>
        <button
          className="button button-secondary"
          type="button"
          onClick={() => void users.refetch()}
          disabled={users.isFetching}
        >
          <RefreshCw size={17} className={users.isFetching ? 'spin' : ''} />刷新
        </button>
      </div>

      <div className="metric-strip">
        <div><span>用户总数</span><strong>{users.data?.total ?? 0}</strong></div>
        <div><span>管理员</span><strong>{adminCount}</strong></div>
        <div><span>已禁用</span><strong>{disabledCount}</strong></div>
      </div>

      <section className="data-section">
        <div className="section-heading">
          <h2>所有用户</h2>
          <div className="toolbar">
            <div className="search-box">
              <Search size={15} />
              <input
                type="text"
                placeholder="搜索工号 / 姓名 / 邮箱"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
              />
            </div>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}>
              <option value="all">全部状态</option>
              <option value="active">启用</option>
              <option value="disabled">禁用</option>
            </select>
          </div>
        </div>

        {users.isLoading ? (
          <div className="loading-row"><LoaderCircle className="spin" size={18} />正在加载用户列表</div>
        ) : users.isError ? (
          <div className="inline-error">{users.error.message}</div>
        ) : rows.length ? (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>工号 / 账号</th>
                  <th>姓名</th>
                  <th>邮箱</th>
                  <th>角色</th>
                  <th>状态</th>
                  <th>应用数</th>
                  <th>注册时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((u: PlatformUser) => (
                  <tr key={`${u.role}:${u.itcode}`}>
                    <td><strong>{u.itcode}</strong></td>
                    <td>{u.name || '—'}</td>
                    <td>{u.email || '—'}</td>
                    <td>
                      <span className={`role-badge ${u.role}`}>
                        {u.role === 'admin' ? '管理员' : 'OA 用户'}
                      </span>
                    </td>
                    <td>
                      <span className={`status-badge ${u.status}`}>
                        <i />{u.status === 'active' ? '启用' : '禁用'}
                      </span>
                    </td>
                    <td>{u.role === 'admin' ? '—' : u.app_count}</td>
                    <td>{formatDate(u.created_at)}</td>
                    <td>
                      {u.role === 'admin' ? (
                        <span className="muted-action">内置账号</span>
                      ) : u.status === 'active' ? (
                          <button
                          className="button button-danger subtle compact"
                          type="button"
                          disabled={setStatus.isPending}
                          onClick={() => void setStatus.mutate({ itcode: u.itcode, target: 'disabled' })}
                        >
                          <UserX size={15} />禁用
                        </button>
                      ) : (
                        <button
                          className="button button-secondary"
                          type="button"
                          disabled={setStatus.isPending}
                          onClick={() => void setStatus.mutate({ itcode: u.itcode, target: 'active' })}
                        >
                          <UserCheck size={15} />启用
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <UserX size={28} />
            <h3>暂无用户</h3>
            <p>OA 单点登录用户首次登录后会自动注册到此处。</p>
          </div>
        )}
      </section>
    </div>
  )
}
