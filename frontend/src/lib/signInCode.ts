/**
 * Register and Sign in (ADR-0005): a password first, then a Sign-in Code
 * e-mailed to the address. A code is 6 digits, and a new one can be asked
 * for at most every 60 seconds.
 */

export const CODE_LENGTH = 6
export const RESEND_WAIT_SECONDS = 60

export const MIN_PASSWORD_LENGTH = 8
/** bcrypt reads at most 72 bytes; Supabase Auth refuses longer passwords. */
export const MAX_PASSWORD_LENGTH = 72

/** What the sign-in proxy says once the first step is done. */
export const CODE_SENT_MESSAGE = "We've e-mailed you a 6-digit code."

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

/** Supabase Auth's codes for a code that doesn't match or ran out. */
const WRONG_OR_EXPIRED = new Set(['otp_expired', 'otp_invalid', 'invalid_credentials'])

/** What the person sees when the API refused their code. */
export function codeErrorMessage(err: { code?: string | null; status?: number; message: string }): string {
  if (err.code && WRONG_OR_EXPIRED.has(err.code)) {
    return 'That code is wrong or has expired. Check it, or send a new code.'
  }
  if (err.status === 429) {
    return 'Too many attempts. Wait a minute, then try again.'
  }
  return err.message
}
