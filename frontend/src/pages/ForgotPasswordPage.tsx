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
  'w-full rounded-lg border border-navy-700 bg-navy-950 px-4 py-2.5 text-navy-50 placeholder-navy-500 transition-colors focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50'

const BUTTON_CLASS =
  'flex w-full items-center justify-center gap-2 rounded-lg bg-navy-600 px-4 py-2.5 font-medium text-navy-50 transition-colors hover:bg-navy-500 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:cursor-not-allowed disabled:opacity-50'

/** Forgot password: e-mail, then the code e-mailed to it and a new password
 * (ADR-0005). Every session of the Account ends; the person then signs in
 * with the new password and a Sign-in Code as usual. */
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
    <div className="flex min-h-screen items-center justify-center bg-navy-950 px-4 py-8">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-navy-800 ring-1 ring-navy-700">
            <Anchor className="h-8 w-8 text-navy-200" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-navy-50">Set a new password</h1>
          <p className="mt-2 text-sm text-navy-400">
            We'll e-mail you a code to prove the address is yours
          </p>
        </div>

        <div className="rounded-xl border border-navy-800 bg-navy-900 p-8 shadow-2xl">
          {codeSent ? (
            <form onSubmit={handleReset} className="space-y-6" noValidate>
              <div
                role="status"
                className="flex items-start gap-3 rounded-lg border border-navy-700 bg-navy-950 p-4"
              >
                <MailCheck className="mt-0.5 h-5 w-5 shrink-0 text-navy-300" aria-hidden="true" />
                <p className="text-sm text-navy-200">
                  If an Account exists for <strong className="text-navy-50">{email}</strong>, we've
                  sent it a code. It is valid for 10 minutes.
                </p>
              </div>

              {error && <ErrorNote message={error} />}

              <div>
                <label htmlFor="code" className="mb-2 block text-sm font-medium text-navy-100">
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
                  className={`${INPUT_CLASS} text-center font-mono text-2xl tracking-[0.5em] placeholder-navy-600`}
                  placeholder="000000"
                />
              </div>

              <div>
                <label htmlFor="password" className="mb-2 block text-sm font-medium text-navy-100">
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
                <p id="password-hint" className="mt-1.5 text-xs text-navy-400">
                  At least {MIN_PASSWORD_LENGTH} characters, and not a common or breached password.
                </p>
              </div>

              <div>
                <label htmlFor="repeated" className="mb-2 block text-sm font-medium text-navy-100">
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
                className="flex items-center gap-1 rounded text-sm font-medium text-navy-300 transition-colors hover:text-navy-50 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50"
              >
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                Back
              </button>
            </form>
          ) : (
            <form onSubmit={handleEmail} className="space-y-6" noValidate>
              {error && <ErrorNote message={error} />}

              <div>
                <label htmlFor="email" className="mb-2 block text-sm font-medium text-navy-100">
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

        <p className="mt-6 text-center text-sm text-navy-400">
          Remembered it?{' '}
          <Link
            to="/login"
            className="rounded font-medium text-navy-200 transition-colors hover:text-navy-50 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
          >
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
