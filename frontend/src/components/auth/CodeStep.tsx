import { useEffect, useState, type FormEvent } from 'react'
import { ArrowLeft, Loader2, MailCheck, RefreshCw } from 'lucide-react'
import { ErrorNote } from '../ErrorNote'
import {
  CODE_LENGTH,
  CODE_SENT_MESSAGE,
  codeErrorMessage,
  isCompleteCode,
  normaliseCode,
  secondsUntilResend,
} from '../../lib/signInCode'

const INPUT_CLASS =
  'w-full rounded-lg border border-navy-700 bg-navy-950 px-4 py-2.5 text-center font-mono text-2xl tracking-[0.5em] text-navy-50 placeholder-navy-600 transition-colors focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50'

function toError(err: unknown): Error {
  return err instanceof Error ? err : new Error('Something went wrong. Try again.')
}

/**
 * The second step of Register and Sign in: type the Sign-in Code that was
 * e-mailed (ADR-0004). The page that shows it sent the first code.
 */
export function CodeStep({
  email,
  onVerify,
  onResend,
  onChangeEmail,
}: {
  email: string
  /** Checks the code and starts the session; throws the API's refusal. */
  onVerify: (code: string) => Promise<void>
  /** Asks for a new code the same way the first one was asked for. */
  onResend: () => Promise<void>
  onChangeEmail: () => void
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
      setError(codeErrorMessage(toError(err)))
      setVerifying(false)
    }
  }

  const handleResend = async () => {
    setError(null)
    setResending(true)
    try {
      await onResend()
      setCode('')
      setSentAt(Date.now())
      setNow(Date.now())
    } catch (err) {
      setError(toError(err).message)
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
        <MailCheck className="mt-0.5 h-5 w-5 shrink-0 text-navy-300" aria-hidden="true" />
        <p className="text-sm text-navy-200">
          {CODE_SENT_MESSAGE} It was sent to <strong className="text-navy-50">{email}</strong> and
          is valid for 10 minutes.
        </p>
      </div>

      {error && <ErrorNote message={error} />}

      <div>
        <label htmlFor="code" className="mb-2 block text-sm font-medium text-navy-100">
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
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-navy-600 px-4 py-2.5 font-medium text-navy-50 transition-colors hover:bg-navy-500 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {verifying && <Loader2 className="h-5 w-5 animate-spin" />}
        {verifying ? 'Checking code...' : 'Continue'}
      </button>

      <div className="flex items-center justify-between gap-3 text-sm">
        <button
          type="button"
          onClick={onChangeEmail}
          disabled={verifying}
          className="flex items-center gap-1 rounded font-medium text-navy-300 transition-colors hover:text-navy-50 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Change e-mail
        </button>
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
      </div>
    </form>
  )
}
