import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import api from '@/lib/api'

interface User {
  id: string
  email: string
  full_name: string
  role: string
  tenant_id: string
  is_platform_admin: boolean
  language: string
}

interface AuthCtx {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthCtx>({} as AuthCtx)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('sp_token')
    if (!token) { setLoading(false); return }
    api.get('/auth/me')
      .then((r) => setUser(r.data))
      .catch(() => { localStorage.removeItem('sp_token') })
      .finally(() => setLoading(false))
  }, [])

  const login = async (email: string, password: string) => {
    const r = await api.post('/auth/login', { email, password })
    localStorage.setItem('sp_token', r.data.access_token)
    localStorage.setItem('sp_refresh', r.data.refresh_token)
    const me = await api.get('/auth/me')
    setUser(me.data)
  }

  const logout = () => {
    localStorage.removeItem('sp_token')
    localStorage.removeItem('sp_refresh')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
