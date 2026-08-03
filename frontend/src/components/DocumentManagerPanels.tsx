import type { DocumentData } from '../api'

type DocumentID = DocumentData['id']

interface IndexManagerPanelProps {
  collection: string
  indexes: string[]
  loading: boolean
  onCollectionChange: (value: string) => void
  onDelete: (collection: string) => void
  onRefresh: () => void
}

export function IndexManagerPanel({
  collection,
  indexes,
  loading,
  onCollectionChange,
  onDelete,
  onRefresh,
}: IndexManagerPanelProps) {
  return (
    <section>
      <div className="manager-panel-header">
        <h2>索引管理</h2>
        <button className="manager-button" onClick={onRefresh} disabled={loading}>
          {loading ? '加载中...' : '刷新索引列表'}
        </button>
      </div>

      <div className="manager-index-delete">
        <label>使用当前集合名称快速删除索引</label>
        <div>
          <input value={collection} onChange={(event) => onCollectionChange(event.target.value)} />
          <button className="manager-button manager-button-danger" onClick={() => onDelete(collection)} disabled={loading}>
            {loading ? '删除中...' : '删除该索引'}
          </button>
        </div>
      </div>

      <h3 className="manager-subtitle">当前应用索引列表</h3>
      {loading && indexes.length === 0 ? (
        <div>加载中...</div>
      ) : indexes.length === 0 ? (
        <div className="manager-empty">暂无索引</div>
      ) : (
        <div className="manager-index-list">
          {indexes.map((name) => (
            <div className="manager-index-row" key={name}>
              <span>{name}</span>
              <button className="manager-link manager-link-danger" onClick={() => onDelete(name)} disabled={loading}>
                删除索引
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

interface DocumentListPanelProps {
  collection: string
  documents: DocumentData[]
  loading: boolean
  onDelete: (id: DocumentID) => void
  onEdit: (id: DocumentID) => void
  onRefresh: () => void
}

const documentPreview = (document: DocumentData) => {
  const json = JSON.stringify(document, null, 2)
  return json.length > 200 ? `${json.slice(0, 200)}...` : json
}

export function DocumentListPanel({
  collection,
  documents,
  loading,
  onDelete,
  onEdit,
  onRefresh,
}: DocumentListPanelProps) {
  return (
    <section>
      <div className="manager-panel-header">
        <h2>文档列表 ({collection})</h2>
        <button className="manager-button" onClick={onRefresh}>刷新</button>
      </div>

      {loading ? (
        <div>加载中...</div>
      ) : documents.length === 0 ? (
        <div className="manager-empty">暂无文档</div>
      ) : (
        <div className="manager-document-list">
          {documents.map((document) => (
            <article className="manager-document" key={document.id}>
              <div className="manager-document-header">
                <strong>{document.id}</strong>
                <div>
                  <button className="manager-link" onClick={() => onEdit(document.id)}>编辑</button>
                  <button className="manager-link manager-link-danger" onClick={() => onDelete(document.id)}>删除</button>
                </div>
              </div>
              <pre>{documentPreview(document)}</pre>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

interface DocumentEditorPanelProps {
  content: string
  editingId: DocumentID | null
  loading: boolean
  mode: 'create' | 'edit'
  onCancel: () => void
  onChange: (value: string) => void
  onSave: () => void
}

export function DocumentEditorPanel({
  content,
  editingId,
  loading,
  mode,
  onCancel,
  onChange,
  onSave,
}: DocumentEditorPanelProps) {
  const creating = mode === 'create'
  return (
    <section className="manager-editor">
      <h2>{creating ? '新建文档' : `编辑文档: ${editingId}`}</h2>
      <label htmlFor="document-json">JSON 内容</label>
      <textarea
        id="document-json"
        value={content}
        onChange={(event) => onChange(event.target.value)}
      />
      <div className="manager-actions">
        <button className="manager-button manager-button-primary" onClick={onSave} disabled={loading}>
          {loading ? '提交中...' : (creating ? '创建文档' : '保存修改')}
        </button>
        <button className="manager-button" onClick={onCancel}>取消</button>
      </div>
    </section>
  )
}
