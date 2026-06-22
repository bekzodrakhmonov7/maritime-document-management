import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  LayoutDashboard,
  FileText,
  Bell,
  Users,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Clock,
  Shield,
  Ban,
  type LucideIcon,
} from 'lucide-react'
import { useSeafarers } from '../hooks/useSeafarers'
import { useDocuments } from '../hooks/useDocuments'
import { CrewTable } from '../components/CrewTable'
import { cn } from '../lib/cn'
import type { DocumentStatus } from '../types'

interface SummaryCardConfig {
  status: DocumentStatus
  icon: LucideIcon
  colorClass: string
  bgClass: string
  borderClass: string
}

const SUMMARY_CARDS: SummaryCardConfig[] = [
  {
    status: 'valid',
    icon: CheckCircle,
    colorClass: 'text-status-valid',
    bgClass: 'bg-status-valid-bg/10',
    borderClass: 'border-status-valid/30',
  },
  {
    status: 'expiring_soon',
    icon: AlertTriangle,
    colorClass: 'text-status-expiring',
    bgClass: 'bg-status-expiring-bg/10',
    borderClass: 'border-status-expiring/30',
  },
  {
    status: 'expired',
    icon: XCircle,
    colorClass: 'text-status-expired',
    bgClass: 'bg-status-expired-bg/10',
    borderClass: 'border-status-expired/30',
  },
  {
    status: 'pending',
    icon: Clock,
    colorClass: 'text-status-pending',
    bgClass: 'bg-status-pending-bg/10',
    borderClass: 'border-status-pending/30',
  },
  {
    status: 'verified',
    icon: Shield,
    colorClass: 'text-status-verified',
    bgClass: 'bg-status-verified-bg/10',
    borderClass: 'border-status-verified/30',
  },
  {
    status: 'rejected',
    icon: Ban,
    colorClass: 'text-status-rejected',
    bgClass: 'bg-status-rejected-bg/10',
    borderClass: 'border-status-rejected/30',
  },
]

const STATUS_LABELS: Record<DocumentStatus, string> = {
  valid: 'Valid',
  expiring_soon: 'Expiring Soon',
  expired: 'Expired',
  pending: 'Pending',
  verified: 'Verified',
  rejected: 'Rejected',
}

export function DashboardPage() {
  const seafarersQuery = useSeafarers()
  const documentsQuery = useDocuments()

  const statusCounts = useMemo(() => {
    const documents = documentsQuery.data ?? []
    const counts = {
      valid: 0,
      expiring_soon: 0,
      expired: 0,
      pending: 0,
      verified: 0,
      rejected: 0,
    } as Record<DocumentStatus, number>

    for (const doc of documents) {
      counts[doc.status]++
    }

    return counts
  }, [documentsQuery.data])

  const totalCrew = seafarersQuery.data?.length ?? 0
  const totalDocs = documentsQuery.data?.length ?? 0

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <LayoutDashboard className="h-5 w-5 text-navy-300" aria-hidden="true" />
          <h1 className="text-xl font-bold tracking-tight text-navy-50">
            Fleet Dashboard
          </h1>
        </div>
        <p className="text-sm text-navy-400">
          Fleet-wide crew document status overview
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {SUMMARY_CARDS.map((card) => {
          const Icon = card.icon
          const count = statusCounts[card.status]
          return (
            <div
              key={card.status}
              className={cn(
                'rounded-xl border p-4',
                card.borderClass,
                card.bgClass,
              )}
            >
              <div className="flex items-center justify-between">
                <Icon
                  className={cn('h-5 w-5', card.colorClass)}
                  aria-hidden="true"
                />
                <span
                  className={cn('text-2xl font-bold', card.colorClass)}
                  aria-label={`${STATUS_LABELS[card.status]}: ${count}`}
                >
                  {count}
                </span>
              </div>
              <p className="mt-2 text-xs font-medium text-navy-300">
                {STATUS_LABELS[card.status]}
              </p>
            </div>
          )
        })}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-navy-800 bg-navy-900 p-4">
          <div className="flex items-center gap-2">
            <Users className="h-5 w-5 text-navy-300" aria-hidden="true" />
            <span className="text-sm font-medium text-navy-200">Total Crew</span>
          </div>
          <p className="mt-2 text-2xl font-bold text-navy-50">{totalCrew}</p>
        </div>
        <div className="rounded-xl border border-navy-800 bg-navy-900 p-4">
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-navy-300" aria-hidden="true" />
            <span className="text-sm font-medium text-navy-200">Total Documents</span>
          </div>
          <p className="mt-2 text-2xl font-bold text-navy-50">{totalDocs}</p>
        </div>
        <Link
          to="/documents"
          className="rounded-xl border border-navy-800 bg-navy-900 p-4 transition-colors hover:border-navy-600 hover:bg-navy-800 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
        >
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-navy-300" aria-hidden="true" />
            <span className="text-sm font-medium text-navy-200">Documents</span>
          </div>
          <p className="mt-2 text-sm text-navy-400">Manage document registry</p>
        </Link>
        <Link
          to="/alerts"
          className="rounded-xl border border-navy-800 bg-navy-900 p-4 transition-colors hover:border-navy-600 hover:bg-navy-800 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
        >
          <div className="flex items-center gap-2">
            <Bell className="h-5 w-5 text-navy-300" aria-hidden="true" />
            <span className="text-sm font-medium text-navy-200">Alerts</span>
          </div>
          <p className="mt-2 text-sm text-navy-400">View expiring documents</p>
        </Link>
      </div>

      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-navy-50">Crew Overview</h2>
        </div>
        <CrewTable />
      </div>
    </div>
  )
}
