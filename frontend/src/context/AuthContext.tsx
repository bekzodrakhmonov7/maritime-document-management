import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { apiFetch, apiSend, onAccountSwitchedOff, onSessionRefused, refreshSession } from '../lib/api'
import {
  forgetLegacySessions,
  onSessionChange,
  readSession,
  secondsUntilRefresh,
  sessionFromTokens,
  writeSession,
  type Session,
  type SessionTokens,
  type User,
} from '../lib/session'
import type { AccountStatus, Me, UserRole } from '../types'
import type { SignInStep } from '../lib/signInCode'

const SWITCHED_OFF_KEY = 'account-switched-off'

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
  /** Sign in, step 1: check the password; returns the authenticator step
   * (its code, or enrolling the app first). */
  signIn: (email: string, password: string) => Promise<SignInStep>
  /** Register, step 1: create the pending Account; e-mails a code, returns that step. */
  register: (email: string, fullName: string, password: string) => Promise<SignInStep>
  /** E-mail a new code for Register's e-mailed step. */
  resendCode: (challenge: string) => Promise<void>
  /** Check a code. Returns the next step (enrolling after Register's
   * e-mailed code), or null once the session has started; throws the API's refusal. */
  verifyCode: (email: string, challenge: string, code: string) => Promise<SignInStep | null>
  /** Forgot password: e-mail a code for setting a new one. */
  requestPasswordReset: (email: string) => Promise<void>
  /** Set a new password with that code; every session of the Account ends. */
  /** `totp`: the authenticator's code, when the Account has one (ADR 0007). */
  resetPassword: (email: string, code: string, password: string, totp?: string) => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => {
    forgetLegacySessions()
    return readSession()
  })
  const user: User | null = session?.user ?? null
  const [role, setRole] = useState<UserRole | null>(null)
  const [status, setStatus] = useState<AccountStatus | null>(null)
  // Until /api/me has answered for a kept session.
  const [loading, setLoading] = useState(() => readSession() !== null)
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

  // Only this browser forgets the session; Supabase Auth is never called
  // from here (SR-01).
  const endSession = useCallback(async () => {
    writeSession(null)
    setRole(null)
    setStatus(null)
  }, [])

  const signOut = useCallback(async () => {
    // Records *logout* in the Audit Log and ends the session at Supabase
    // Auth. Best effort: signing out must work even when the API can't be
    // reached.
    try {
      await apiSend('POST', '/api/auth/logout')
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

  // A session that skipped a sign-in step is refused by the API (ADR 0005,
  // ADR 0007): end it, so the person signs in again with password and code.
  useEffect(() => onSessionRefused(() => void endSession()), [endSession])

  useEffect(() => {
    let cancelled = false
    const stored = readSession()
    if (stored) {
      // /api/me renews an expired session first (lib/api.ts).
      void apiFetch<Me>('/api/me')
        .then(
          (me) => {
            if (cancelled) return
            setRole(me.role)
            setStatus(me.status)
          },
          () => undefined,
        )
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }

    let userId = stored?.user.id ?? null
    const stop = onSessionChange((s) => {
      setSession(s)
      if (!s) {
        setRole(null)
        setStatus(null)
      } else if (s.user.id !== userId) {
        // A new sign-in: wait for /api/me before routing on status, or
        // ProtectedRoute briefly shows "can't be loaded" (status still null).
        setLoading(true)
        void fetchAccount().finally(() => setLoading(false))
      }
      userId = s?.user.id ?? null
    })

    return () => {
      cancelled = true
      stop()
    }
  }, [fetchAccount])

  // Renew the session shortly before its access token expires.
  useEffect(() => {
    if (!session) return
    const timer = setTimeout(
      () => void refreshSession(),
      secondsUntilRefresh(session) * 1000,
    )
    return () => clearTimeout(timer)
  }, [session])

  const clearSwitchedOff = useCallback(() => {
    sessionStorage.removeItem(SWITCHED_OFF_KEY)
    setSwitchedOff(false)
  }, [])

  // Every sign-in step goes through the API's sign-in proxy (ADR 0005,
  // ADR 0007): it records failed attempts (FR-22) and lets only sessions that
  // passed both the password and the authenticator code into the API.
  const post = <T,>(path: string, body: unknown) => apiSend<T>('POST', path, body)

  const signIn = (email: string, password: string) =>
    post<SignInStep>('/api/auth/login', { email, password })

  const register = (email: string, fullName: string, password: string) =>
    post<SignInStep>('/api/auth/register', { email, full_name: fullName, password })

  const resendCode = async (challenge: string) => {
    await post('/api/auth/code', { challenge })
  }

  // The session the proxy returns is kept in this browser; the existing
  // routing then sends a pending Account to the waiting page (FR-01).
  const verifyCode = async (email: string, challenge: string, code: string) => {
    const answer = await post<SessionTokens | SignInStep>('/api/auth/verify', {
      email,
      challenge,
      code,
    })
    if (!('access_token' in answer)) return answer
    const started = sessionFromTokens(answer)
    if (!started) throw new Error('Sign-in failed. Try again.')
    clearSwitchedOff()
    writeSession(started)
    return null
  }

  const requestPasswordReset = async (email: string) => {
    await post('/api/auth/password/forgot', { email })
  }

  const resetPassword = async (email: string, code: string, password: string, totp?: string) => {
    await post('/api/auth/password/reset', totp ? { email, code, password, totp } : { email, code, password })
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
        register,
        resendCode,
        verifyCode,
        requestPasswordReset,
        resetPassword,
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
