import { useState } from 'react'
import type { ReactNode } from 'react'
import { Download } from 'lucide-react'

interface SdkDownloadButtonProps {
  url: string
  fallbackName: string
  children: ReactNode
}

/**
 * 通过 fetch + blob 触发 SDK 下载，而非依赖 <a download>。
 *
 * 原因：当后端不可达或返回错误 JSON（如 404/503）时，<a download> 会把错误响应体
 * 直接当成文件保存，表现为“下载到一个 json 文件”。这里显式校验状态码与
 * Content-Type，仅在确认为 ZIP 时才触发下载，否则把错误信息呈现给用户。
 */
export function SdkDownloadButton({ url, fallbackName, children }: SdkDownloadButtonProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleClick() {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(url, { credentials: 'include' })
      if (!res.ok) {
        let message = `下载失败（HTTP ${res.status}）`
        try {
          const payload = await res.json()
          if (payload?.message) message = payload.message
        } catch {
          // 忽略非 JSON 错误体
        }
        throw new Error(message)
      }
      const contentType = res.headers.get('content-type') || ''
      if (!contentType.includes('zip')) {
        throw new Error('服务端未返回可用的 SDK 安装包，请稍后重试')
      }
      const blob = await res.blob()
      const disposition = res.headers.get('content-disposition') || ''
      const match = disposition.match(/filename="?([^";]+)"?/)
      const filename = match?.[1] || fallbackName
      const objectUrl = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = objectUrl
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(objectUrl)
    } catch (err) {
      setError(err instanceof Error ? err.message : '下载失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="sdk-download-action">
      <button type="button" className="button button-primary" onClick={handleClick} disabled={busy}>
        <Download size={16} />
        {busy ? '下载中…' : children}
      </button>
      {error && (
        <span className="sdk-download-error" role="alert">
          {error}
        </span>
      )}
    </div>
  )
}
