import React, { useState } from 'react'
import SearchTester from './components/SearchTester'
import BrowserSearchPage from './components/BrowserSearchPage'
import DocumentManager from './components/DocumentManager'

type ViewMode = 'tester' | 'browser' | 'manager'

function App() {
  const [mode, setMode] = useState<ViewMode>('tester')

  return (
    <div className="app">
      <div className="top-nav">
        <button
          className={mode === 'tester' ? 'top-nav-btn active' : 'top-nav-btn'}
          onClick={() => setMode('tester')}
        >
          接口测试模式
        </button>
        <button
          className={mode === 'browser' ? 'top-nav-btn active' : 'top-nav-btn'}
          onClick={() => setMode('browser')}
        >
          浏览器模式
        </button>
        <button
          className={mode === 'manager' ? 'top-nav-btn active' : 'top-nav-btn'}
          onClick={() => setMode('manager')}
        >
          文档管理
        </button>
      </div>
      {mode === 'tester' && <SearchTester />}
      {mode === 'browser' && <BrowserSearchPage />}
      {mode === 'manager' && <DocumentManager />}
    </div>
  )
}

export default App
