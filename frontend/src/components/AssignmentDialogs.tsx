import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAssignmentAction } from '../hooks/useAssignments'
import { usePositions, useVessels } from '../hooks/useReferenceData'
import { fullName } from '../hooks/useSeafarers'
import { cn } from '../lib/cn'
import { BADGE_TONE } from '../lib/badgeTone'
import { ASSIGNMENT_STATE_LABELS, type Assignment, type AssignmentState, type Seafarer } from '../types'
import { ActionButton } from './ActionButton'
import { Field, FIELD_CLASS, FormDialog } from './FormDialog'
import { Table } from './Table'

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
  upcoming: BADGE_TONE.warn,
  under_way: BADGE_TONE.ok,
  finished: BADGE_TONE.neutral,
  cancelled: cn(BADGE_TONE.muted, 'line-through'),
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
  return (
    <Table
      head={[
        show === 'vessel' ? 'Vessel' : 'Seafarer',
        'Position',
        'From',
        'To',
        'State',
        { label: 'Actions', className: 'text-right' },
      ]}
      empty={assignments?.length === 0 ? empty : null}
    >
      {assignments?.map((a) => (
        <tr key={a.id}>
          <td className="px-4 py-3">
            {show === 'vessel' ? (
              <Link to={`/vessels/${a.vessel_id}`} className="text-ink hover:underline">
                {a.vessel_name}
              </Link>
            ) : (
              <Link to={`/seafarers/${a.seafarer_id}`} className="text-ink hover:underline">
                {a.seafarer_first_name} {a.seafarer_last_name}
              </Link>
            )}
          </td>
          <td className="px-4 py-3 text-ink-muted">
            {a.position_name}
            {a.position_differs && (
              <span
                className="ml-2 text-xs text-warning"
                title="Differs from the held Position"
              >
                (not the held Position)
              </span>
            )}
          </td>
          <td className="px-4 py-3 text-ink-muted">{a.start_date}</td>
          <td className="px-4 py-3 text-ink-muted">{a.end_date}</td>
          <td className="px-4 py-3">
            <span title={a.cancel_reason ?? undefined}>
              <AssignmentStateBadge state={a.state} />
            </span>
          </td>
          <td className="px-4 py-3">
            {isChangeable(a) && (
              <div className="flex items-center justify-end gap-2">
                <Link
                  to={`/assignments/${a.id}/readiness`}
                  className="inline-flex items-center gap-1.5 h-8 shrink-0 whitespace-nowrap rounded-md border border-line-strong bg-canvas px-3 text-sm font-medium text-ink hover:bg-surface-active focus:outline-none focus:ring-2 focus:ring-accent/40"
                >
                  Readiness
                </Link>
                {onEdit && <ActionButton onClick={() => onEdit(a)}>Edit</ActionButton>}
                {onCancel && (
                  <ActionButton tone="danger" onClick={() => onCancel(a)}>
                    Cancel
                  </ActionButton>
                )}
              </div>
            )}
          </td>
        </tr>
      ))}
    </Table>
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
      <Field id="assignment-vessel" label="Vessel">
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
      </Field>
      <Field id="assignment-position" label="Position">
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
          <p className="mt-1 text-xs text-warning">
            This differs from the held Position ({seafarer.position_name}). The held Position
            doesn't change by itself: edit the seafarer to record a promotion.
          </p>
        )}
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="assignment-start" label="From">
          <input
            id="assignment-start"
            type="date"
            required
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className={FIELD_CLASS}
          />
        </Field>
        <Field id="assignment-end" label="To (included)">
          <input
            id="assignment-end"
            type="date"
            required
            min={startDate || undefined}
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className={FIELD_CLASS}
          />
        </Field>
      </div>
      {!datesInOrder && (
        <p className="text-xs text-danger">The end date can't be before the start date.</p>
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
      <p className="text-sm text-ink-muted">
        Cancelling is permanent. The Assignment is kept, marked cancelled, with the reason.
      </p>
      <Field id="assignment-cancel-reason" label="Reason">
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
      </Field>
    </FormDialog>
  )
}
