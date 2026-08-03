import { LoaderCircle } from 'lucide-react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { ConsoleLayout } from './components/ConsoleLayout'
import { SiteLayout } from './components/SiteLayout'
import { ApiReferencePage } from './pages/ApiReferencePage'
import { AppDetailPage } from './pages/AppDetailPage'
import { AppsPage } from './pages/AppsPage'
import { AuditPage } from './pages/AuditPage'
import { AuthenticationPage } from './pages/AuthenticationPage'
import { LoginPage } from './pages/LoginPage'
import { PythonSdkPage } from './pages/PythonSdkPage'
import { QuickstartPage } from './pages/QuickstartPage'

function ProtectedRoute() {
  const { session, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="page-loading"><LoaderCircle className="spin" /><span>正在验证管理员会话</span></div>
  if (!session) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />
  return <ConsoleLayout />
}

export function App() {
  return (
    <SiteLayout>
      <Routes>
        <Route index element={<Navigate to="/docs/quickstart" replace />} />
        <Route path="docs/quickstart" element={<QuickstartPage />} />
        <Route path="docs/authentication" element={<AuthenticationPage />} />
        <Route path="docs/python-sdk" element={<PythonSdkPage />} />
        <Route path="docs/api-reference" element={<ApiReferencePage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="console" element={<ProtectedRoute />}>
          <Route index element={<Navigate to="apps" replace />} />
          <Route path="apps" element={<AppsPage />} />
          <Route path="apps/:appId" element={<AppDetailPage />} />
          <Route path="audit" element={<AuditPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/docs/quickstart" replace />} />
      </Routes>
    </SiteLayout>
  )
}
