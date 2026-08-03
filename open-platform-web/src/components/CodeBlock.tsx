import { Check, Copy } from 'lucide-react'
import { useEffect, useState } from 'react'

interface CodeBlockProps {
  code: string
  language?: string
}

export function CodeBlock({ code, language = 'bash' }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 1600)
    return () => window.clearTimeout(timer)
  }, [copied])

  async function copy() {
    await navigator.clipboard.writeText(code)
    setCopied(true)
  }

  return (
    <div className="code-block">
      <div className="code-toolbar"><span>{language}</span><button type="button" onClick={copy} aria-label="复制代码">{copied ? <Check size={15} /> : <Copy size={15} />}</button></div>
      <pre><code>{code}</code></pre>
    </div>
  )
}
