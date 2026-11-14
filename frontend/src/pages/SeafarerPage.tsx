import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Plus } from 'lucide-react'
import { useSeafarerAssignments } from '../hooks/useAssignments'
import { fullName, useSeafarer } from '../hooks/useSeafarers'
import { flagLabel } from '../lib/flags'
import { ActionButton } from '../components/ActionButton'
import {
  AssignmentDialog,
  AssignmentsTable,
  type AssignmentDialogState,
} from '../components/AssignmentDialogs'
import { ErrorNote } from '../components/ErrorNote'
import {
  SeafarerActions,
  SeafarerDialog,
  SeafarerStatusBadge,
  type SeafarerDialogState,
} from '../components/SeafarerDialogs'

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-navy-400">{label}</dt>
      <dd className="mt-1 text-navy-50">{children}</dd>
    </div>
  )
}

/** One seafarer's record: personal details, held Position, Current Vessel and
 * Assignments. Later slices add documents (S7) and missing documents (S10). */
export function SeafarerPage() {
  const { id } = useParams()
  const { data: seafarer, isLoading, error } = useSeafarer(Number(id))
  const assignments = useSeafarerAssignments(Number(id))
  const [dialog, setDialog] = useState<SeafarerDialogState | null>(null)
  const [assignmentDialog, setAssignmentDialog] = useState<AssignmentDialogState | null>(null)

  return (
    <div className="max-w-3xl space-y-6">
      <Link
        to="/seafarers"
        className="inline-flex items-center gap-1 text-sm text-navy-300 hover:text-navy-100"
      >
        <ArrowLeft className="h-4 w-4" />
        All seafarers
      </Link>

      {isLoading && <p className="text-sm text-navy-400">Loading…</p>}
      {error && <ErrorNote message={error.message} />}

      {seafarer && (
        <>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <h2 className="text-2xl font-semibold text-navy-50">{fullName(seafarer)}</h2>
              <SeafarerStatusBadge seafarer={seafarer} />
            </div>
            <SeafarerActions seafarer={seafarer} onOpen={setDialog} />
          </div>

          {seafarer.inactive_since && (
            <p className="rounded-lg border border-navy-700 bg-navy-900 p-3 text-sm text-navy-300">
              Inactive since {new Date(seafarer.inactive_since).toLocaleDateString()}:{' '}
              {seafarer.inactive_reason}
            </p>
          )}

          <dl className="grid gap-4 rounded-xl border border-navy-800 bg-navy-900 p-6 sm:grid-cols-2">
            <Detail label="Position">
              {seafarer.position_name}
              {seafarer.position_retired && (
                <span className="ml-2 text-xs text-navy-400">(retired Position)</span>
              )}
            </Detail>
            <Detail label="Nationality">
              {seafarer.nationality ? flagLabel(seafarer.nationality) : '—'}
            </Detail>
            <Detail label="Date of birth">{seafarer.date_of_birth ?? '—'}</Detail>
            <Detail label="Current vessel">
              {seafarer.current_vessel_id ? (
                <Link to={`/vessels/${seafarer.current_vessel_id}`} className="hover:underline">
                  {seafarer.current_vessel_name}
                </Link>
              ) : (
                'Ashore'
              )}
            </Detail>
          </dl>

          <section className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-lg font-semibold text-navy-50">Assignments</h3>
              {!seafarer.inactive_since && (
                <ActionButton
                  tone="primary"
                  onClick={() => setAssignmentDialog({ kind: 'create', seafarer })}
                >
                  <Plus className="h-4 w-4" />
                  Plan Assignment
                </ActionButton>
              )}
            </div>
            {assignments.error && <ErrorNote message={assignments.error.message} />}
            <AssignmentsTable
              assignments={assignments.data}
              show="vessel"
              empty="No Assignments yet."
              onEdit={(assignment) => setAssignmentDialog({ kind: 'edit', seafarer, assignment })}
              onCancel={(assignment) => setAssignmentDialog({ kind: 'cancel', assignment })}
            />
          </section>
        </>
      )}

      {dialog && <SeafarerDialog state={dialog} onClose={() => setDialog(null)} />}
      {assignmentDialog && (
        <AssignmentDialog state={assignmentDialog} onClose={() => setAssignmentDialog(null)} />
      )}
    </div>
  )
}
