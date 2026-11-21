import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { Anchor, Loader2, UserPlus } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { CodeStep } from '../components/auth/CodeStep'
import { ErrorNote } from '../components/ErrorNote'
import {
  MAX_PASSWORD_LENGTH,
  MIN_PASSWORD_LENGTH,
  passwordProblem,
  type SignInStep,
} from '../lib/signInCode'

const INPUT_CLASS =
  'w-full rounded-md border border-line-strong bg-canvas px-4 py-2.5 text-ink placeholder-ink-faint transition-colors focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-50'

/** Register: full name, e-mail and password, then the code e-mailed to the
 * address, then enrolling an authenticator app (ADR 0005, ADR 0007). The only
 * place an Account comes into existence; it starts pending, so the last code
 * leads to the waiting-for-approval page (FR-01). */
export function RegisterPage() {
  const { register, resendCode, verifyCode, user, loading: authLoading } = useAuth()
  const navigate = useNavigate()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [repeated, setRepeated] = useState('')
  const [step, setStep] = useState<SignInStep | null>(null)
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
    const problem = passwordProblem(password, repeated)
    if (problem) {
      setError(problem)
      return
    }
    setError(null)
    setLoading(true)
    try {
      const issued = await register(typed, name, password)
      setFullName(name)
      setEmail(typed)
      setPassword('')
      setRepeated('')
      setStep(issued)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed.')
    } finally {
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
          <h1 className="text-xl font-medium tracking-tight text-ink">
            Create your account
          </h1>
          <p className="mt-2 text-sm text-ink-faint">
            Register to start monitoring crew document expiry
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
              {error && <ErrorNote message={error} />}

              <div>
                <label
                  htmlFor="fullName"
                  className="mb-2 block text-sm font-medium text-ink"
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
                  className="mb-2 block text-sm font-medium text-ink"
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

              <div>
                <label
                  htmlFor="password"
                  className="mb-2 block text-sm font-medium text-ink"
                >
                  Password
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
                  aria-invalid={error ? true : undefined}
                  className={INPUT_CLASS}
                />
                <p id="password-hint" className="mt-1.5 text-xs text-ink-faint">
                  At least {MIN_PASSWORD_LENGTH} characters, and not a common or breached password.
                </p>
              </div>

              <div>
                <label
                  htmlFor="repeated"
                  className="mb-2 block text-sm font-medium text-ink"
                >
                  Repeat password
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
                {loading ? (
                  'Creating account...'
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

        <p className="mt-6 text-center text-sm text-ink-faint">
          Already have an account?{' '}
          <Link
            to="/login"
            className="font-medium text-ink-muted transition-colors hover:text-ink focus:outline-none focus:ring-2 focus:ring-accent/40 rounded"
          >
            Sign in
          </Link>
        </p>

        <p className="mt-3 text-center text-xs text-ink-faint">
          Maritime Crew Document Expiry Monitoring System
        </p>
      </div>
    </div>
  )
}
