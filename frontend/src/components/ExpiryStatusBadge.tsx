import { AlertTriangle, CheckCircle, CircleHelp, CircleSlash, Infinity as NoExpiry, XCircle, type LucideIcon } from 'lucide-react'
import { cn } from '../lib/cn'
import { BADGE_TONE } from '../lib/badgeTone'
import { EXPIRY_STATUS_LABELS, type ExpiryStatus } from '../types'

const STYLE: Record<ExpiryStatus, { icon: LucideIcon; className: string }> = {
  unexpired: { icon: CheckCircle, className: BADGE_TONE.ok },
  expiring_soon: { icon: AlertTriangle, className: BADGE_TONE.warn },
  expired: { icon: XCircle, className: BADGE_TONE.bad },
  no_expiry_date: { icon: NoExpiry, className: BADGE_TONE.neutral },
  expiry_not_stated: { icon: CircleHelp, className: BADGE_TONE.warn },
}

/** A document's Expiry Status, whether or not it is reviewed. `null` means it
 * has no Current Version (every Version rejected) and counts as missing. */
export function ExpiryStatusBadge({ status, className }: { status: ExpiryStatus | null; className?: string }) {
  const { icon: Icon, className: tone } = status
    ? STYLE[status]
    : { icon: CircleSlash, className: BADGE_TONE.neutral }
  const label = status ? EXPIRY_STATUS_LABELS[status] : 'Missing'
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium',
        tone,
        className,
      )}
      aria-label={`Expiry status: ${label}`}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {label}
    </span>
  )
}
