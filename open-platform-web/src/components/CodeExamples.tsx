import { useState } from 'react'
import { CodeBlock } from './CodeBlock'

interface CodeExamplesProps {
  examples: {
    curl: string
    python: string
  }
}

const labels = { curl: 'cURL', python: 'Python' } as const

export function CodeExamples({ examples }: CodeExamplesProps) {
  const [language, setLanguage] = useState<keyof typeof examples>('curl')
  return (
    <div className="code-examples">
      <div className="code-tabs" role="tablist" aria-label="代码示例语言">
        {(Object.keys(labels) as Array<keyof typeof labels>).map((item) => (
          <button key={item} role="tab" aria-selected={language === item} className={language === item ? 'active' : ''} type="button" onClick={() => setLanguage(item)}>{labels[item]}</button>
        ))}
      </div>
      <CodeBlock code={examples[language]} language={labels[language]} />
    </div>
  )
}
