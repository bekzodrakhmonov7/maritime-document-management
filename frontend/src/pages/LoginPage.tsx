import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Anchor, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { CodeStep } from '../components/auth/CodeStep'
import { ErrorNote } from '../components/ErrorNote'
import { signInErrorMessage, type SignInStep } from '../lib/signInCode'

const INPUT_CLASS =
  'w-full rounded-md border border-line-strong bg-canvas px-4 py-2.5 text-ink placeholder-ink-faint transition-colors focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-50'

/** Sign in: e-mail and password, then the code from the authenticator app,
 * enrolling the app at the first sign-in (ADR 0005, ADR 0007, SR-03). Never
 * creates an Account. */
export function LoginPage() {
  const { signIn, resendCode, verifyCode, user, loading: authLoading, switchedOff } = useAuth()
  const navigate = useNavigate()
  // Set by the Forgot password page once a new password is saved.
  const notice = (useLocation().state as { notice?: string } | null)?.notice ?? null

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [step, setStep] = useState<SignInStep | null>(null)
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
      setStep(issued)
    } catch (err) {
      setError(err instanceof Error ? signInErrorMessage(err) : 'Sign-in failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-surface-active ring-1 ring-line">
            <Anchor className="h-8 w-8 text-ink-muted" />
          </div>
          <h1 className="text-xl font-medium tracking-tight text-ink">
            Maritime Crew Monitor
          </h1>
          <p className="mt-2 text-sm text-ink-faint">
            Sign in to monitor crew document expiry
          </p>
        </div>

        <div className="rounded-md border border-line bg-canvas p-8">
          {step ? (
            <CodeStep
              key={step.challenge}
              email={email}
              step={step}
              onVerify={async (code) => {
                const next = await verifyCode(email, step.challenge, code)
                if (next) setStep(next)
                else navigate('/')
              }}
              onResend={() => resendCode(step.challenge)}
              onBack={() => setStep(null)}
              onExpired={(message) => {
                setStep(null)
                setError(message)
              }}
            />
          ) : (
            <form onSubmit={handleSubmit} className="space-y-6" noValidate>
              {switchedOff && !error && (
                <div
                  role="alert"
                  className="flex items-start gap-3 rounded-md border border-danger/40 p-4"
                >
                  <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-danger" />
                  <p className="text-sm text-danger">
                    Your account has been switched off by an administrator, so you were signed out.
                  </p>
                </div>
              )}

              {notice && !error && (
                <div
                  role="status"
                  className="flex items-start gap-3 rounded-md border border-line-strong bg-canvas p-4"
                >
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-ink-muted" aria-hidden="true" />
                  <p className="text-sm text-ink-muted">{notice}</p>
                </div>
              )}

              {error && <ErrorNote message={error} />}

              <div>
                <label htmlFor="email" className="mb-2 block text-sm font-medium text-ink">
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
                  <label htmlFor="password" className="block text-sm font-medium text-ink">
                    Password
                  </label>
                  <Link
                    to="/forgot-password"
                    className="rounded text-sm font-medium text-ink-muted transition-colors hover:text-ink focus:outline-none focus:ring-2 focus:ring-accent/40"
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
                className="flex w-full items-center justify-center gap-2 rounded-md bg-accent px-4 py-2.5 font-medium text-on-accent transition-colors hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading && <Loader2 className="h-5 w-5 animate-spin" />}
                {loading ? 'Signing in...' : 'Sign in'}
              </button>
            </form>
          )}
        </div>

        <p className="mt-6 text-center text-sm text-ink-faint">
          Don't have an account?{' '}
          <Link
            to="/register"
            className="font-medium text-ink-muted transition-colors hover:text-ink focus:outline-none focus:ring-2 focus:ring-accent/40 rounded"
          >
            Register
          </Link>
        </p>

        <p className="mt-3 text-center text-xs text-ink-faint">
          Maritime Crew Document Expiry Monitoring System
        </p>
      </div>
    </div>
  )
}
