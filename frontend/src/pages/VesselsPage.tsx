import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useVessels } from '../hooks/useReferenceData'
import { useCanReportOnVessel } from '../hooks/useReports'
import { flagLabel } from '../lib/flags'
import { ActionButton } from '../components/ActionButton'
import { ErrorNote } from '../components/ErrorNote'
import { ReportDownloads } from '../components/ReportDownloads'
import { StateBadge } from '../components/StateBadge'
import { VesselActions, VesselDialog, type VesselDialogState } from '../components/VesselDialogs'

/** The fleet (FR-05). Administrators maintain it; crewing officers read it. */
export function VesselsPage() {
  const { role } = useAuth()
  const isAdmin = role === 'administrator'
  const [withoutOfficer, setWithoutOfficer] = useState(false)
  const { data: vessels, isLoading, error } = useVessels(withoutOfficer)
  const [dialog, setDialog] = useState<VesselDialogState | null>(null)
  const sorted = vessels ? [...vessels].sort((a, b) => Number(b.active) - Number(a.active)) : []
  const canReport = useCanReportOnVessel()
  const columns = isAdmin ? 6 : 5

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-medium text-ink">Vessels</h2>
          <p className="mt-1 text-sm text-ink-faint">
            The company's fleet with each vessel's current flag.
            {isAdmin && ' Vessels are deactivated, never deleted.'}
          </p>
        </div>
        {isAdmin && (
          <ActionButton tone="primary" onClick={() => setDialog({ kind: 'create' })}>
            <Plus className="h-4 w-4" />
            Add vessel
          </ActionButton>
        )}
      </div>

      <label className="flex items-center gap-2 text-sm text-ink-muted">
        <input
          type="checkbox"
          checked={withoutOfficer}
          onChange={(e) => setWithoutOfficer(e.target.checked)}
          className="h-4 w-4 rounded border-line-strong bg-canvas"
        />
        Only vessels with no active Responsible Officer
      </label>

      {error && <ErrorNote message={error.message} />}

      <div className="overflow-x-auto rounded-md border border-line bg-canvas">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line bg-surface text-xs text-ink-faint">
            <tr>
              <th scope="col" className="px-4 py-3">Name</th>
              <th scope="col" className="px-4 py-3">IMO number</th>
              <th scope="col" className="px-4 py-3">Flag</th>
              <th scope="col" className="px-4 py-3">Status</th>
              <th scope="col" className="px-4 py-3">Status Report</th>
              {isAdmin && (
                <th scope="col" className="px-4 py-3 text-right">Actions</th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {isLoading && (
              <tr>
                <td colSpan={columns} className="px-4 py-6 text-center text-ink-faint">
                  Loading…
                </td>
              </tr>
            )}
            {vessels?.length === 0 && (
              <tr>
                <td colSpan={columns} className="px-4 py-6 text-center text-ink-faint">
                  {withoutOfficer ? 'Every vessel has an active Responsible Officer.' : 'No vessels yet.'}
                </td>
              </tr>
            )}
            {sorted.map((vessel) => (
              <tr key={vessel.id}>
                <td className="px-4 py-3">
                  <Link
                    to={`/vessels/${vessel.id}`}
                    className="font-medium text-ink underline-offset-2 hover:underline"
                  >
                    {vessel.name}
                  </Link>
                </td>
                <td className="px-4 py-3 font-mono text-ink-muted">{vessel.imo_number}</td>
                <td className="px-4 py-3 text-ink-muted">{flagLabel(vessel.flag)}</td>
                <td className="px-4 py-3">
                  <StateBadge on={vessel.active} label={vessel.active ? 'Active' : 'Deactivated'} />
                </td>
                <td className="px-4 py-3">
                  {canReport(vessel.id) && (
                    <ReportDownloads kind="vessel" id={vessel.id} label={`${vessel.name}'s Status Report`} />
                  )}
                </td>
                {isAdmin && (
                  <td className="px-4 py-3">
                    <VesselActions vessel={vessel} onOpen={setDialog} />
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {dialog && <VesselDialog state={dialog} onClose={() => setDialog(null)} />}
    </div>
  )
}
