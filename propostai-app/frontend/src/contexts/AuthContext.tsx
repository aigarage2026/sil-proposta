// AuthContext aligned with v3 §6.3 JWT claims (products[], roles{by_product}).
// Compatible with the contract `agn-ui.AuthContext` is expected to expose
// when Onda 6 migrates this into the Portal SPA — the consumer-facing shape
// (`user`, `loading`, `login`, `logout`, `hasProduct`, `roleFor`) is what
// agn-ui will eventually re-export, so call sites don't need to change.
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

import api from '@/lib/api'

interface JwtPayload {
  sub: string
  email?: string
  tenant_id?: string
  products?: string[]
  roles?: Record<string, string>
  is_platform_admin?: boolean
  exp?: number
}

interface MeResponse {
  id: string
  email: string
  full_name: string
  role: string
  tenant_id: string
  is_platform_admin: boolean
  language: string
}

export interface AuthUser extends MeResponse {
  /** Products the tenant has access to (from JWT.products[]). */
  products: string[]
  /** Per-product role map (from JWT.roles{by_product}). */
  rolesByProduct: Record<string, string>
}

interface AuthCtx {
  user: AuthUser | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  /** True when the JWT lists `productSlug` in its products[] claim. */
  hasProduct: (productSlug: string) => boolean
  /** Role of the authenticated user inside `productSlug`, or null. */
  roleFor: (productSlug: string) => string | null
}

const AuthContext = createContext<AuthCtx>({} as AuthCtx)

const TOKEN_KEY = 'sp_token'
const REFRESH_KEY = 'sp_refresh'

function decodeJwt(token: string): JwtPayload | null {
  try {
    const [, payload] = token.split('.')
    if (!payload) return null
    const b64 = payload.replace(/-/g, '+').replace(/_/g, '/')
    const json = atob(b64.padEnd(b64.length + ((4 - (b64.length % 4)) % 4), '='))
    return JSON.parse(json) as JwtPayload
  } catch {
    return null
  }
}

function mergeUser(me: MeResponse, claims: JwtPayload | null): AuthUser {
  return {
    ...me,
    products: claims?.products ?? ['propostai'],
    rolesByProduct: claims?.roles ?? { 'propostai': me.role },
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) {
      setLoading(false)
      return
    }
    api
      .get('/auth/me')
      .then((r) => setUser(mergeUser(r.data as MeResponse, decodeJwt(token))))
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY)
        localStorage.removeItem(REFRESH_KEY)
      })
      .finally(() => setLoading(false))
  }, [])

  const login = async (email: string, password: string) => {
    const r = await api.post('/auth/login', { email, password })
    const token = r.data.access_token as string
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(REFRESH_KEY, r.data.refresh_token)
    const me = await api.get('/auth/me')
    setUser(mergeUser(me.data as MeResponse, decodeJwt(token)))
  }

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
    setUser(null)
  }

  const hasProduct = (slug: string) => Boolean(user && user.products.includes(slug))
  const roleFor = (slug: string) => (user ? user.rolesByProduct[slug] ?? null : null)

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, hasProduct, roleFor }}>
      {children}
    </AuthContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthContext)
