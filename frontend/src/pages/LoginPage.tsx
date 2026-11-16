import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { Anchor, Loader2, AlertCircle } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { CodeStep } from '../components/auth/CodeStep'
import { ErrorNote } from '../components/ErrorNote'

/** Sign in: e-mail, then the Sign-in Code e-mailed to it (ADR-0004). Never
 * creates an Account, and answers every e-mail the same way. */
export function LoginPage() {
  const { requestCode, verifyCode, user, loading: authLoading, switchedOff } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!authLoading && user) {
    return <Navigate to="/" replace />
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const typed = email.trim()
    if (!typed) {
      setError('Enter your e-mail.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      await requestCode(typed)
      setEmail(typed)
      setCodeSent(true)
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
          {codeSent ? (
            <CodeStep
              email={email}
              onVerify={async (code) => {
                await verifyCode(email, code)
                navigate('/')
              }}
              onResend={() => requestCode(email)}
              onChangeEmail={() => setCodeSent(false)}
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

              {error && <ErrorNote message={error} />}

              <div>
                <label
                  htmlFor="email"
                  className="mb-2 block text-sm font-medium text-navy-100"
                >
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
                  className="w-full rounded-lg border border-navy-700 bg-navy-950 px-4 py-2.5 text-navy-50 placeholder-navy-500 transition-colors focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50"
                  placeholder="you@company.com"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-navy-600 px-4 py-2.5 font-medium text-navy-50 transition-colors hover:bg-navy-500 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading && <Loader2 className="h-5 w-5 animate-spin" />}
                {loading ? 'Sending code...' : 'Send me a code'}
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
