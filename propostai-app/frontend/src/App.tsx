import { Suspense, lazy } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'

import { useAuth } from '@/contexts/AuthContext'
import AppLayout from '@/layouts/AppLayout'
import AuthLayout from '@/layouts/AuthLayout'
import { propostaiRoutes } from '@/products/propostai/routes'

// LoginPage stays eager — it's the very first page on cold start.
import LoginPage from '@/pages/LoginPage'

const RouteFallback = lazy(() => import('@/components/RouteFallback'))

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin w-8 h-8 border-3 border-brand border-t-transparent rounded-full" />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route element={<AuthLayout />}>
          <Route path="/login" element={<LoginPage />} />
        </Route>
        <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
          {/* propostai product routes — see frontend/src/products/propostai/routes.tsx.
              The Portal SPA will mount this set under /propostai/* once that
              integration lands (Onda 6). Today it mounts at the SPA root. */}
          {propostaiRoutes.map((r) => (
            <Route
              key={r.path ?? '_index'}
              index={r.index}
              path={r.path}
              element={r.element}
            />
          ))}
        </Route>
      </Routes>
    </Suspense>
  )
}
