import { Clock, ShieldCheck } from 'lucide-react'
import { cn } from '../lib/cn'
import { BADGE_TONE } from '../lib/badgeTone'

/** On a Current Version (or any Version) that no one has reviewed yet. */
export function NotReviewedTag({
  className,
  label = 'Not reviewed',
}: {
  className?: string
  label?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
        BADGE_TONE.warn,
        className,
      )}
    >
      <Clock className="h-3 w-3" aria-hidden="true" />
      {label}
    </span>
  )
}

/** Shown only when the Current Version's latest Verification is confirmed.
 * Verified (the issuing authority confirmed) is never the same as Reviewed. */
export function VerifiedShield({ className }: { className?: string }) {
  return (
    <span
      className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium', BADGE_TONE.ok, className)}
      title="The issuing authority confirmed the current version"
    >
      <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
      Verified
    </span>
  )
}
