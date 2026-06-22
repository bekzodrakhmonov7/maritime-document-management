import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { Anchor, Loader2, AlertCircle, CheckCircle, UserPlus } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import type { UserRole } from '../types'

const MIN_PASSWORD_LENGTH = 6

export function RegisterPage() {
  const { signUp, user, loading: authLoading } = useAuth()
  const navigate = useNavigate()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [role, setRole] = useState<UserRole>('crewing_officer')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  if (!authLoading && user) {
    return <Navigate to="/dashboard" replace />
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setInfo(null)

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`)
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)

    const { error: signUpError, needsEmailConfirmation } = await signUp(
      email,
      password,
      fullName.trim(),
      role,
    )

    if (signUpError) {
      setError(signUpError.message)
      setLoading(false)
      return
    }

    if (needsEmailConfirmation) {
      setInfo(
        'Account created. Please check your email to confirm your address before signing in.',
      )
      setLoading(false)
      return
    }

    navigate('/dashboard')
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
          <form onSubmit={handleSubmit} className="space-y-6" noValidate>
            {error && (
              <div
                role="alert"
                className="flex items-start gap-3 rounded-lg border border-status-expired/40 bg-status-expired-bg/10 p-4"
              >
                <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-status-expired" />
                <p className="text-sm text-status-expired">{error}</p>
              </div>
            )}

            {info && (
              <div
                role="status"
                className="flex items-start gap-3 rounded-lg border border-status-valid/40 bg-status-valid-bg/10 p-4"
              >
                <CheckCircle className="mt-0.5 h-5 w-5 shrink-0 text-status-valid" />
                <p className="text-sm text-status-valid">{info}</p>
              </div>
            )}

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
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                disabled={loading}
                aria-required="true"
                aria-invalid={error ? true : undefined}
                className="w-full rounded-lg border border-navy-700 bg-navy-950 px-4 py-2.5 text-navy-50 placeholder-navy-500 transition-colors focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50"
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
                className="w-full rounded-lg border border-navy-700 bg-navy-950 px-4 py-2.5 text-navy-50 placeholder-navy-500 transition-colors focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50"
                placeholder="you@company.com"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="mb-2 block text-sm font-medium text-navy-100"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                required
                minLength={MIN_PASSWORD_LENGTH}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
                aria-required="true"
                aria-invalid={error ? true : undefined}
                className="w-full rounded-lg border border-navy-700 bg-navy-950 px-4 py-2.5 text-navy-50 placeholder-navy-500 transition-colors focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50"
                placeholder="At least 6 characters"
              />
            </div>

            <div>
              <label
                htmlFor="confirmPassword"
                className="mb-2 block text-sm font-medium text-navy-100"
              >
                Confirm Password
              </label>
              <input
                id="confirmPassword"
                type="password"
                autoComplete="new-password"
                required
                minLength={MIN_PASSWORD_LENGTH}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                disabled={loading}
                aria-required="true"
                aria-invalid={error ? true : undefined}
                className="w-full rounded-lg border border-navy-700 bg-navy-950 px-4 py-2.5 text-navy-50 placeholder-navy-500 transition-colors focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50"
                placeholder="Re-enter your password"
              />
            </div>

            <div>
              <label
                htmlFor="role"
                className="mb-2 block text-sm font-medium text-navy-100"
              >
                Role
              </label>
              <select
                id="role"
                required
                value={role}
                onChange={(e) => setRole(e.target.value as UserRole)}
                disabled={loading}
                aria-required="true"
                className="w-full rounded-lg border border-navy-700 bg-navy-950 px-4 py-2.5 text-navy-50 transition-colors focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50"
              >
                <option value="crewing_officer">Crewing Officer</option>
                <option value="administrator">Administrator</option>
              </select>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-navy-600 px-4 py-2.5 font-medium text-navy-50 transition-colors hover:bg-navy-500 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:cursor-not-allowed disabled:opacity-50"
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
