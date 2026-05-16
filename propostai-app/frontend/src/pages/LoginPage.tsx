import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { useTranslation } from 'react-i18next'

export default function LoginPage() {
  const { login } = useAuth()
  const { t } = useTranslation()
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
      nav('/proposals')
    } catch {
      setError('Credenciais invalidas')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="bg-white/10 backdrop-blur border border-white/10 rounded-2xl p-8 space-y-5">
      {error && <div className="text-red-400 text-sm text-center bg-red-500/10 rounded-lg py-2">{error}</div>}
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1.5">{t('auth.email')}</label>
        <input type="email" value={email} onChange={e => setEmail(e.target.value)} required
          className="w-full px-4 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder-slate-500 outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
          placeholder="seu.email@empresa.com.br" />
      </div>
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1.5">{t('auth.password')}</label>
        <input type="password" value={password} onChange={e => setPassword(e.target.value)} required
          className="w-full px-4 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder-slate-500 outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
          placeholder="********" />
      </div>
      <button type="submit" disabled={loading}
        className="w-full py-2.5 rounded-lg bg-brand text-white font-semibold text-sm hover:bg-brand-dark disabled:opacity-50 transition-all">
        {loading ? '...' : t('auth.login')}
      </button>
    </form>
  )
}
