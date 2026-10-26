import type { ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'

import QualityPage from './pages/QualityPage'
import ComplaintsPage from './pages/ComplaintsPage'
import ProcessPage from './pages/ProcessPage'
import ArDashboardPage from './pages/ArDashboardPage'
import ArDevicesPage from './pages/ArDevicesPage'
import ArInspectPage from './pages/ArInspectPage'
import PhotoInspectPage from './pages/PhotoInspectPage'
import { AR_MARKER_ENABLED } from './features'
import { useAuth } from './auth/AuthContext'
import LoginPage from './pages/LoginPage'
import UsersPage from './pages/UsersPage'

/** 需要登入的頁面；切換資料集（線別）時以 key 重新掛載，各頁自然重抓資料 */
function Protected({ children, admin = false }: { children: ReactNode; admin?: boolean }) {
  const { user, isAdmin, dataset } = useAuth()
  const location = useLocation()
  if (user === undefined) return <div className="p-10 text-center text-sm text-slate-500">載入中…</div>
  if (user === null) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  if (admin && !isAdmin) return <Navigate to="/quality" replace />
  return <div key={dataset ?? 'none'}>{children}</div>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Navigate to="/quality" replace />} />
      <Route path="/admin/users" element={<Protected admin><UsersPage /></Protected>} />
      <Route path="/quality" element={<Protected><QualityPage /></Protected>} />
      <Route path="/complaints" element={<Protected><ComplaintsPage /></Protected>} />
      <Route path="/process" element={<Protected><ProcessPage /></Protected>} />

      <Route path="/ar/dashboard" element={<Protected><ArDashboardPage /></Protected>} />
      {AR_MARKER_ENABLED && <Route path="/ar/devices" element={<Protected><ArDevicesPage /></Protected>} />}
      <Route path="/ar/photo" element={<Protected><PhotoInspectPage /></Protected>} />
      {/*
        AR 掃描頁刻意不套 AppShell：A-Frame 會以 position:fixed 蓋滿整個視窗，
        與頁首互相遮蓋（見 ar-integration-spec.md §2 / REQ-ROUTE-03）。
      */}
      {AR_MARKER_ENABLED && <Route path="/ar/inspect" element={<Protected><ArInspectPage /></Protected>} />}

      <Route path="*" element={<Navigate to="/quality" replace />} />
    </Routes>
  )
}
