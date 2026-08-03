import { useEffect, useState } from 'react'
import {
  createDocument,
  deleteDocument,
  deleteIndex,
  getDocument,
  listDocuments,
  listIndexes,
} from '../api'
import type { DocumentData } from '../api'
import {
  DocumentEditorPanel,
  DocumentListPanel,
  IndexManagerPanel,
} from './DocumentManagerPanels'

const DEFAULT_BASE_URL = import.meta.env.VITE_UNIDATA_API_BASE?.trim() || window.location.origin
const DEFAULT_API_KEY = import.meta.env.VITE_DEFAULT_API_KEY ?? ''
const NEW_DOCUMENT = '{\n  "id": "new-doc-001",\n  "name": "示例数据"\n}'
const errorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback

type ManagerTab = 'list' | 'create' | 'edit' | 'indexes'
type MenuTab = Exclude<ManagerTab, 'edit'>

const MENU_ITEMS: Array<{ tab: MenuTab; name: string; description: string }> = [
  { tab: 'list', name: '文档列表', description: '查看当前集合下的所有文档' },
  { tab: 'create', name: '新建文档', description: '创建新的 JSON 文档' },
  { tab: 'indexes', name: '索引管理', description: '查看索引列表并删除集合索引' },
]

const DocumentManager = () => {
  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE_URL)
  const [apiKey, setApiKey] = useState(DEFAULT_API_KEY)
  const [collection, setCollection] = useState('shared_docs')
  const [activeTab, setActiveTab] = useState<ManagerTab>('list')
  const [documents, setDocuments] = useState<DocumentData[]>([])
  const [indexes, setIndexes] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [editorContent, setEditorContent] = useState(NEW_DOCUMENT)
  const [editingId, setEditingId] = useState<DocumentData['id'] | null>(null)

  const runTask = async (task: () => Promise<void>, fallback: string) => {
    setLoading(true)
    setError(null)
    try {
      await task()
    } catch (error) {
      setError(errorMessage(error, fallback))
    } finally {
      setLoading(false)
    }
  }

  const fetchDocuments = () => runTask(async () => {
    setSuccessMsg(null)
    setDocuments(await listDocuments(baseUrl, apiKey, collection, 100, 0))
  }, '加载文档失败')

  const fetchIndexes = () => runTask(async () => {
    setSuccessMsg(null)
    setIndexes(await listIndexes(baseUrl, apiKey, 100, 0))
  }, '加载索引失败')

  useEffect(() => {
    if (activeTab === 'list' && apiKey.trim()) void fetchDocuments()
  }, [activeTab, collection, baseUrl, apiKey])

  const handleSave = () => {
    const action = activeTab === 'create' ? '创建' : '更新'
    return runTask(async () => {
      setSuccessMsg(null)
      const payload: unknown = JSON.parse(editorContent)
      if (!payload || typeof payload !== 'object' || Array.isArray(payload) || !('id' in payload) || !payload.id) {
        throw new Error('文档必须包含 id 字段')
      }
      await createDocument(baseUrl, apiKey, collection, payload as DocumentData)
      setSuccessMsg(`文档 ${payload.id} ${action}成功`)
    }, `${action}失败`)
  }

  const handleDelete = (id: DocumentData['id']) => {
    if (!window.confirm(`确定要删除文档 ${id} 吗？`)) return
    void runTask(async () => {
      await deleteDocument(baseUrl, apiKey, collection, id)
      setDocuments((current) => current.filter((document) => document.id !== id))
      setSuccessMsg(`文档 ${id} 删除成功`)
    }, '删除失败')
  }

  const startEdit = (id: DocumentData['id']) => runTask(async () => {
    const document = await getDocument(baseUrl, apiKey, collection, id)
    setEditorContent(JSON.stringify(document, null, 2))
    setEditingId(id)
    setActiveTab('edit')
  }, '获取文档详情失败')

  const handleDeleteIndex = (targetCollection: string) => {
    const name = targetCollection.trim()
    if (!name) {
      setError('请先填写要删除索引的集合名称')
      return
    }
    if (!window.confirm(`确定要删除索引 ${name} 吗？该集合下的文档将被逻辑删除。`)) return
    void runTask(async () => {
      setSuccessMsg(null)
      const result = await deleteIndex(baseUrl, apiKey, name)
      setIndexes((current) => current.filter((index) => index !== result.collection))
      setSuccessMsg(`索引 ${result.collection} 删除成功，逻辑删除文档数量：${result.deleted_count}`)
    }, '删除索引失败')
  }

  const openTab = (tab: MenuTab) => {
    setActiveTab(tab)
    setSuccessMsg(null)
    setError(null)
    if (tab === 'create') {
      setEditingId(null)
      setEditorContent(NEW_DOCUMENT)
    } else if (tab === 'indexes') {
      void fetchIndexes()
    }
  }

  const configFields = [
    { label: 'API 地址', value: baseUrl, setValue: setBaseUrl, type: 'text' },
    { label: 'API Key', value: apiKey, setValue: setApiKey, type: 'password' },
    { label: '集合名称 (Collection)', value: collection, setValue: setCollection, type: 'text' },
  ]

  return (
    <div className="search-tester">
      <header className="header manager-header">
        <h1>通用文档管理</h1>
        <p>UniData 通用数据 CRUD 管理界面</p>
      </header>

      <div className="main-container">
        <aside className="sidebar">
          <div className="sidebar-title">功能菜单</div>
          <div className="scenario-list">
            {MENU_ITEMS.map((item) => (
              <div
                key={item.tab}
                className={`scenario-item ${activeTab === item.tab ? 'active' : ''}`}
                onClick={() => openTab(item.tab)}
              >
                <div className="scenario-name">{item.name}</div>
                <div className="scenario-desc">{item.description}</div>
              </div>
            ))}
          </div>

          <div className="sidebar-title manager-config-title">配置</div>
          <div className="manager-config">
            {configFields.map((field) => (
              <div className="config-field" key={field.label}>
                <label>{field.label}</label>
                <input
                  type={field.type}
                  value={field.value}
                  onChange={(event) => field.setValue(event.target.value)}
                />
              </div>
            ))}
          </div>
        </aside>

        <main className="content manager-content">
          {error && <div className="manager-alert manager-alert-error">{error}</div>}
          {successMsg && <div className="manager-alert manager-alert-success">{successMsg}</div>}

          {activeTab === 'indexes' && (
            <IndexManagerPanel
              collection={collection}
              indexes={indexes}
              loading={loading}
              onCollectionChange={setCollection}
              onDelete={handleDeleteIndex}
              onRefresh={() => void fetchIndexes()}
            />
          )}
          {activeTab === 'list' && (
            <DocumentListPanel
              collection={collection}
              documents={documents}
              loading={loading}
              onDelete={handleDelete}
              onEdit={(id) => void startEdit(id)}
              onRefresh={() => void fetchDocuments()}
            />
          )}
          {(activeTab === 'create' || activeTab === 'edit') && (
            <DocumentEditorPanel
              content={editorContent}
              editingId={editingId}
              loading={loading}
              mode={activeTab}
              onCancel={() => setActiveTab('list')}
              onChange={setEditorContent}
              onSave={() => void handleSave()}
            />
          )}
        </main>
      </div>
    </div>
  )
}

export default DocumentManager
