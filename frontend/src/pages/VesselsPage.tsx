import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useVessels } from '../hooks/useReferenceData'
import { flagLabel } from '../lib/flags'
import { ActionButton } from '../components/ActionButton'
import { ErrorNote } from '../components/ErrorNote'
import { StateBadge } from '../components/StateBadge'
import { VesselDialog, type VesselDialogState } from '../components/VesselDialogs'

/** The fleet (FR-05). Administrators maintain it; crewing officers read it. */
export function VesselsPage() {
  const { role } = useAuth()
  const isAdmin = role === 'administrator'
  const { data: vessels, isLoading, error } = useVessels()
  const [dialog, setDialog] = useState<VesselDialogState | null>(null)
  const sorted = vessels ? [...vessels].sort((a, b) => Number(b.active) - Number(a.active)) : []
  const columns = isAdmin ? 5 : 4

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold text-navy-50">Vessels</h2>
          <p className="mt-1 text-sm text-navy-400">
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

      {error && <ErrorNote message={error.message} />}

      <div className="overflow-x-auto rounded-xl border border-navy-800 bg-navy-900">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-navy-800 text-xs uppercase tracking-wider text-navy-400">
            <tr>
              <th scope="col" className="px-4 py-3">Name</th>
              <th scope="col" className="px-4 py-3">IMO number</th>
              <th scope="col" className="px-4 py-3">Flag</th>
              <th scope="col" className="px-4 py-3">Status</th>
              {isAdmin && (
                <th scope="col" className="px-4 py-3 text-right">Actions</th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-navy-800">
            {isLoading && (
              <tr>
                <td colSpan={columns} className="px-4 py-6 text-center text-navy-400">
                  Loading…
                </td>
              </tr>
            )}
            {vessels?.length === 0 && (
              <tr>
                <td colSpan={columns} className="px-4 py-6 text-center text-navy-400">
                  No vessels yet.
                </td>
              </tr>
            )}
            {sorted.map((vessel) => (
              <tr key={vessel.id}>
                <td className="px-4 py-3">
                  <Link
                    to={`/vessels/${vessel.id}`}
                    className="font-medium text-navy-50 underline-offset-2 hover:underline"
                  >
                    {vessel.name}
                  </Link>
                </td>
                <td className="px-4 py-3 font-mono text-navy-200">{vessel.imo_number}</td>
                <td className="px-4 py-3 text-navy-200">{flagLabel(vessel.flag)}</td>
                <td className="px-4 py-3">
                  <StateBadge on={vessel.active} label={vessel.active ? 'Active' : 'Deactivated'} />
                </td>
                {isAdmin && (
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      <ActionButton onClick={() => setDialog({ kind: 'edit', vessel })}>Edit</ActionButton>
                      <ActionButton
                        tone={vessel.active ? 'danger' : 'default'}
                        onClick={() => setDialog({ kind: 'toggle', vessel })}
                      >
                        {vessel.active ? 'Deactivate' : 'Reactivate'}
                      </ActionButton>
                    </div>
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
