import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useVesselCrew } from '../hooks/useAssignments'
import { useVessel } from '../hooks/useReferenceData'
import { flagLabel } from '../lib/flags'
import { AssignmentsTable } from '../components/AssignmentDialogs'
import { ErrorNote } from '../components/ErrorNote'
import { ResponsibleOfficers } from '../components/ResponsibleOfficers'
import { StateBadge } from '../components/StateBadge'
import { VesselActions, VesselDialog, type VesselDialogState } from '../components/VesselDialogs'

/** One vessel's details, Responsible Officers and crew under way and upcoming.
 * Read-only for crewing officers, who see only the crew within their Scope. */
export function VesselPage() {
  const { id } = useParams()
  const { role } = useAuth()
  const isAdmin = role === 'administrator'
  const { data: vessel, isLoading, error } = useVessel(Number(id))
  const crew = useVesselCrew(Number(id))
  const [dialog, setDialog] = useState<VesselDialogState | null>(null)

  return (
    <div className="max-w-3xl space-y-6">
      <Link to="/vessels" className="inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" />
        All vessels
      </Link>

      {isLoading && <p className="text-sm text-ink-faint">Loading…</p>}
      {error && <ErrorNote message={error.message} />}

      {vessel && (
        <>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-medium text-ink">{vessel.name}</h2>
              <StateBadge on={vessel.active} label={vessel.active ? 'Active' : 'Deactivated'} />
            </div>
            {isAdmin && <VesselActions vessel={vessel} onOpen={setDialog} />}
          </div>

          <dl className="grid gap-4 rounded-md border border-line bg-canvas p-6 sm:grid-cols-2">
            <div>
              <dt className="text-xs text-ink-faint">IMO number</dt>
              <dd className="mt-1 font-mono text-ink">{vessel.imo_number}</dd>
            </div>
            <div>
              <dt className="text-xs text-ink-faint">Flag</dt>
              <dd className="mt-1 text-ink">{flagLabel(vessel.flag)}</dd>
            </div>
          </dl>

          <ResponsibleOfficers vesselId={vessel.id} isAdmin={isAdmin} />

          <section className="space-y-3">
            <h3 className="text-lg font-medium text-ink">Crew under way and upcoming</h3>
            {crew.error && <ErrorNote message={crew.error.message} />}
            <AssignmentsTable
              assignments={crew.data}
              show="seafarer"
              empty={
                isAdmin
                  ? 'Nobody is on board or planned.'
                  : 'Nobody on board or planned that you are responsible for.'
              }
            />
          </section>
        </>
      )}

      {dialog && <VesselDialog state={dialog} onClose={() => setDialog(null)} />}
    </div>
  )
}
