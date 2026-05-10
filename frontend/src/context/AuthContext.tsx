import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  useEffect,
} from 'react'
import { useNavigate } from 'react-router-dom'
import { setToken, setUnauthorizedHandler } from '../api/client'
import { login as apiLogin } from '../api/auth'
import type { JwtPayload, LoginRequest, UserRole } from '../types'

// ─── JWT HELPERS ─────────────────────────────────────────────

function parseJwt(token: string): JwtPayload | null {
  try {
    const base64Url = token.split('.')[1]
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    )
    return JSON.parse(jsonPayload) as JwtPayload
  } catch {
    return null
  }
}

function extractRole(payload: JwtPayload): UserRole {
  if (payload.role) return payload.role
  const groups = payload['cognito:groups'] ?? []
  if (groups.includes('admin')) return 'admin'
  if (groups.includes('analyst')) return 'analyst'
  return 'viewer'
}

// ─── TYPES ─────────────────────────────────────────────

interface AuthState {
  token: string | null
  role: UserRole | null
  userId: string | null
  email: string | null
}

interface AuthContextValue extends AuthState {
  isAuthenticated: boolean
  login: (credentials: LoginRequest) => Promise<void>
  logout: () => void
  canWrite: boolean
  isAdmin: boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

// ─── PROVIDER ─────────────────────────────────────────────

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate()

  const [authState, setAuthState] = useState<AuthState>({
    token: null,
    role: null,
    userId: null,
    email: null,
  })

  const [loading, setLoading] = useState(true)

  // ─── RESTORE SESSION ─────────────────────────────────────
  useEffect(() => {
    const savedToken = localStorage.getItem('token')

    if (savedToken) {
      const payload = parseJwt(savedToken)

      if (payload) {
        setAuthState({
          token: savedToken,
          role: extractRole(payload),
          userId: payload.sub,
          email: payload.email ?? null,
        })

        setToken(savedToken)
      } else {
        localStorage.removeItem('token')
      }
    }

    setLoading(false)
  }, [])

  // ─── GLOBAL 401 HANDLER ─────────────────────────────────
  useEffect(() => {
    setUnauthorizedHandler(() => {
      localStorage.removeItem('token')
      setAuthState({
        token: null,
        role: null,
        userId: null,
        email: null,
      })
      navigate('/login', { replace: true })
    })
  }, [navigate])

  // ─── LOGIN ───────────────────────────────────────────────
  const login = useCallback(
    async (credentials: LoginRequest) => {
      try {
        const response = await apiLogin(credentials)

        console.log("LOGIN RESPONSE:", response)

        const token =
          response.access_token ??
          response.id_token ??
          response.token

        if (!token) {
          throw new Error("No token received from backend")
        }

        const payload = parseJwt(token)

        if (!payload) {
          throw new Error("Invalid token format")
        }

        localStorage.setItem('token', token)
        setToken(token)

        setAuthState({
          token,
          role: extractRole(payload),
          userId: payload.sub,
          email: payload.email ?? null,
        })

        navigate('/dashboard', { replace: true })

      } catch (error) {
        console.error("LOGIN FAILED:", error)
        throw error
      }
    },
    [navigate]
  )

  // ─── LOGOUT ──────────────────────────────────────────────
  const logout = useCallback(() => {
    localStorage.removeItem('token')
    setToken(null)

    setAuthState({
      token: null,
      role: null,
      userId: null,
      email: null,
    })

    navigate('/login', { replace: true })
  }, [navigate])

  // ─── DERIVED STATE ───────────────────────────────────────
  const value = useMemo<AuthContextValue>(
    () => ({
      ...authState,
      isAuthenticated: !!authState.token,
      canWrite: authState.role === 'admin' || authState.role === 'analyst',
      isAdmin: authState.role === 'admin',
      login,
      logout,
    }),
    [authState, login, logout]
  )

  // ─── LOADING GUARD ───────────────────────────────────────
  if (loading) {
    return <div>Loading...</div>
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

// ─── HOOK ─────────────────────────────────────────────

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}