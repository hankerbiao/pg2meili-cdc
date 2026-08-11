import { LoaderCircle } from 'lucide-react'
import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { OaAuthProvider, useOaAuth } from './auth/OaAuthContext'
import { ConsoleLayout } from './components/ConsoleLayout'
import { SiteLayout } from './components/SiteLayout'
import { AgentsPage } from './pages/AgentsPage'
import { ApiPlaygroundPage } from './pages/ApiPlaygroundPage'
import { ApiReferencePage } from './pages/ApiReferencePage'
import { AgentGuidePage } from './pages/AgentGuidePage'
import { AppDetailPage } from './pages/AppDetailPage'
import { AppsPage } from './pages/AppsPage'
import { AuditPage } from './pages/AuditPage'
import { UsersPage } from './pages/UsersPage'
import { AuthenticationPage } from './pages/AuthenticationPage'
import { LoginPage } from './pages/LoginPage'
import { OaCallbackPage } from './pages/OaCallbackPage'
import { OaHomePage } from './pages/OaHomePage'
import { PythonSdkPage } from './pages/PythonSdkPage'
import { QuickstartPage } from './pages/QuickstartPage'
import { RuntimeArchitecturePage } from './pages/RuntimeArchitecturePage'

function ProtectedRoute() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="page-loading"><LoaderCircle className="spin" /><span>正在验证登录会话</span></div>
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />
  return <ConsoleLayout />
}

function RequireAdmin() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="page-loading"><LoaderCircle className="spin" /><span>正在验证登录会话</span></div>
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />
  // 仅管理员可访问代理节点 / 审计日志 / 用户管理（后端同样强制 admin）
  if (user.role !== 'admin') return <Navigate to="/console/apps" replace />
  return <Outlet />
}

function ProtectedOaRoute() {
  const { oaUser, loading } = useOaAuth()
  if (loading) return <div className="page-loading"><LoaderCircle className="spin" /><span>正在验证 OA 会话</span></div>
  if (!oaUser) return <Navigate to="/login" replace />
  return <Outlet />
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
        <Route path="docs/agent-guide" element={<AgentGuidePage />} />
        <Route path="docs/runtime-architecture" element={<RuntimeArchitecturePage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="oa/callback" element={<OaCallbackPage />} />
        <Route path="oa" element={<OaAuthProvider><ProtectedOaRoute /></OaAuthProvider>}>
          <Route index element={<Navigate to="home" replace />} />
          <Route path="home" element={<OaHomePage />} />
        </Route>
        <Route path="console" element={<ProtectedRoute />}>
          <Route index element={<Navigate to="apps" replace />} />
          <Route path="apps" element={<AppsPage />} />
          <Route path="apps/:appId" element={<AppDetailPage />} />
          <Route path="api-playground" element={<ApiPlaygroundPage />} />
          <Route element={<RequireAdmin />}>
            <Route path="agents" element={<AgentsPage />} />
            <Route path="audit" element={<AuditPage />} />
            <Route path="users" element={<UsersPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/docs/quickstart" replace />} />
      </Routes>
    </SiteLayout>
  )
}
