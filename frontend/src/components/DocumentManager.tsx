import React, { useState, useEffect } from 'react'
import {
  listDocuments,
  createDocument,
  updateDocument,
  deleteDocument,
  getDocument,
  listIndexes,
  deleteIndex
} from '../api'

const DEFAULT_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcHBfbmFtZSI6ImxpYmlhb190ZXN0Iiwic2NvcGVzIjpbXSwiZXhwIjoxODMwMzU1MTk4fQ.HKsX8kU5UHpZfWbw-bxivup21jnON2k6zXw6LpHNtoY'

const DocumentManager: React.FC = () => {
  const [baseUrl, setBaseUrl] = useState('http://10.32.129.188:8080')
  const [token, setToken] = useState(DEFAULT_TOKEN)
  const [collection, setCollection] = useState('shared_docs')
  const [activeTab, setActiveTab] = useState<'list' | 'create' | 'edit' | 'indexes'>('list')

  const [documents, setDocuments] = useState<any[]>([])
  const [indexes, setIndexes] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [deletedIndexCount, setDeletedIndexCount] = useState<number | null>(null)

  // Editor state
  const [editorContent, setEditorContent] = useState('{\n  "id": "new-doc-001",\n  "name": "示例数据"\n}')
  const [editingId, setEditingId] = useState<string | null>(null)

  const fetchDocuments = async () => {
    setLoading(true)
    setError(null)
    setSuccessMsg(null)
    try {
      const docs = await listDocuments(baseUrl, token, collection, 100, 0)
      setDocuments(docs)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载文档失败')
    } finally {
      setLoading(false)
    }
  }

  const fetchIndexes = async () => {
    setLoading(true)
    setError(null)
    setSuccessMsg(null)
    setDeletedIndexCount(null)
    try {
      const items = await listIndexes(baseUrl, token, 100, 0)
      setIndexes(items)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载索引失败')
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteIndex = async (targetCollection: string) => {
    const name = targetCollection || collection
    if (!name) {
      setError('请先填写要删除索引的集合名称')
      return
    }
    if (!window.confirm(`确定要删除索引 ${name} 吗？该集合下的文档将被逻辑删除。`)) {
      return
    }
    setLoading(true)
    setError(null)
    setSuccessMsg(null)
    setDeletedIndexCount(null)
    try {
      const res = await deleteIndex(baseUrl, token, name)
      setDeletedIndexCount(res.deleted_count)
      setSuccessMsg(`索引 ${res.collection} 删除成功，逻辑删除文档数量：${res.deleted_count}`)
      await fetchIndexes()
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除索引失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (activeTab === 'list') {
      fetchDocuments()
    }
  }, [activeTab, collection, baseUrl, token])

  const handleCreate = async () => {
    setLoading(true)
    setError(null)
    setSuccessMsg(null)
    try {
      const payload = JSON.parse(editorContent)
      if (!payload.id) {
        throw new Error('文档必须包含 id 字段')
      }
      await createDocument(baseUrl, token, collection, payload)
      setSuccessMsg(`文档 ${payload.id} 创建成功`)
      // Optional: switch to list or clear form
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建失败')
    } finally {
      setLoading(false)
    }
  }

  const handleUpdate = async () => {
    setLoading(true)
    setError(null)
    setSuccessMsg(null)
    try {
      const payload = JSON.parse(editorContent)
      if (!payload.id) {
        throw new Error('文档必须包含 id 字段')
      }
      // Although updateDocument calls createDocument internally (upsert), we keep semantic separate
      await updateDocument(baseUrl, token, collection, payload)
      setSuccessMsg(`文档 ${payload.id} 更新成功`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新失败')
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!window.confirm(`确定要删除文档 ${id} 吗？`)) return
    
    setLoading(true)
    setError(null)
    try {
      await deleteDocument(baseUrl, token, collection, id)
      setSuccessMsg(`文档 ${id} 删除成功`)
      fetchDocuments() // refresh list
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败')
    } finally {
      setLoading(false)
    }
  }

  const startEdit = async (id: string) => {
    setLoading(true)
    setError(null)
    try {
      const doc = await getDocument(baseUrl, token, collection, id)
      // Remove server-injected fields if needed, or keep them. 
      // Usually users might want to edit the payload.
      // For simplicity, we show the full doc.
      setEditorContent(JSON.stringify(doc, null, 2))
      setEditingId(id)
      setActiveTab('edit')
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取文档详情失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="search-tester">
      <header className="header" style={{ background: 'linear-gradient(135deg, #10B981 0%, #059669 100%)' }}>
        <h1>通用文档管理</h1>
        <p>UniData 通用数据 CRUD 管理界面</p>
      </header>

      <div className="main-container">
        {/* Sidebar */}
        <aside className="sidebar">
          <div className="sidebar-title">功能菜单</div>
          <div className="scenario-list">
            <div 
              className={`scenario-item ${activeTab === 'list' ? 'active' : ''}`}
              style={{ backgroundColor: activeTab === 'list' ? '#e6fffa' : 'transparent' }}
              onClick={() => setActiveTab('list')}
            >
              <div className="scenario-name">文档列表</div>
              <div className="scenario-desc">查看当前集合下的所有文档</div>
            </div>
            <div 
              className={`scenario-item ${activeTab === 'create' ? 'active' : ''}`}
              style={{ backgroundColor: activeTab === 'create' ? '#e6fffa' : 'transparent' }}
              onClick={() => {
                setActiveTab('create')
                setEditingId(null)
                setEditorContent('{\n  "id": "new-doc-001",\n  "name": "示例数据"\n}')
                setSuccessMsg(null)
                setError(null)
              }}
            >
              <div className="scenario-name">新建文档</div>
              <div className="scenario-desc">创建新的 JSON 文档</div>
            </div>
            <div
              className={`scenario-item ${activeTab === 'indexes' ? 'active' : ''}`}
              style={{ backgroundColor: activeTab === 'indexes' ? '#e6fffa' : 'transparent' }}
              onClick={() => {
                setActiveTab('indexes')
                setSuccessMsg(null)
                setError(null)
                setDeletedIndexCount(null)
                fetchIndexes()
              }}
            >
              <div className="scenario-name">索引管理</div>
              <div className="scenario-desc">查看索引列表并删除集合索引</div>
            </div>
          </div>
          
          <div className="sidebar-title" style={{ marginTop: '20px' }}>配置</div>
          <div style={{ padding: '16px' }}>
            <div style={{ marginBottom: '12px' }}>
              <label style={{ display: 'block', fontSize: '12px', marginBottom: '4px', color: '#666' }}>API 地址</label>
              <input 
                style={{ width: '100%', padding: '6px', borderRadius: '4px', border: '1px solid #ddd' }}
                value={baseUrl}
                onChange={e => setBaseUrl(e.target.value)}
              />
            </div>
            <div style={{ marginBottom: '12px' }}>
              <label style={{ display: 'block', fontSize: '12px', marginBottom: '4px', color: '#666' }}>Token</label>
              <input 
                style={{ width: '100%', padding: '6px', borderRadius: '4px', border: '1px solid #ddd' }}
                value={token}
                onChange={e => setToken(e.target.value)}
                type="password"
              />
            </div>
            <div style={{ marginBottom: '12px' }}>
              <label style={{ display: 'block', fontSize: '12px', marginBottom: '4px', color: '#666' }}>集合名称 (Collection)</label>
              <input 
                style={{ width: '100%', padding: '6px', borderRadius: '4px', border: '1px solid #ddd' }}
                value={collection}
                onChange={e => setCollection(e.target.value)}
              />
            </div>
          </div>
        </aside>

        {/* Main Content */}
        <main className="content" style={{ flex: 1, padding: '24px', overflowY: 'auto', backgroundColor: '#fff' }}>
          
          {error && (
            <div style={{ padding: '12px', background: '#fee2e2', color: '#b91c1c', borderRadius: '6px', marginBottom: '16px' }}>
              {error}
            </div>
          )}
          
          {successMsg && (
            <div style={{ padding: '12px', background: '#d1fae5', color: '#047857', borderRadius: '6px', marginBottom: '16px' }}>
              {successMsg}
            </div>
          )}

          {activeTab === 'indexes' && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h2 style={{ fontSize: '18px', fontWeight: 600 }}>索引管理</h2>
                <button
                  onClick={fetchIndexes}
                  disabled={loading}
                  style={{ padding: '6px 12px', background: '#f3f4f6', border: '1px solid #d1d5db', borderRadius: '4px', cursor: 'pointer' }}
                >
                  {loading ? '加载中...' : '刷新索引列表'}
                </button>
              </div>

              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: 500, marginBottom: '8px' }}>
                  使用当前集合名称快速删除索引
                </label>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <input
                    style={{ flex: 1, padding: '6px', borderRadius: '4px', border: '1px solid #ddd' }}
                    value={collection}
                    onChange={e => setCollection(e.target.value)}
                  />
                  <button
                    onClick={() => handleDeleteIndex(collection)}
                    disabled={loading}
                    style={{ padding: '6px 12px', background: '#ef4444', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', opacity: loading ? 0.7 : 1 }}
                  >
                    {loading ? '删除中...' : '删除该索引'}
                  </button>
                </div>
              </div>

              <div>
                <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>当前应用索引列表</h3>
                {loading && indexes.length === 0 ? (
                  <div>加载中...</div>
                ) : indexes.length === 0 ? (
                  <div style={{ color: '#666', fontStyle: 'italic' }}>暂无索引</div>
                ) : (
                  <div style={{ display: 'grid', gap: '8px' }}>
                    {indexes.map(name => (
                      <div
                        key={name}
                        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', borderRadius: '6px', border: '1px solid #e5e7eb', background: '#f9fafb' }}
                      >
                        <span>{name}</span>
                        <button
                          onClick={() => handleDeleteIndex(name)}
                          disabled={loading}
                          style={{ padding: '4px 10px', background: '#fee2e2', color: '#b91c1c', border: 'none', borderRadius: '4px', cursor: 'pointer', opacity: loading ? 0.7 : 1 }}
                        >
                          删除索引
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                {deletedIndexCount !== null && (
                  <div style={{ marginTop: '12px', color: '#047857' }}>
                    最近一次删除操作逻辑删除文档数量：{deletedIndexCount}
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'list' && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h2 style={{ fontSize: '18px', fontWeight: 600 }}>文档列表 ({collection})</h2>
                <button 
                  onClick={fetchDocuments}
                  style={{ padding: '6px 12px', background: '#f3f4f6', border: '1px solid #d1d5db', borderRadius: '4px', cursor: 'pointer' }}
                >
                  刷新
                </button>
              </div>

              {loading ? (
                <div>加载中...</div>
              ) : (
                <div style={{ display: 'grid', gap: '12px' }}>
                  {documents.length === 0 ? (
                    <div style={{ color: '#666', fontStyle: 'italic' }}>暂无文档</div>
                  ) : (
                    documents.map((doc: any) => (
                      <div key={doc.id} style={{ border: '1px solid #e5e7eb', borderRadius: '8px', padding: '16px', background: '#fff', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                          <span style={{ fontWeight: 600, color: '#111827' }}>{doc.id}</span>
                          <div>
                            <button 
                              onClick={() => startEdit(doc.id)}
                              style={{ marginRight: '8px', color: '#2563eb', background: 'none', border: 'none', cursor: 'pointer' }}
                            >
                              编辑
                            </button>
                            <button 
                              onClick={() => handleDelete(doc.id)}
                              style={{ color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer' }}
                            >
                              删除
                            </button>
                          </div>
                        </div>
                        <pre style={{ background: '#f9fafb', padding: '8px', borderRadius: '4px', fontSize: '12px', overflowX: 'auto', margin: 0 }}>
                          {JSON.stringify(doc, null, 2).slice(0, 200) + (JSON.stringify(doc).length > 200 ? '...' : '')}
                        </pre>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          )}

          {(activeTab === 'create' || activeTab === 'edit') && (
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
              <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>
                {activeTab === 'create' ? '新建文档' : `编辑文档: ${editingId}`}
              </h2>
              
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', marginBottom: '16px' }}>
                <label style={{ marginBottom: '8px', fontSize: '14px', fontWeight: 500 }}>JSON 内容</label>
                <textarea
                  style={{ 
                    flex: 1, 
                    minHeight: '400px', 
                    padding: '12px', 
                    fontFamily: 'monospace', 
                    fontSize: '14px', 
                    border: '1px solid #d1d5db', 
                    borderRadius: '6px',
                    lineHeight: '1.5'
                  }}
                  value={editorContent}
                  onChange={e => setEditorContent(e.target.value)}
                />
              </div>

              <div style={{ display: 'flex', gap: '12px' }}>
                <button
                  onClick={activeTab === 'create' ? handleCreate : handleUpdate}
                  disabled={loading}
                  style={{
                    padding: '10px 24px',
                    background: '#10B981',
                    color: 'white',
                    border: 'none',
                    borderRadius: '6px',
                    cursor: loading ? 'not-allowed' : 'pointer',
                    opacity: loading ? 0.7 : 1,
                    fontWeight: 500
                  }}
                >
                  {loading ? '提交中...' : (activeTab === 'create' ? '创建文档' : '保存修改')}
                </button>
                <button
                  onClick={() => setActiveTab('list')}
                  style={{
                    padding: '10px 24px',
                    background: '#fff',
                    color: '#374151',
                    border: '1px solid #d1d5db',
                    borderRadius: '6px',
                    cursor: 'pointer'
                  }}
                >
                  取消
                </button>
              </div>
            </div>
          )}

        </main>
      </div>
    </div>
  )
}

export default DocumentManager
