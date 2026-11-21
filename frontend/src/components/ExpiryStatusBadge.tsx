import { cn } from '../lib/cn'
import { BADGE_TONE, type BadgeTone } from '../lib/badgeTone'
import { EXPIRY_STATUS_LABELS, type ExpiryStatus } from '../types'

const TONE: Record<ExpiryStatus, BadgeTone> = {
  unexpired: 'ok',
  expiring_soon: 'warn',
  expired: 'bad',
  no_expiry_date: 'neutral',
  expiry_not_stated: 'warn',
}

/** A document's Expiry Status, whether or not it is reviewed: a dot and a word.
 * `null` means it has no Current Version (every Version rejected) and counts
 * as missing. */
export function ExpiryStatusBadge({ status, className }: { status: ExpiryStatus | null; className?: string }) {
  const tone = status ? TONE[status] : 'bad'
  const label = status ? EXPIRY_STATUS_LABELS[status] : 'Missing'
  return (
    <span className={cn('text-sm', BADGE_TONE[tone], className)} aria-label={`Expiry status: ${label}`}>
      {label}
    </span>
  )
}
