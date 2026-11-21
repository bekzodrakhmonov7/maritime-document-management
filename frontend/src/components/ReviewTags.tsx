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
  return <span className={cn('text-xs', BADGE_TONE.warn, className)}>{label}</span>
}

/** Shown only when the Current Version's latest Verification is confirmed.
 * Verified (the issuing authority confirmed) is never the same as Reviewed. */
export function VerifiedShield({ className }: { className?: string }) {
  return (
    <span
      className={cn('text-xs', BADGE_TONE.ok, className)}
      title="The issuing authority confirmed the current version"
    >
      Verified
    </span>
  )
}
