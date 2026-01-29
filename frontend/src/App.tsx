import React, { useState } from 'react'
import SearchTester from './components/SearchTester'
import BrowserSearchPage from './components/BrowserSearchPage'

type ViewMode = 'tester' | 'browser'

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
      </div>
      {mode === 'tester' ? <SearchTester /> : <BrowserSearchPage />}
    </div>
  )
}

export default App
