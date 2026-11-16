import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Anchor, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { CodeStep } from '../components/auth/CodeStep'
import { ErrorNote } from '../components/ErrorNote'

const INPUT_CLASS =
  'w-full rounded-lg border border-navy-700 bg-navy-950 px-4 py-2.5 text-navy-50 placeholder-navy-500 transition-colors focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50'

/** Sign in: e-mail and password, then the Sign-in Code e-mailed to the
 * address (ADR-0005). Never creates an Account. */
export function LoginPage() {
  const { signIn, resendCode, verifyCode, user, loading: authLoading, switchedOff } = useAuth()
  const navigate = useNavigate()
  // Set by the Forgot password page once a new password is saved.
  const notice = (useLocation().state as { notice?: string } | null)?.notice ?? null

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [challenge, setChallenge] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!authLoading && user) {
    return <Navigate to="/" replace />
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const typed = email.trim()
    if (!typed || !password) {
      setError('Enter your e-mail and password.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      const issued = await signIn(typed, password)
      setEmail(typed)
      setPassword('')
      setChallenge(issued)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-navy-950 px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-navy-800 ring-1 ring-navy-700">
            <Anchor className="h-8 w-8 text-navy-200" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-navy-50">
            Maritime Crew Monitor
          </h1>
          <p className="mt-2 text-sm text-navy-400">
            Sign in to monitor crew document expiry
          </p>
        </div>

        <div className="rounded-xl border border-navy-800 bg-navy-900 p-8 shadow-2xl">
          {challenge ? (
            <CodeStep
              email={email}
              onVerify={async (code) => {
                await verifyCode(email, challenge, code)
                navigate('/')
              }}
              onResend={() => resendCode(challenge)}
              onBack={() => setChallenge(null)}
              onExpired={(message) => {
                setChallenge(null)
                setError(message)
              }}
            />
          ) : (
            <form onSubmit={handleSubmit} className="space-y-6" noValidate>
              {switchedOff && !error && (
                <div
                  role="alert"
                  className="flex items-start gap-3 rounded-lg border border-status-expired/40 bg-status-expired-bg/10 p-4"
                >
                  <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-status-expired" />
                  <p className="text-sm text-status-expired">
                    Your account has been switched off by an administrator, so you were signed out.
                  </p>
                </div>
              )}

              {notice && !error && (
                <div
                  role="status"
                  className="flex items-start gap-3 rounded-lg border border-navy-700 bg-navy-950 p-4"
                >
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-navy-300" aria-hidden="true" />
                  <p className="text-sm text-navy-200">{notice}</p>
                </div>
              )}

              {error && <ErrorNote message={error} />}

              <div>
                <label htmlFor="email" className="mb-2 block text-sm font-medium text-navy-100">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="username"
                  required
                  autoFocus
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={loading}
                  aria-required="true"
                  aria-invalid={error ? true : undefined}
                  className={INPUT_CLASS}
                  placeholder="you@company.com"
                />
              </div>

              <div>
                <div className="mb-2 flex items-baseline justify-between gap-3">
                  <label htmlFor="password" className="block text-sm font-medium text-navy-100">
                    Password
                  </label>
                  <Link
                    to="/forgot-password"
                    className="rounded text-sm font-medium text-navy-300 transition-colors hover:text-navy-50 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
                  >
                    Forgot password?
                  </Link>
                </div>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  maxLength={72}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={loading}
                  aria-required="true"
                  aria-invalid={error ? true : undefined}
                  className={INPUT_CLASS}
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-navy-600 px-4 py-2.5 font-medium text-navy-50 transition-colors hover:bg-navy-500 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading && <Loader2 className="h-5 w-5 animate-spin" />}
                {loading ? 'Signing in...' : 'Sign in'}
              </button>
            </form>
          )}
        </div>

        <p className="mt-6 text-center text-sm text-navy-400">
          Don't have an account?{' '}
          <Link
            to="/register"
            className="font-medium text-navy-200 transition-colors hover:text-navy-50 focus:outline-none focus:ring-2 focus:ring-navy-400/40 rounded"
          >
            Register
          </Link>
        </p>

        <p className="mt-3 text-center text-xs text-navy-500">
          Maritime Crew Document Expiry Monitoring System
        </p>
      </div>
    </div>
  )
}
