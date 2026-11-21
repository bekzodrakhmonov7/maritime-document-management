import { useEffect, useState, type FormEvent } from 'react'
import { ArrowLeft, Loader2, MailCheck, RefreshCw } from 'lucide-react'
import { ErrorNote } from '../ErrorNote'
import { ApiError } from '../../lib/api'
import {
  CHALLENGE_EXPIRED,
  CODE_LENGTH,
  CODE_SENT_MESSAGE,
  codeErrorMessage,
  isCompleteCode,
  normaliseCode,
  secondsUntilResend,
} from '../../lib/signInCode'

const INPUT_CLASS =
  'w-full rounded-md border border-line-strong bg-canvas px-4 py-2.5 text-center font-mono text-xl tracking-[0.5em] text-ink placeholder-ink-faint transition-colors focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-50'

function toError(err: unknown): Error {
  return err instanceof Error ? err : new Error('Something went wrong. Try again.')
}

/**
 * The second step of Register and Sign in: type the Sign-in Code that was
 * e-mailed (ADR-0005). The page that shows it did the first step (the
 * password) and sent the first code.
 */
export function CodeStep({
  email,
  onVerify,
  onResend,
  onBack,
  onExpired,
}: {
  email: string
  /** Checks the code and starts the session; throws the API's refusal. */
  onVerify: (code: string) => Promise<void>
  /** Asks for a new code for the same first step. */
  onResend: () => Promise<void>
  /** Back to the first step. */
  onBack: () => void
  /** The first step must be done again; given the message to show there. */
  onExpired: (message: string) => void
}) {
  const [code, setCode] = useState('')
  const [sentAt, setSentAt] = useState(() => Date.now())
  const [now, setNow] = useState(() => Date.now())
  const [verifying, setVerifying] = useState(false)
  const [resending, setResending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const wait = secondsUntilResend(sentAt, now)

  useEffect(() => {
    if (wait === 0) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [wait])

  /** Hands an expired challenge back to the page; true when it did. */
  const expired = (err: unknown): boolean => {
    if (err instanceof ApiError && err.code === CHALLENGE_EXPIRED) {
      onExpired(err.message)
      return true
    }
    return false
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!isCompleteCode(code)) {
      setError(`Enter the ${CODE_LENGTH}-digit code from the e-mail.`)
      return
    }
    setError(null)
    setVerifying(true)
    try {
      await onVerify(code)
    } catch (err) {
      if (!expired(err)) {
        setError(codeErrorMessage(toError(err)))
        setVerifying(false)
      }
    }
  }

  const handleResend = async () => {
    setError(null)
    setResending(true)
    try {
      await onResend()
      const resentAt = Date.now()
      setCode('')
      setSentAt(resentAt)
      setNow(resentAt)
    } catch (err) {
      if (!expired(err)) setError(toError(err).message)
    } finally {
      setResending(false)
    }
  }

  const busy = verifying || resending

  return (
    <form onSubmit={handleSubmit} className="space-y-6" noValidate>
      <div
        role="status"
        className="flex items-start gap-3 rounded-md border border-line-strong bg-canvas p-4"
      >
        <MailCheck className="mt-0.5 h-5 w-5 shrink-0 text-ink-muted" aria-hidden="true" />
        <p className="text-sm text-ink-muted">
          {CODE_SENT_MESSAGE} It was sent to <strong className="text-ink">{email}</strong> and
          is valid for 10 minutes.
        </p>
      </div>

      {error && <ErrorNote message={error} />}

      <div>
        <label htmlFor="code" className="mb-2 block text-sm font-medium text-ink">
          Sign-in Code
        </label>
        <input
          id="code"
          name="code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]*"
          maxLength={CODE_LENGTH}
          required
          autoFocus
          value={code}
          onChange={(e) => setCode(normaliseCode(e.target.value))}
          disabled={verifying}
          aria-required="true"
          aria-invalid={error ? true : undefined}
          className={INPUT_CLASS}
          placeholder="000000"
        />
      </div>

      <button
        type="submit"
        disabled={busy}
        className="flex w-full items-center justify-center gap-2 rounded-md bg-accent px-4 py-2.5 font-medium text-on-accent transition-colors hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {verifying && <Loader2 className="h-5 w-5 animate-spin" />}
        {verifying ? 'Checking code...' : 'Continue'}
      </button>

      <div className="flex items-center justify-between gap-3 text-sm">
        <button
          type="button"
          onClick={onBack}
          disabled={verifying}
          className="flex items-center gap-1 rounded font-medium text-ink-muted transition-colors hover:text-ink focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-50"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back
        </button>
        <button
          type="button"
          onClick={() => void handleResend()}
          disabled={busy || wait > 0}
          className="flex items-center gap-1 rounded font-medium text-ink-muted transition-colors hover:text-ink focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {resending ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          )}
          {wait > 0 ? `Send a new code (${wait} s)` : 'Send a new code'}
        </button>
      </div>
    </form>
  )
}
