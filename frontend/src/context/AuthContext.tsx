import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { supabase } from '../lib/supabase'
import { apiFetch, onAccountSwitchedOff } from '../lib/api'
import type { Session, User } from '@supabase/supabase-js'
import type { AccountStatus, Me, UserRole } from '../types'

const SWITCHED_OFF_KEY = 'account-switched-off'

/** The part of the sign-in proxy's response that `setSession` needs. */
interface SessionTokens {
  access_token: string
  refresh_token: string
}

interface AuthContextValue {
  user: User | null
  session: Session | null
  /** The Account's role; null while pending (FR-01). */
  role: UserRole | null
  /** null until /api/me has answered (or when it failed). */
  status: AccountStatus | null
  loading: boolean
  /** Set when the app signed out because the account was switched off. */
  switchedOff: boolean
  clearSwitchedOff: () => void
  refreshAccount: () => Promise<void>
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
  const [role, setRole] = useState<UserRole | null>(null)
  const [status, setStatus] = useState<AccountStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [switchedOff, setSwitchedOff] = useState(
    () => sessionStorage.getItem(SWITCHED_OFF_KEY) === '1',
  )

  const fetchAccount = useCallback(async () => {
    try {
      const me = await apiFetch<Me>('/api/me')
      setRole(me.role)
      setStatus(me.status)
    } catch {
      setRole(null)
      setStatus(null)
    }
  }, [])

  const endSession = useCallback(async () => {
    await supabase.auth.signOut()
    setRole(null)
    setStatus(null)
  }, [])

  const signOut = useCallback(async () => {
    // Records *logout* in the Audit Log. Best effort: signing out must work
    // even when the API can't be reached.
    try {
      await apiFetch('/api/auth/logout', { method: 'POST' })
    } catch {
      // ignored
    }
    await endSession()
  }, [endSession])

  // FR-02: a switched-off account is refused on its next request; sign out
  // and tell the person why. The API would refuse its logout call too, so
  // only the local session is ended.
  useEffect(
    () =>
      onAccountSwitchedOff(() => {
        sessionStorage.setItem(SWITCHED_OFF_KEY, '1')
        setSwitchedOff(true)
        void endSession()
      }),
    [endSession],
  )

  useEffect(() => {
    let cancelled = false
    supabase.auth.getSession().then(async ({ data }) => {
      if (cancelled) return
      setSession(data.session)
      setUser(data.session?.user ?? null)
      if (data.session) {
        await fetchAccount()
      }
      if (!cancelled) {
        setLoading(false)
      }
    })

    const { data: listener } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s)
      setUser(s?.user ?? null)
      if (s) {
        void fetchAccount()
      } else {
        setRole(null)
        setStatus(null)
      }
    })

    return () => {
      cancelled = true
      listener.subscription.unsubscribe()
    }
  }, [fetchAccount])

  const clearSwitchedOff = useCallback(() => {
    sessionStorage.removeItem(SWITCHED_OFF_KEY)
    setSwitchedOff(false)
  }, [])

  // Sign-in goes through the API so failed attempts reach the Audit Log
  // (T7); the session it returns is then handed to Supabase.
  const signIn = async (email: string, password: string) => {
    let tokens: SessionTokens
    try {
      tokens = await apiFetch<SessionTokens>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      })
    } catch (err) {
      return { error: err instanceof Error ? err : new Error('Sign-in failed.') }
    }
    const { error } = await supabase.auth.setSession({
      access_token: tokens.access_token,
      refresh_token: tokens.refresh_token,
    })
    if (!error) clearSwitchedOff()
    return { error: error ?? undefined }
  }

  const signUp = async (email: string, password: string, fullName: string) => {
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

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        role,
        status,
        loading,
        switchedOff,
        clearSwitchedOff,
        refreshAccount: fetchAccount,
        signIn,
        signUp,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
