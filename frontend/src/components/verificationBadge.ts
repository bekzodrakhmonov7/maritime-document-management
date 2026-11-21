// No JSX here so the node test runner can render it (tests/verificationBadge.test.ts).
import { createElement } from 'react'
import { cn } from '../lib/cn.ts'
import { BADGE_TONE } from '../lib/badgeTone.ts'

/** Shown when the Current Version's latest Verification is confirmed.
 * Verified (the issuing authority confirmed) is never the same as Reviewed. */
export function VerifiedShield({ className }: { className?: string }) {
  return createElement(
    'span',
    {
      className: cn('text-xs', BADGE_TONE.ok, className),
      title: 'The issuing authority confirmed the current version',
    },
    'Verified',
  )
}

/** F-12: the counterpart of the shield, grey like any other status word
 * (light minimal redesign: not a problem, so no warning colour). */
export function NotVerifiedTag({ className }: { className?: string }) {
  return createElement('span', { className: cn('text-xs', BADGE_TONE.neutral, className) }, 'Not verified')
}

/** Verified shield or "Not verified": wherever a Document's Verification shows. */
export function VerificationBadge({ verified, className }: { verified: boolean; className?: string }) {
  return verified ? VerifiedShield({ className }) : NotVerifiedTag({ className })
}
