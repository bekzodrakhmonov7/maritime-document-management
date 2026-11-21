import { cn } from '../lib/cn'
import type { EffectiveExpiryFields } from '../lib/effectiveExpiry'

/** The note shown when an Endorsement's Effective Expiry isn't its own date:
 * capped by its certificate (both dates shown), or no certificate behind it
 * (counts as expired). Renders nothing otherwise, so callers keep their own
 * expiry display. */
export function EndorsementCapNote({
  ownExpiry,
  effectiveExpiry,
  cappedBy,
  certificateMissing,
  className,
}: EffectiveExpiryFields & { className?: string }) {
  if (certificateMissing) {
    return (
      <span className={cn('text-sm text-danger', className)}>
        Certificate missing: counts as expired
      </span>
    )
  }
  if (!cappedBy || !effectiveExpiry) return null
  return (
    <span className={cn('text-sm text-ink-muted', className)}>
      Valid until {effectiveExpiry} (capped by {cappedBy}; own expiry {ownExpiry ?? 'none'})
    </span>
  )
}
