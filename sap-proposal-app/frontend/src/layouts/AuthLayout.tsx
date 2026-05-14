import { Outlet } from 'react-router-dom'

export default function AuthLayout() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-brand-dark">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br from-brand to-indigo-500 text-white text-lg font-extrabold mb-3">S</div>
          <h1 className="text-2xl font-bold text-white">Sil-Proposta</h1>
          <p className="text-sm text-slate-400 mt-1">Plataforma SaaS — Cast Group</p>
        </div>
        <Outlet />
      </div>
    </div>
  )
}
