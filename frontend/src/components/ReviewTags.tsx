import { Clock, ShieldCheck } from 'lucide-react'
import { cn } from '../lib/cn'

/** On a Current Version (or any Version) that no one has reviewed yet. */
export function NotReviewedTag({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full bg-status-expiring-bg/10 px-2 py-0.5 text-xs font-medium text-status-expiring',
        className,
      )}
    >
      <Clock className="h-3 w-3" aria-hidden="true" />
      Not reviewed
    </span>
  )
}

/** Shown only when the Current Version's latest Verification is confirmed.
 * Verified (the issuing authority confirmed) is never the same as Reviewed. */
export function VerifiedShield({ className }: { className?: string }) {
  return (
    <span
      className={cn('inline-flex items-center gap-1 text-xs font-medium text-status-valid', className)}
      title="The issuing authority confirmed the current version"
    >
      <ShieldCheck className="h-4 w-4" aria-hidden="true" />
      Verified
    </span>
  )
}
