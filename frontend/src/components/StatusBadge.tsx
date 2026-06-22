import {
  CheckCircle,
  AlertTriangle,
  XCircle,
  Clock,
  Shield,
  Ban,
  type LucideIcon,
} from 'lucide-react'
import type { DocumentStatus } from '../types'
import { cn } from '../lib/cn'

interface StatusConfig {
  icon: LucideIcon
  label: string
  colorClass: string
  bgClass: string
}

const STATUS_CONFIG: Record<DocumentStatus, StatusConfig> = {
  valid: {
    icon: CheckCircle,
    label: 'Valid',
    colorClass: 'text-status-valid',
    bgClass: 'bg-status-valid-bg/10',
  },
  expiring_soon: {
    icon: AlertTriangle,
    label: 'Expiring Soon',
    colorClass: 'text-status-expiring',
    bgClass: 'bg-status-expiring-bg/10',
  },
  expired: {
    icon: XCircle,
    label: 'Expired',
    colorClass: 'text-status-expired',
    bgClass: 'bg-status-expired-bg/10',
  },
  pending: {
    icon: Clock,
    label: 'Pending',
    colorClass: 'text-status-pending',
    bgClass: 'bg-status-pending-bg/10',
  },
  verified: {
    icon: Shield,
    label: 'Verified',
    colorClass: 'text-status-verified',
    bgClass: 'bg-status-verified-bg/10',
  },
  rejected: {
    icon: Ban,
    label: 'Rejected',
    colorClass: 'text-status-rejected',
    bgClass: 'bg-status-rejected-bg/10',
  },
}

interface StatusBadgeProps {
  status: DocumentStatus
  className?: string
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status]
  const Icon = config.icon

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium',
        config.colorClass,
        config.bgClass,
        className,
      )}
      aria-label={`Status: ${config.label}`}
      role="status"
    >
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {config.label}
    </span>
  )
}
