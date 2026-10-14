import { Navigate, Route, Routes } from 'react-router-dom'

import QualityPage from './pages/QualityPage'
import ComplaintsPage from './pages/ComplaintsPage'
import ProcessPage from './pages/ProcessPage'
import ArDashboardPage from './pages/ArDashboardPage'
import ArDevicesPage from './pages/ArDevicesPage'
import ArInspectPage from './pages/ArInspectPage'
import PhotoInspectPage from './pages/PhotoInspectPage'
import { AR_MARKER_ENABLED } from './features'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/quality" replace />} />
      <Route path="/quality" element={<QualityPage />} />
      <Route path="/complaints" element={<ComplaintsPage />} />
      <Route path="/process" element={<ProcessPage />} />

      <Route path="/ar/dashboard" element={<ArDashboardPage />} />
      {AR_MARKER_ENABLED && <Route path="/ar/devices" element={<ArDevicesPage />} />}
      <Route path="/ar/photo" element={<PhotoInspectPage />} />
      {/*
        AR 掃描頁刻意不套 AppShell：A-Frame 會以 position:fixed 蓋滿整個視窗，
        與頁首互相遮蓋（見 ar-integration-spec.md §2 / REQ-ROUTE-03）。
      */}
      {AR_MARKER_ENABLED && <Route path="/ar/inspect" element={<ArInspectPage />} />}

      <Route path="*" element={<Navigate to="/quality" replace />} />
    </Routes>
  )
}
