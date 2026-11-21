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
