import { Check, Copy } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ApiKeySecret } from '../api/types'
import { Dialog } from './Dialog'

export function ApiKeySecretDialog({ secrets, onClose }: { secrets: ApiKeySecret[]; onClose: () => void }) {
  const [copiedIds, setCopiedIds] = useState<Set<string>>(new Set())
  const secretIdentity = secrets.map((secret) => secret.id).join(',')

  useEffect(() => setCopiedIds(new Set()), [secretIdentity])

  async function copy(secret: ApiKeySecret) {
    await navigator.clipboard.writeText(secret.api_key)
    setCopiedIds((current) => new Set(current).add(secret.id))
  }

  async function copyAll() {
    const content = secrets
      .map((secret) => `${secret.name} (${secret.scopes.join(', ')})\n${secret.api_key}`)
      .join('\n\n')
    await navigator.clipboard.writeText(content)
    setCopiedIds(new Set(secrets.map((secret) => secret.id)))
  }

  const allCopied = secrets.length > 0 && secrets.every((secret) => copiedIds.has(secret.id))
  return (
    <Dialog
      open={secrets.length > 0}
      onOpenChange={(open) => !open && onClose()}
      title={secrets.length > 1 ? '保存你的 API Keys' : '保存你的 API Key'}
      description="完整密钥只显示这一次。关闭后无法再次查看。"
    >
      <div className="secret-panel">
        <div className="secret-warning">请立即保存到对应调用端的密钥管理位置</div>
        <div className="secret-list">
          {secrets.map((secret) => (
            <section className="secret-entry" key={secret.id}>
              <div className="secret-meta">
                <strong>{secret.name}</strong>
                <span>{secret.scopes.join(' + ')}</span>
              </div>
              <div className="secret-value">
                <code>{secret.api_key}</code>
                <button className="icon-button on-dark" type="button" onClick={() => copy(secret)} aria-label={`复制 ${secret.name}`}>
                  {copiedIds.has(secret.id) ? <Check size={17} /> : <Copy size={17} />}
                </button>
              </div>
            </section>
          ))}
        </div>
        <div className="dialog-actions secret-actions">
          {secrets.length > 1 && (
            <button className="button button-secondary" type="button" onClick={copyAll}>
              {allCopied ? <Check size={16} /> : <Copy size={16} />}{allCopied ? '已复制全部' : '复制全部'}
            </button>
          )}
          <button className="button button-primary" type="button" onClick={onClose}>
            {allCopied ? '已保存，关闭' : '我已保存，关闭'}
          </button>
        </div>
      </div>
    </Dialog>
  )
}
