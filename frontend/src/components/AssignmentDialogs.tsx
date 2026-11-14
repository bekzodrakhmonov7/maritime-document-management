import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAssignmentAction } from '../hooks/useAssignments'
import { usePositions, useVessels } from '../hooks/useReferenceData'
import { fullName } from '../hooks/useSeafarers'
import { cn } from '../lib/cn'
import { ASSIGNMENT_STATE_LABELS, type Assignment, type AssignmentState, type Seafarer } from '../types'
import { ActionButton } from './ActionButton'
import { FIELD_CLASS, FormDialog, LABEL_CLASS } from './FormDialog'

/** Which Assignment dialog is open: plan, edit or cancel. */
export type AssignmentDialogState =
  | { kind: 'create'; seafarer: Seafarer }
  | { kind: 'edit'; seafarer: Seafarer; assignment: Assignment }
  | { kind: 'cancel'; assignment: Assignment }

export function AssignmentDialog({
  state,
  onClose,
}: {
  state: AssignmentDialogState
  onClose: () => void
}) {
  if (state.kind === 'cancel') return <CancelAssignment assignment={state.assignment} onClose={onClose} />
  return (
    <AssignmentForm
      seafarer={state.seafarer}
      assignment={state.kind === 'edit' ? state.assignment : null}
      onClose={onClose}
    />
  )
}

const STATE_STYLE: Record<AssignmentState, string> = {
  upcoming: 'bg-status-expiring-bg/10 text-status-expiring',
  under_way: 'bg-status-valid-bg/10 text-status-valid',
  finished: 'bg-navy-800 text-navy-300',
  cancelled: 'bg-navy-800 text-navy-500 line-through',
}

export function AssignmentStateBadge({ state }: { state: AssignmentState }) {
  return (
    <span className={cn('rounded-full px-2.5 py-1 text-xs font-medium', STATE_STYLE[state])}>
      {ASSIGNMENT_STATE_LABELS[state]}
    </span>
  )
}

/** Finished and cancelled Assignments are read-only. */
const isChangeable = (assignment: Assignment) =>
  assignment.state === 'upcoming' || assignment.state === 'under_way'

/** One table for a seafarer's Assignments or a vessel's crew. */
export function AssignmentsTable({
  assignments,
  show,
  onEdit,
  onCancel,
  empty,
}: {
  assignments: Assignment[] | undefined
  /** The column that varies: the vessel (seafarer page) or the seafarer (vessel page). */
  show: 'vessel' | 'seafarer'
  onEdit?: (assignment: Assignment) => void
  onCancel?: (assignment: Assignment) => void
  empty: string
}) {
  const hasActions = !!(onEdit || onCancel)
  const columns = hasActions ? 6 : 5
  return (
    <div className="overflow-x-auto rounded-xl border border-navy-800 bg-navy-900">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-navy-800 text-xs uppercase tracking-wider text-navy-400">
          <tr>
            <th scope="col" className="px-4 py-3">{show === 'vessel' ? 'Vessel' : 'Seafarer'}</th>
            <th scope="col" className="px-4 py-3">Position</th>
            <th scope="col" className="px-4 py-3">From</th>
            <th scope="col" className="px-4 py-3">To</th>
            <th scope="col" className="px-4 py-3">State</th>
            {hasActions && <th scope="col" className="px-4 py-3 text-right">Actions</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-navy-800">
          {assignments?.length === 0 && (
            <tr>
              <td colSpan={columns} className="px-4 py-6 text-center text-navy-400">
                {empty}
              </td>
            </tr>
          )}
          {assignments?.map((a) => (
            <tr key={a.id}>
              <td className="px-4 py-3">
                {show === 'vessel' ? (
                  <Link to={`/vessels/${a.vessel_id}`} className="text-navy-50 hover:underline">
                    {a.vessel_name}
                  </Link>
                ) : (
                  <Link to={`/seafarers/${a.seafarer_id}`} className="text-navy-50 hover:underline">
                    {a.seafarer_first_name} {a.seafarer_last_name}
                  </Link>
                )}
              </td>
              <td className="px-4 py-3 text-navy-200">
                {a.position_name}
                {a.position_differs && (
                  <span
                    className="ml-2 text-xs text-status-expiring"
                    title="Differs from the held Position"
                  >
                    (not the held Position)
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-navy-200">{a.start_date}</td>
              <td className="px-4 py-3 text-navy-200">{a.end_date}</td>
              <td className="px-4 py-3">
                <span title={a.cancel_reason ?? undefined}>
                  <AssignmentStateBadge state={a.state} />
                </span>
              </td>
              {hasActions && (
                <td className="px-4 py-3">
                  {isChangeable(a) && (
                    <div className="flex justify-end gap-2">
                      {onEdit && <ActionButton onClick={() => onEdit(a)}>Edit</ActionButton>}
                      {onCancel && (
                        <ActionButton tone="danger" onClick={() => onCancel(a)}>
                          Cancel
                        </ActionButton>
                      )}
                    </div>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AssignmentForm({
  seafarer,
  assignment,
  onClose,
}: {
  seafarer: Seafarer
  assignment: Assignment | null
  onClose: () => void
}) {
  const [vesselId, setVesselId] = useState(assignment ? String(assignment.vessel_id) : '')
  const [positionId, setPositionId] = useState(String(assignment?.position_id ?? seafarer.position_id))
  const [startDate, setStartDate] = useState(assignment?.start_date ?? '')
  const [endDate, setEndDate] = useState(assignment?.end_date ?? '')
  const { data: vessels } = useVessels()
  const { data: positions } = usePositions()
  const action = useAssignmentAction()

  // Only active vessels and current Positions; an edit may keep ones switched off since.
  const pickableVessels = (vessels ?? []).filter((v) => v.active || v.id === assignment?.vessel_id)
  const pickablePositions = (positions ?? []).filter(
    (p) => !p.retired || p.id === assignment?.position_id,
  )
  const body = {
    vessel_id: Number(vesselId),
    position_id: Number(positionId),
    start_date: startDate,
    end_date: endDate,
  }
  const datesInOrder = !startDate || !endDate || endDate >= startDate
  const canSubmit = !!vesselId && !!positionId && !!startDate && !!endDate && datesInOrder
  const heldPositionDiffers = !!positionId && Number(positionId) !== seafarer.position_id

  return (
    <FormDialog
      title={assignment ? 'Edit Assignment' : 'Plan Assignment'}
      subtitle={fullName(seafarer)}
      submitLabel={assignment ? 'Save' : 'Plan Assignment'}
      onSubmit={() =>
        action.mutate(
          assignment
            ? { kind: 'edit', id: assignment.id, body }
            : { kind: 'create', body: { ...body, seafarer_id: seafarer.id } },
          { onSuccess: onClose },
        )
      }
      onClose={onClose}
      pending={action.isPending}
      canSubmit={canSubmit}
      error={action.error}
    >
      <div>
        <label htmlFor="assignment-vessel" className={LABEL_CLASS}>
          Vessel
        </label>
        <select
          id="assignment-vessel"
          required
          value={vesselId}
          onChange={(e) => setVesselId(e.target.value)}
          className={FIELD_CLASS}
        >
          <option value="" disabled>
            Pick a vessel
          </option>
          {pickableVessels.map((v) => (
            <option key={v.id} value={v.id}>
              {v.active ? v.name : `${v.name} (deactivated)`}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="assignment-position" className={LABEL_CLASS}>
          Position
        </label>
        <select
          id="assignment-position"
          required
          value={positionId}
          onChange={(e) => setPositionId(e.target.value)}
          className={FIELD_CLASS}
        >
          {pickablePositions.map((p) => (
            <option key={p.id} value={p.id}>
              {p.retired ? `${p.name} (retired)` : p.name}
            </option>
          ))}
        </select>
        {heldPositionDiffers && (
          <p className="mt-1 text-xs text-status-expiring">
            This differs from the held Position ({seafarer.position_name}). The held Position
            doesn't change by itself: edit the seafarer to record a promotion.
          </p>
        )}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="assignment-start" className={LABEL_CLASS}>
            From
          </label>
          <input
            id="assignment-start"
            type="date"
            required
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className={FIELD_CLASS}
          />
        </div>
        <div>
          <label htmlFor="assignment-end" className={LABEL_CLASS}>
            To (included)
          </label>
          <input
            id="assignment-end"
            type="date"
            required
            min={startDate || undefined}
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className={FIELD_CLASS}
          />
        </div>
      </div>
      {!datesInOrder && (
        <p className="text-xs text-status-expired">The end date can't be before the start date.</p>
      )}
    </FormDialog>
  )
}

function CancelAssignment({ assignment, onClose }: { assignment: Assignment; onClose: () => void }) {
  const [reason, setReason] = useState('')
  const action = useAssignmentAction()
  const trimmed = reason.trim()

  return (
    <FormDialog
      title="Cancel Assignment"
      subtitle={`${assignment.vessel_name} · ${assignment.start_date} to ${assignment.end_date}`}
      submitLabel="Cancel Assignment"
      onSubmit={() =>
        action.mutate({ kind: 'cancel', id: assignment.id, reason: trimmed }, { onSuccess: onClose })
      }
      onClose={onClose}
      pending={action.isPending}
      canSubmit={!!trimmed}
      error={action.error}
    >
      <p className="text-sm text-navy-300">
        Cancelling is permanent. The Assignment is kept, marked cancelled, with the reason.
      </p>
      <div>
        <label htmlFor="assignment-cancel-reason" className={LABEL_CLASS}>
          Reason
        </label>
        <textarea
          id="assignment-cancel-reason"
          required
          rows={3}
          maxLength={500}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className={FIELD_CLASS}
          placeholder="Recorded in the Audit Log"
        />
      </div>
    </FormDialog>
  )
}
