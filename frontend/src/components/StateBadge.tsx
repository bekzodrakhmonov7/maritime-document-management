import { cn } from '../lib/cn'
import { BADGE_TONE } from '../lib/badgeTone'

/** "Active" / "Deactivated" / "Retired" etc. for reference data rows. */
export function StateBadge({ on, label }: { on: boolean; label: string }) {
  return (
    <span
      className={cn(
        'rounded-full px-2.5 py-1 text-xs font-medium',
        on ? BADGE_TONE.ok : BADGE_TONE.neutral,
      )}
    >
      {label}
    </span>
  )
}
