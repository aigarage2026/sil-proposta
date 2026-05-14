import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import AuthLayout from '@/layouts/AuthLayout'
import AppLayout from '@/layouts/AppLayout'
import LoginPage from '@/pages/LoginPage'
import ProposalList from '@/pages/ProposalList'
import IntakeForm from '@/pages/IntakeForm'
import GenerationView from '@/pages/GenerationView'
import ProposalDetail from '@/pages/ProposalDetail'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="flex items-center justify-center h-screen"><div className="animate-spin w-8 h-8 border-3 border-brand border-t-transparent rounded-full" /></div>
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
      </Route>
      <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
        <Route path="/" element={<Navigate to="/proposals" replace />} />
        <Route path="/proposals" element={<ProposalList />} />
        <Route path="/proposals/new" element={<IntakeForm />} />
        <Route path="/proposals/:id" element={<ProposalDetail />} />
        <Route path="/proposals/:id/generate" element={<GenerationView />} />
      </Route>
    </Routes>
  )
}
