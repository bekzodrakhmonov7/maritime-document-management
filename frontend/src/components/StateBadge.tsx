import { cn } from '../lib/cn'

/** "Active" / "Deactivated" / "Retired" etc. for reference data rows. */
export function StateBadge({ on, label }: { on: boolean; label: string }) {
  return (
    <span
      className={cn(
        'rounded-full px-2.5 py-1 text-xs font-medium',
        on ? 'bg-status-valid-bg/10 text-status-valid' : 'bg-navy-800 text-navy-400',
      )}
    >
      {label}
    </span>
  )
}
