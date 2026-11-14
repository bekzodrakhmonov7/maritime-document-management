import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react'
import { supabase } from '../lib/supabase'
import { apiFetch } from '../lib/api'
import type { Session, User } from '@supabase/supabase-js'

interface AuthUser {
  sub: string
  email: string
  role: string
  is_approved: boolean
}

interface AuthContextValue {
  user: User | null
  session: Session | null
  role: string | null
  /** false while an administrator has not yet approved the account (FR-01) */
  isApproved: boolean
  loading: boolean
  signIn: (email: string, password: string) => Promise<{ error?: Error }>
  signUp: (
    email: string,
    password: string,
    fullName: string,
  ) => Promise<{ error?: Error; needsEmailConfirmation?: boolean }>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [session, setSession] = useState<Session | null>(null)
  const [role, setRole] = useState<string | null>(null)
  const [isApproved, setIsApproved] = useState(false)
  const [loading, setLoading] = useState(true)

  const fetchRole = useCallback(async () => {
    try {
      const data = await apiFetch('/auth/me') as AuthUser
      setRole(data.role)
      setIsApproved(data.is_approved)
    } catch {
      setRole(null)
      setIsApproved(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    supabase.auth.getSession().then(async ({ data }) => {
      if (cancelled) return
      setSession(data.session)
      setUser(data.session?.user ?? null)
      if (data.session) {
        await fetchRole()
      }
      if (!cancelled) {
        setLoading(false)
      }
    })

    const { data: listener } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s)
      setUser(s?.user ?? null)
      if (s) {
        fetchRole()
      } else {
        setRole(null)
      }
    })

    return () => {
      cancelled = true
      listener.subscription.unsubscribe()
    }
  }, [fetchRole])

  const signIn = async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    return { error: error ?? undefined }
  }

  const signUp = async (
    email: string,
    password: string,
    fullName: string,
  ) => {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { full_name: fullName },
      },
    })
    if (error) {
      return { error: error as Error }
    }
    const needsEmailConfirmation = !data.session
    return { needsEmailConfirmation }
  }

  const signOut = async () => {
    await supabase.auth.signOut()
    setRole(null)
    setIsApproved(false)
  }

  return (
    <AuthContext.Provider value={{ user, session, role, isApproved, loading, signIn, signUp, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}