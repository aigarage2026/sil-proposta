import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { useTranslation } from 'react-i18next'

export default function AppLayout() {
  const { user, logout } = useAuth()
  const { t } = useTranslation()
  const nav = useNavigate()

  const link = (to: string, label: string) => (
    <NavLink to={to} className={({ isActive }) =>
      `px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all ${isActive ? 'bg-brand-light text-brand font-semibold' : 'text-gray-500 hover:bg-gray-100'}`
    }>{label}</NavLink>
  )

  return (
    <div className="min-h-screen flex flex-col">
      {/* Topbar */}
      <header className="sticky top-0 z-50 flex items-center justify-between px-6 h-14 bg-white/97 backdrop-blur border-b border-gray-200 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand to-indigo-500 flex items-center justify-center text-white text-xs font-extrabold">S</div>
          <div>
            <div className="text-sm font-bold text-surface-dark">Sil-Proposta</div>
            <div className="text-[10px] text-gray-400">v1.0 · Cast Group</div>
          </div>
        </div>
        <nav className="flex gap-1">
          {link('/proposals', t('nav.proposals'))}
          {link('/proposals/new', t('nav.new'))}
        </nav>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400 font-mono">{user?.email}</span>
          <button onClick={() => { logout(); nav('/login') }} className="btn-ghost text-xs">{t('auth.logout')}</button>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 p-8 max-w-6xl mx-auto w-full">
        <Outlet />
      </main>
    </div>
  )
}
