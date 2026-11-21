import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { Anchor, ArrowLeft, KeyRound, Loader2, MailCheck } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { ErrorNote } from '../components/ErrorNote'
import { ApiError } from '../lib/api'
import {
  CODE_LENGTH,
  MAX_PASSWORD_LENGTH,
  MIN_PASSWORD_LENGTH,
  codeErrorMessage,
  isCompleteCode,
  normaliseCode,
  passwordProblem,
} from '../lib/signInCode'

const INPUT_CLASS =
  'w-full rounded-md border border-line-strong bg-canvas px-4 py-2.5 text-ink placeholder-ink-faint transition-colors focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-50'

const BUTTON_CLASS =
  'flex w-full items-center justify-center gap-2 rounded-md bg-accent px-4 py-2.5 font-medium text-on-accent transition-colors hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:cursor-not-allowed disabled:opacity-50'

/** Forgot password: e-mail, then the code e-mailed to it and a new password
 * (ADR 0005). Every session of the Account ends; the person then signs in
 * with the new password and their authenticator code as usual (ADR 0007). */
export function ForgotPasswordPage() {
  const { requestPasswordReset, resetPassword, user, loading: authLoading } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [repeated, setRepeated] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!authLoading && user) {
    return <Navigate to="/" replace />
  }

  const handleEmail = async (e: FormEvent) => {
    e.preventDefault()
    const typed = email.trim()
    if (!typed) {
      setError('Enter your e-mail.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      await requestPasswordReset(typed)
      setEmail(typed)
      setCodeSent(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleReset = async (e: FormEvent) => {
    e.preventDefault()
    if (!isCompleteCode(code)) {
      setError(`Enter the ${CODE_LENGTH}-digit code from the e-mail.`)
      return
    }
    const problem = passwordProblem(password, repeated)
    if (problem) {
      setError(problem)
      return
    }
    setError(null)
    setLoading(true)
    try {
      await resetPassword(email, code, password)
      navigate('/login', {
        replace: true,
        state: { notice: 'Your password has been changed. Sign in with it now.' },
      })
    } catch (err) {
      setError(
        err instanceof ApiError
          ? codeErrorMessage(err)
          : err instanceof Error
            ? err.message
            : 'Something went wrong. Try again.',
      )
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4 py-8">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-surface-active ring-1 ring-line">
            <Anchor className="h-8 w-8 text-ink-muted" />
          </div>
          <h1 className="text-xl font-medium tracking-tight text-ink">Set a new password</h1>
          <p className="mt-2 text-sm text-ink-faint">
            We'll e-mail you a code to prove the address is yours
          </p>
        </div>

        <div className="rounded-md border border-line bg-canvas p-8">
          {codeSent ? (
            <form onSubmit={handleReset} className="space-y-6" noValidate>
              <div
                role="status"
                className="flex items-start gap-3 rounded-md border border-line-strong bg-canvas p-4"
              >
                <MailCheck className="mt-0.5 h-5 w-5 shrink-0 text-ink-muted" aria-hidden="true" />
                <p className="text-sm text-ink-muted">
                  If an Account exists for <strong className="text-ink">{email}</strong>, we've
                  sent it a code. It is valid for 10 minutes.
                </p>
              </div>

              {error && <ErrorNote message={error} />}

              <div>
                <label htmlFor="code" className="mb-2 block text-sm font-medium text-ink">
                  Code
                </label>
                <input
                  id="code"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]*"
                  maxLength={CODE_LENGTH}
                  required
                  autoFocus
                  value={code}
                  onChange={(e) => setCode(normaliseCode(e.target.value))}
                  disabled={loading}
                  aria-required="true"
                  className={`${INPUT_CLASS} text-center font-mono text-xl tracking-[0.5em] placeholder-ink-faint`}
                  placeholder="000000"
                />
              </div>

              <div>
                <label htmlFor="password" className="mb-2 block text-sm font-medium text-ink">
                  New password
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={MIN_PASSWORD_LENGTH}
                  maxLength={MAX_PASSWORD_LENGTH}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={loading}
                  aria-required="true"
                  aria-describedby="password-hint"
                  className={INPUT_CLASS}
                />
                <p id="password-hint" className="mt-1.5 text-xs text-ink-faint">
                  At least {MIN_PASSWORD_LENGTH} characters, and not a common or breached password.
                </p>
              </div>

              <div>
                <label htmlFor="repeated" className="mb-2 block text-sm font-medium text-ink">
                  Repeat new password
                </label>
                <input
                  id="repeated"
                  type="password"
                  autoComplete="new-password"
                  required
                  maxLength={MAX_PASSWORD_LENGTH}
                  value={repeated}
                  onChange={(e) => setRepeated(e.target.value)}
                  disabled={loading}
                  aria-required="true"
                  className={INPUT_CLASS}
                />
              </div>

              <button type="submit" disabled={loading} className={BUTTON_CLASS}>
                {loading ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <KeyRound className="h-5 w-5" aria-hidden="true" />
                )}
                {loading ? 'Saving...' : 'Save new password'}
              </button>

              <button
                type="button"
                onClick={() => {
                  setCodeSent(false)
                  setCode('')
                  setError(null)
                }}
                disabled={loading}
                className="flex items-center gap-1 rounded text-sm font-medium text-ink-muted transition-colors hover:text-ink focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-50"
              >
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                Back
              </button>
            </form>
          ) : (
            <form onSubmit={handleEmail} className="space-y-6" noValidate>
              {error && <ErrorNote message={error} />}

              <div>
                <label htmlFor="email" className="mb-2 block text-sm font-medium text-ink">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
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

              <button type="submit" disabled={loading} className={BUTTON_CLASS}>
                {loading && <Loader2 className="h-5 w-5 animate-spin" />}
                {loading ? 'Sending code...' : 'Send me a code'}
              </button>
            </form>
          )}
        </div>

        <p className="mt-6 text-center text-sm text-ink-faint">
          Remembered it?{' '}
          <Link
            to="/login"
            className="rounded font-medium text-ink-muted transition-colors hover:text-ink focus:outline-none focus:ring-2 focus:ring-accent/40"
          >
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
