import { useEffect, useState, type FormEvent } from 'react'
import { ArrowLeft, KeyRound, Loader2, MailCheck, RefreshCw, Smartphone } from 'lucide-react'
import { ErrorNote } from '../ErrorNote'
import { ApiError } from '../../lib/api'
import {
  CHALLENGE_EXPIRED,
  CODE_LENGTH,
  CODE_SENT_MESSAGE,
  codeErrorMessage,
  groupSecret,
  isCompleteCode,
  normaliseCode,
  qrCodeSource,
  secondsUntilResend,
  type SignInStep,
} from '../../lib/signInCode'

const INPUT_CLASS =
  'w-full rounded-lg border border-navy-700 bg-navy-950 px-4 py-2.5 text-center font-mono text-2xl tracking-[0.5em] text-navy-50 placeholder-navy-600 transition-colors focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50'

function toError(err: unknown): Error {
  return err instanceof Error ? err : new Error('Something went wrong. Try again.')
}

/**
 * The step after the password (ADR 0005, ADR 0007): the code from the
 * authenticator app, or enrolling the app first (QR code, or the key typed
 * by hand), or, to finish Register, the code e-mailed to the address. The
 * page that shows it did the step before.
 */
export function CodeStep({
  email,
  step,
  onVerify,
  onResend,
  onBack,
  onExpired,
}: {
  email: string
  step: SignInStep
  /** Checks the code and goes on (next step or session); throws the API's refusal. */
  onVerify: (code: string) => Promise<void>
  /** Asks for a new e-mailed code for the same step (Register only). */
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
  const emailed = step.step === 'email'

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
      setError(
        `Enter the ${CODE_LENGTH}-digit code from ${emailed ? 'the e-mail' : 'your authenticator app'}.`,
      )
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
        className="flex items-start gap-3 rounded-lg border border-navy-700 bg-navy-950 p-4"
      >
        {emailed ? (
          <MailCheck className="mt-0.5 h-5 w-5 shrink-0 text-navy-300" aria-hidden="true" />
        ) : (
          <Smartphone className="mt-0.5 h-5 w-5 shrink-0 text-navy-300" aria-hidden="true" />
        )}
        <p className="text-sm text-navy-200">
          {emailed ? (
            <>
              {CODE_SENT_MESSAGE} It was sent to <strong className="text-navy-50">{email}</strong>{' '}
              and is valid for 10 minutes.
            </>
          ) : step.step === 'enrol' ? (
            <>
              Set up two-step sign-in for <strong className="text-navy-50">{email}</strong>: scan
              the QR code with an authenticator app (for example Google Authenticator, Microsoft
              Authenticator or 1Password), then enter the 6-digit code it shows.
            </>
          ) : (
            <>Enter the 6-digit code your authenticator app shows for this account.</>
          )}
        </p>
      </div>

      {step.step === 'enrol' && (
        <div className="space-y-3">
          <img
            src={qrCodeSource(step.qr_code)}
            alt="QR code to add this account to an authenticator app"
            width={207}
            height={207}
            className="mx-auto rounded-lg bg-white p-2"
          />
          <div className="rounded-lg border border-navy-700 bg-navy-950 p-3">
            <p className="flex items-center gap-2 text-xs text-navy-400">
              <KeyRound className="h-4 w-4" aria-hidden="true" />
              Can't scan it? Type this key into the app instead:
            </p>
            <p
              className="mt-1 break-all text-center font-mono text-sm tracking-wider text-navy-50"
              aria-label="Key for typing into the authenticator app"
            >
              {groupSecret(step.secret)}
            </p>
          </div>
        </div>
      )}

      {error && <ErrorNote message={error} />}

      <div>
        <label htmlFor="code" className="mb-2 block text-sm font-medium text-navy-100">
          {emailed ? 'Code from the e-mail' : 'Code from your authenticator app'}
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
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-navy-600 px-4 py-2.5 font-medium text-navy-50 transition-colors hover:bg-navy-500 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {verifying && <Loader2 className="h-5 w-5 animate-spin" />}
        {verifying ? 'Checking code...' : 'Continue'}
      </button>

      <div className="flex items-center justify-between gap-3 text-sm">
        <button
          type="button"
          onClick={onBack}
          disabled={verifying}
          className="flex items-center gap-1 rounded font-medium text-navy-300 transition-colors hover:text-navy-50 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back
        </button>
        {emailed && (
          <button
            type="button"
            onClick={() => void handleResend()}
            disabled={busy || wait > 0}
            className="flex items-center gap-1 rounded font-medium text-navy-300 transition-colors hover:text-navy-50 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {resending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
            )}
            {wait > 0 ? `Send a new code (${wait} s)` : 'Send a new code'}
          </button>
        )}
      </div>
    </form>
  )
}
