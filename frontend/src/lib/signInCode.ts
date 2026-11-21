/**
 * Register and Sign in (ADR 0005, ADR 0007, SR-03): a password first, then
 * a 6-digit code from an authenticator app (TOTP). The first sign-in enrols
 * the app; Register is finished with a code e-mailed to the address first,
 * and a new one of those can be asked for at most every 60 seconds.
 */

export const CODE_LENGTH = 6
export const RESEND_WAIT_SECONDS = 60

/** SR-02: the API also refuses common and breached passwords (422 weak_password). */
export const MIN_PASSWORD_LENGTH = 12
/** bcrypt reads at most 72 bytes; Supabase Auth refuses longer passwords. */
export const MAX_PASSWORD_LENGTH = 72

/** What the sign-in proxy says once Register's first step is done. */
export const CODE_SENT_MESSAGE = "We've e-mailed you a 6-digit code."

/** The step after the password (or after Register), as the sign-in proxy
 * answers it: the e-mailed code that finishes Register, the code of the
 * enrolled authenticator, or enrolling one first. */
export type SignInStep =
  | { challenge: string; step: 'email' | 'totp'; message: string }
  | {
      challenge: string
      step: 'enrol'
      message: string
      /** An SVG image of the otpauth URI. */
      qr_code: string
      /** The same key, for typing into the app by hand. */
      secret: string
      uri: string
    }

/** The QR code SVG as an image source; an <img> runs no script in it. */
export function qrCodeSource(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
}

/** The key in groups of four, easier to type by hand. */
export function groupSecret(secret: string): string {
  return secret.replace(/\s+/g, '').match(/.{1,4}/g)?.join(' ') ?? ''
}

/** The sign-in proxy's code for a first step that must be done again
 * (10 minutes passed, 5 wrong codes, or already used). */
export const CHALLENGE_EXPIRED = 'challenge_expired'

/** Why a new password can't be used yet, or null when it can. */
export function passwordProblem(password: string, repeated: string): string | null {
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Use at least ${MIN_PASSWORD_LENGTH} characters for the password.`
  }
  if (new TextEncoder().encode(password).length > MAX_PASSWORD_LENGTH) {
    return `Use at most ${MAX_PASSWORD_LENGTH} characters for the password.`
  }
  if (password !== repeated) {
    return 'The two passwords are not the same.'
  }
  return null
}

/** The digits of what was typed or pasted, at most 6. */
export function normaliseCode(input: string): string {
  return input.replace(/\D/g, '').slice(0, CODE_LENGTH)
}

const COMPLETE_CODE = new RegExp(`^[0-9]{${CODE_LENGTH}}$`)

export function isCompleteCode(code: string): boolean {
  return COMPLETE_CODE.test(code)
}

/** Whole seconds left before "Send a new code" may be used again. */
export function secondsUntilResend(sentAt: number | null, now: number): number {
  if (sentAt === null) return 0
  const left = RESEND_WAIT_SECONDS * 1000 - (now - sentAt)
  return left <= 0 ? 0 : Math.ceil(left / 1000)
}

/** Supabase Auth's codes for an e-mailed code that doesn't match or ran out. */
const WRONG_OR_EXPIRED = new Set(['otp_expired', 'otp_invalid', 'invalid_credentials'])

type Refusal = { code?: string | null; status?: number; message: string }

/** SR-18: 10 failed sign-ins for the e-mail or from the address within
 * 15 minutes block both steps for 15 minutes (429 login_blocked). */
export const LOGIN_BLOCKED = 'login_blocked'
export const LOGIN_BLOCKED_MESSAGE =
  'Too many failed sign-in attempts. Wait 15 minutes, then try again.'
const TOO_MANY_MESSAGE = 'Too many attempts. Wait a minute, then try again.'

/** What the person sees when the API refused their e-mail and password. */
export function signInErrorMessage(err: Refusal): string {
  if (err.code === LOGIN_BLOCKED) return LOGIN_BLOCKED_MESSAGE
  if (err.status === 429) return TOO_MANY_MESSAGE
  return err.message
}

/** What the person sees when the API refused their code. */
export function codeErrorMessage(err: Refusal): string {
  if (err.code === LOGIN_BLOCKED) return LOGIN_BLOCKED_MESSAGE
  if (err.code === 'totp_invalid') {
    return 'That code is wrong. Enter the code your authenticator app shows now.'
  }
  if (err.code && WRONG_OR_EXPIRED.has(err.code)) {
    return 'That code is wrong or has expired. Check it, or send a new code.'
  }
  if (err.status === 429) return TOO_MANY_MESSAGE
  return err.message
}

/** Where a refused password reset is shown: under the authenticator code
 * field (`totp`) or above the whole form (`null`). A missing or wrong
 * authenticator code used up the e-mailed code, so a new one is needed. */
export function resetError(err: Refusal): { field: 'totp' | null; message: string } {
  const again = ' Go back and send a new code to the e-mail, then try again.'
  if (err.code === 'totp_required') {
    return { field: 'totp', message: 'Enter the code from your authenticator app.' + again }
  }
  if (err.code === 'totp_invalid') {
    return { field: 'totp', message: 'That authenticator code is wrong.' + again }
  }
  return { field: null, message: codeErrorMessage(err) }
}
