import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { Anchor, Loader2, UserPlus } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { CodeStep } from '../components/auth/CodeStep'
import { ErrorNote } from '../components/ErrorNote'

const INPUT_CLASS =
  'w-full rounded-lg border border-navy-700 bg-navy-950 px-4 py-2.5 text-navy-50 placeholder-navy-500 transition-colors focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50'

/** Register: full name and e-mail, then the Sign-in Code e-mailed to it
 * (ADR-0004). The only place an Account comes into existence; it starts
 * pending, so the code leads to the waiting-for-approval page (FR-01). */
export function RegisterPage() {
  const { register, verifyCode, user, loading: authLoading } = useAuth()
  const navigate = useNavigate()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!authLoading && user) {
    return <Navigate to="/" replace />
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const name = fullName.trim()
    const typed = email.trim()
    if (!name || !typed) {
      setError('Enter your full name and e-mail.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      await register(typed, name)
      setFullName(name)
      setEmail(typed)
      setCodeSent(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed.')
    } finally {
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
          <h1 className="text-2xl font-bold tracking-tight text-navy-50">
            Create your account
          </h1>
          <p className="mt-2 text-sm text-navy-400">
            Register to start monitoring crew document expiry
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
              onResend={() => register(email, fullName)}
              onChangeEmail={() => setCodeSent(false)}
            />
          ) : (
            <form onSubmit={handleSubmit} className="space-y-6" noValidate>
              {error && <ErrorNote message={error} />}

              <div>
                <label
                  htmlFor="fullName"
                  className="mb-2 block text-sm font-medium text-navy-100"
                >
                  Full Name
                </label>
                <input
                  id="fullName"
                  type="text"
                  autoComplete="name"
                  required
                  autoFocus
                  maxLength={200}
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  disabled={loading}
                  aria-required="true"
                  aria-invalid={error ? true : undefined}
                  className={INPUT_CLASS}
                  placeholder="John Smith"
                />
              </div>

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
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={loading}
                  aria-required="true"
                  aria-invalid={error ? true : undefined}
                  className={INPUT_CLASS}
                  placeholder="you@company.com"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-navy-600 px-4 py-2.5 font-medium text-navy-50 transition-colors hover:bg-navy-500 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading && <Loader2 className="h-5 w-5 animate-spin" />}
                {loading ? (
                  'Sending code...'
                ) : (
                  <>
                    <UserPlus className="h-5 w-5" aria-hidden="true" />
                    Create Account
                  </>
                )}
              </button>
            </form>
          )}
        </div>

        <p className="mt-6 text-center text-sm text-navy-400">
          Already have an account?{' '}
          <Link
            to="/login"
            className="font-medium text-navy-200 transition-colors hover:text-navy-50 focus:outline-none focus:ring-2 focus:ring-navy-400/40 rounded"
          >
            Sign in
          </Link>
        </p>

        <p className="mt-3 text-center text-xs text-navy-500">
          Maritime Crew Document Expiry Monitoring System
        </p>
      </div>
    </div>
  )
}
