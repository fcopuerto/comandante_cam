import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { Toaster } from '@/components/ui/toaster'
import { useAuthStore } from '@/store/authStore'
import Layout from '@/components/shared/Layout'
import ErrorBoundary from '@/components/shared/ErrorBoundary'
import NotificationToast from '@/components/shared/NotificationToast'

const Login = lazy(() => import('@/pages/Login'))
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const LiveView = lazy(() => import('@/pages/LiveView'))
const Cameras = lazy(() => import('@/pages/Cameras'))
const CameraDetail = lazy(() => import('@/pages/CameraDetail'))
const Recordings = lazy(() => import('@/pages/Recordings'))
const Alerts = lazy(() => import('@/pages/Alerts'))
const Users = lazy(() => import('@/pages/Users'))
const AuditLog = lazy(() => import('@/pages/AuditLog'))
const Storage = lazy(() => import('@/pages/Storage'))
const Settings = lazy(() => import('@/pages/Settings'))
const AddCamera = lazy(() => import('@/pages/AddCamera'))
const EquipmentPage = lazy(() => import('@/pages/Equipment'))
const FloorPlanPage = lazy(() => import('@/pages/FloorPlan'))
const NotFound = lazy(() => import('@/pages/NotFound'))

function Placeholder({ name }: { name: string }) {
  return (
    <div className="flex items-center justify-center h-64 text-muted-foreground">
      {name} — coming soon
    </div>
  )
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const location = useLocation()
  if (!isAuthenticated) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  return <>{children}</>
}

function PageLoader() {
  return <div className="p-6"><Skeleton className="h-64 w-full" /></div>
}

export default function App() {
  return (
    <BrowserRouter>
      <NotificationToast />
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
            <Route index element={<ErrorBoundary><Dashboard /></ErrorBoundary>} />
            <Route path="live" element={<ErrorBoundary><LiveView /></ErrorBoundary>} />
            <Route path="recordings" element={<ErrorBoundary><Recordings /></ErrorBoundary>} />
            <Route path="alerts" element={<ErrorBoundary><Alerts /></ErrorBoundary>} />
            <Route path="cameras" element={<ErrorBoundary><Cameras /></ErrorBoundary>} />
            <Route path="cameras/new" element={<ErrorBoundary><AddCamera /></ErrorBoundary>} />
            <Route path="cameras/:id" element={<ErrorBoundary><CameraDetail /></ErrorBoundary>} />
            <Route path="users" element={<ErrorBoundary><Users /></ErrorBoundary>} />
            <Route path="audit" element={<ErrorBoundary><AuditLog /></ErrorBoundary>} />
            <Route path="storage" element={<ErrorBoundary><Storage /></ErrorBoundary>} />
            <Route path="settings" element={<ErrorBoundary><Settings /></ErrorBoundary>} />
            <Route path="equipment" element={<ErrorBoundary><EquipmentPage /></ErrorBoundary>} />
            <Route path="floor-plan" element={<ErrorBoundary><FloorPlanPage /></ErrorBoundary>} />
            <Route path="profile" element={<Placeholder name="Profile" />} />
            <Route path="sessions" element={<Placeholder name="Sessions" />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </Suspense>
      <Toaster />
    </BrowserRouter>
  )
}
