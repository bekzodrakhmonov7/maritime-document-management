import { useMemo } from 'react'
import {
  BarChart3,
  Loader2,
  AlertCircle,
  FileText,
  FileDown,
  Ship,
  Users,
  CheckCircle,
  AlertTriangle,
  XCircle,
  FileWarning,
  type LucideIcon,
} from 'lucide-react'
import { useMissingMandatory, useFleetSummary } from '../hooks/useReports'
import { cn } from '../lib/cn'
import type { MissingMandatoryDoc, FleetSummary, FleetVesselSummary } from '../types'

function downloadCSV(filename: string, rows: MissingMandatoryDoc[]) {
  const headers = ['Seafarer', 'Rank', 'Vessel', 'Missing Document Type']
  const csvLines = [headers.join(',')]

  for (const row of rows) {
    const values = [
      `"${row.seafarer_name.replace(/"/g, '""')}"`,
      `"${row.rank.replace(/"/g, '""')}"`,
      `"${row.vessel_name.replace(/"/g, '""')}"`,
      `"${row.doc_type_name.replace(/"/g, '""')}"`,
    ]
    csvLines.push(values.join(','))
  }

  const csvContent = csvLines.join('\n')
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', filename)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

async function downloadPDF() {
  const { supabase } = await import('../lib/supabase')
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token

  const res = await fetch(`${import.meta.env.VITE_API_BASE || 'http://localhost:8000'}/reports/export.pdf`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) {
    throw new Error('Failed to download PDF')
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', `fleet-summary-${new Date().toISOString().split('T')[0]}.pdf`)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
function handlePDFDownload() {
  void downloadPDF().catch((err) => console.error('PDF download failed:', err))
}

interface SummaryCardConfig {
  key: keyof FleetSummary
  label: string
  icon: LucideIcon
  colorClass: string
  bgClass: string
  borderClass: string
}

const FLEET_CARDS: SummaryCardConfig[] = [
  {
    key: 'fleet_total_seafarers',
    label: 'Total Seafarers',
    icon: Users,
    colorClass: 'text-navy-200',
    bgClass: 'bg-navy-800/40',
    borderClass: 'border-navy-700',
  },
  {
    key: 'fleet_valid',
    label: 'Valid Documents',
    icon: CheckCircle,
    colorClass: 'text-status-valid',
    bgClass: 'bg-status-valid-bg/10',
    borderClass: 'border-status-valid/30',
  },
  {
    key: 'fleet_expiring_soon',
    label: 'Expiring Soon',
    icon: AlertTriangle,
    colorClass: 'text-status-expiring',
    bgClass: 'bg-status-expiring-bg/10',
    borderClass: 'border-status-expiring/30',
  },
  {
    key: 'fleet_expired',
    label: 'Expired',
    icon: XCircle,
    colorClass: 'text-status-expired',
    bgClass: 'bg-status-expired-bg/10',
    borderClass: 'border-status-expired/30',
  },
  {
    key: 'fleet_missing_mandatory',
    label: 'Missing Mandatory',
    icon: FileWarning,
    colorClass: 'text-status-rejected',
    bgClass: 'bg-status-rejected-bg/10',
    borderClass: 'border-status-rejected/30',
  },
  {
    key: 'fleet_compliance_percentage',
    label: 'Compliance',
    icon: BarChart3,
    colorClass: 'text-status-verified',
    bgClass: 'bg-status-verified-bg/10',
    borderClass: 'border-status-verified/30',
  },
]

function ComplianceBar({ percentage }: { percentage: number }) {
  const clamped = Math.max(0, Math.min(100, percentage))
  const colorClass =
    clamped >= 80
      ? 'bg-status-valid'
      : clamped >= 50
        ? 'bg-status-expiring'
        : 'bg-status-expired'

  return (
    <div className="flex items-center gap-3">
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-navy-700"
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Compliance: ${clamped}%`}
      >
        <div
          className={cn('h-full rounded-full transition-all', colorClass)}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <span className="w-12 shrink-0 text-right text-sm font-semibold tabular-nums text-navy-100">
        {clamped}%
      </span>
    </div>
  )
}

function VesselSummaryRow({ vessel }: { vessel: FleetVesselSummary }) {
  return (
    <tr className="transition-colors hover:bg-navy-800/50">
      <td className="px-4 py-3 whitespace-nowrap">
        <div className="flex items-center gap-2">
          <Ship className="h-4 w-4 text-navy-400" aria-hidden="true" />
          <span className="font-medium text-navy-50">{vessel.vessel_name}</span>
        </div>
      </td>
      <td className="px-4 py-3 whitespace-nowrap text-navy-200 tabular-nums">
        {vessel.total_seafarers}
      </td>
      <td className="px-4 py-3 whitespace-nowrap text-navy-200 tabular-nums">
        {vessel.total_documents}
      </td>
      <td className="px-4 py-3 whitespace-nowrap text-status-valid tabular-nums">
        {vessel.valid}
      </td>
      <td className="px-4 py-3 whitespace-nowrap text-status-expiring tabular-nums">
        {vessel.expiring_soon}
      </td>
      <td className="px-4 py-3 whitespace-nowrap text-status-expired tabular-nums">
        {vessel.expired}
      </td>
      <td className="px-4 py-3 whitespace-nowrap text-status-rejected tabular-nums">
        {vessel.missing_mandatory}
      </td>
      <td className="px-4 py-3 whitespace-nowrap">
        <ComplianceBar percentage={vessel.compliance_percentage} />
      </td>
    </tr>
  )
}

export function ReportsPage() {
  const missingQuery = useMissingMandatory()
  const fleetQuery = useFleetSummary()

  const missingDocs = useMemo(() => missingQuery.data ?? [], [missingQuery.data])
  const fleetSummary = fleetQuery.data

  const isLoading = missingQuery.isLoading || fleetQuery.isLoading
  const isError = missingQuery.isError || fleetQuery.isError

  const handleCSVDownload = () => {
    const date = new Date().toISOString().split('T')[0]
    downloadCSV(`missing-mandatory-documents-${date}.csv`, missingDocs)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between print:hidden">
        <div>
          <div className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-navy-300" aria-hidden="true" />
            <h1 className="text-xl font-bold tracking-tight text-navy-50">
              Compliance Reports
            </h1>
          </div>
          <p className="mt-1 text-sm text-navy-400">
            Fleet-wide document compliance and missing mandatory document tracking
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleCSVDownload}
            disabled={missingDocs.length === 0}
            className="inline-flex items-center gap-2 rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm font-medium text-navy-100 transition-colors hover:bg-navy-700 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Download missing mandatory documents as CSV"
          >
            <FileText className="h-4 w-4" aria-hidden="true" />
            CSV
          </button>
          <button
            type="button"
            onClick={handlePDFDownload}
            disabled={isLoading}
            className="inline-flex items-center gap-2 rounded-lg bg-navy-600 px-4 py-2.5 text-sm font-medium text-navy-50 transition-colors hover:bg-navy-500 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Download or print reports as PDF"
          >
            <FileDown className="h-4 w-4" aria-hidden="true" />
            PDF
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center rounded-xl border border-navy-800 bg-navy-900 p-12 print:hidden">
          <Loader2 className="h-6 w-6 animate-spin text-navy-300" />
          <span className="ml-3 text-sm text-navy-300">Loading reports...</span>
        </div>
      )}

      {isError && !isLoading && (
        <div
          role="alert"
          className="flex items-center gap-3 rounded-xl border border-status-expired/40 bg-status-expired-bg/10 p-6 print:hidden"
        >
          <AlertCircle className="h-5 w-5 shrink-0 text-status-expired" />
          <p className="text-sm text-status-expired">
            Failed to load report data. Please try again later.
          </p>
        </div>
      )}

      {!isLoading && !isError && fleetSummary && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {FLEET_CARDS.map((card) => {
              const Icon = card.icon
              const value = fleetSummary[card.key]
              const displayValue = card.key === 'fleet_compliance_percentage'
                ? `${value}%`
                : String(value)
              return (
                <div
                  key={card.key}
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
                      className={cn('text-2xl font-bold tabular-nums', card.colorClass)}
                      aria-label={`${card.label}: ${displayValue}`}
                    >
                      {displayValue}
                    </span>
                  </div>
                  <p className="mt-2 text-xs font-medium text-navy-300">
                    {card.label}
                  </p>
                </div>
              )
            })}
          </div>

          {fleetSummary.vessels.length > 0 && (
            <div className="overflow-hidden rounded-xl border border-navy-800 bg-navy-900">
              <div className="border-b border-navy-800 px-4 py-3">
                <h2 className="text-sm font-semibold text-navy-100">
                  Per-Vessel Compliance Summary
                </h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-navy-800 bg-navy-800">
                    <tr>
                      <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                        Vessel
                      </th>
                      <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                        Crew
                      </th>
                      <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                        Documents
                      </th>
                      <th scope="col" className="px-4 py-3 font-semibold text-status-valid whitespace-nowrap">
                        Valid
                      </th>
                      <th scope="col" className="px-4 py-3 font-semibold text-status-expiring whitespace-nowrap">
                        Expiring
                      </th>
                      <th scope="col" className="px-4 py-3 font-semibold text-status-expired whitespace-nowrap">
                        Expired
                      </th>
                      <th scope="col" className="px-4 py-3 font-semibold text-status-rejected whitespace-nowrap">
                        Missing
                      </th>
                      <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                        Compliance
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-navy-800">
                    {fleetSummary.vessels.map((vessel) => (
                      <VesselSummaryRow key={vessel.vessel_id} vessel={vessel} />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {!isLoading && !isError && (
        <div className="overflow-hidden rounded-xl border border-navy-800 bg-navy-900">
          <div className="flex items-center justify-between border-b border-navy-800 px-4 py-3">
            <div className="flex items-center gap-2">
              <FileWarning className="h-4 w-4 text-status-rejected" aria-hidden="true" />
              <h2 className="text-sm font-semibold text-navy-100">
                Missing Mandatory Documents
              </h2>
            </div>
            <span className="text-xs text-navy-400 tabular-nums">
              {missingDocs.length} record{missingDocs.length === 1 ? '' : 's'}
            </span>
          </div>

          {missingDocs.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-12">
              <CheckCircle className="mb-3 h-8 w-8 text-status-valid" />
              <p className="text-sm text-navy-400">
                All mandatory documents are present across the fleet.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-navy-800 bg-navy-800">
                  <tr>
                    <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                      Seafarer
                    </th>
                    <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                      Rank
                    </th>
                    <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                      Vessel
                    </th>
                    <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                      Missing Document
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-navy-800">
                  {missingDocs.map((doc) => (
                    <tr
                      key={`${doc.seafarer_id}-${doc.doc_type_id}`}
                      className="transition-colors hover:bg-navy-800/50"
                    >
                      <td className="px-4 py-3 whitespace-nowrap font-medium text-navy-50">
                        {doc.seafarer_name}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-navy-200">
                        {doc.rank}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-navy-200">
                        {doc.vessel_name}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-status-rejected-bg/10 px-2.5 py-1 text-xs font-medium text-status-rejected">
                          <FileWarning className="h-3 w-3" aria-hidden="true" />
                          {doc.doc_type_name}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
