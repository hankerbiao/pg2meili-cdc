import { useState } from 'react'
import SearchTester from './components/SearchTester'
import BrowserSearchPage from './components/BrowserSearchPage'
import DocumentManager from './components/DocumentManager'

type ViewMode = 'tester' | 'browser' | 'manager'

const VIEWS: Array<{ mode: ViewMode; label: string }> = [
  { mode: 'tester', label: '接口测试模式' },
  { mode: 'browser', label: '浏览器模式' },
  { mode: 'manager', label: '文档管理' },
]

function App() {
  const [mode, setMode] = useState<ViewMode>('tester')

  return (
    <div className="app">
      <div className="top-nav">
        {VIEWS.map((view) => (
          <button
            key={view.mode}
            className={`top-nav-btn ${mode === view.mode ? 'active' : ''}`}
            onClick={() => setMode(view.mode)}
          >
            {view.label}
          </button>
        ))}
      </div>
      {mode === 'tester' && <SearchTester />}
      {mode === 'browser' && <BrowserSearchPage />}
      {mode === 'manager' && <DocumentManager />}
    </div>
  )
}

export default App
