import { useState } from 'react'
import { fullName, useSeafarerAction } from '../hooks/useSeafarers'
import { usePositions } from '../hooks/useReferenceData'
import { FLAG_OPTIONS } from '../lib/flags'
import type { Seafarer } from '../types'
import { ActionButton } from './ActionButton'
import { ConfirmDialog } from './ConfirmDialog'
import { Field, FIELD_CLASS, FormDialog } from './FormDialog'
import { StateBadge } from './StateBadge'

/** Which seafarer dialog is open: add, edit, set Inactive or reactivate. */
export type SeafarerDialogState =
  | { kind: 'create' }
  | { kind: 'edit'; seafarer: Seafarer }
  | { kind: 'toggle'; seafarer: Seafarer }

export function SeafarerDialog({
  state,
  onClose,
}: {
  state: SeafarerDialogState
  onClose: () => void
}) {
  if (state.kind === 'create') return <SeafarerForm seafarer={null} onClose={onClose} />
  if (state.kind === 'edit') return <SeafarerForm seafarer={state.seafarer} onClose={onClose} />
  return state.seafarer.inactive_since ? (
    <Reactivate seafarer={state.seafarer} onClose={onClose} />
  ) : (
    <SetInactive seafarer={state.seafarer} onClose={onClose} />
  )
}

/** Edit and Set Inactive / Reactivate buttons for one seafarer. */
export function SeafarerActions({
  seafarer,
  onOpen,
}: {
  seafarer: Seafarer
  onOpen: (dialog: SeafarerDialogState) => void
}) {
  const inactive = seafarer.inactive_since !== null
  return (
    <div className="flex justify-end gap-2">
      <ActionButton onClick={() => onOpen({ kind: 'edit', seafarer })}>Edit</ActionButton>
      <ActionButton
        tone={inactive ? 'default' : 'danger'}
        onClick={() => onOpen({ kind: 'toggle', seafarer })}
      >
        {inactive ? 'Reactivate' : 'Set Inactive'}
      </ActionButton>
    </div>
  )
}

/** "Active" or "Inactive". */
export function SeafarerStatusBadge({ seafarer }: { seafarer: Seafarer }) {
  const active = seafarer.inactive_since === null
  return <StateBadge on={active} label={active ? 'Active' : 'Inactive'} />
}

function SeafarerForm({ seafarer, onClose }: { seafarer: Seafarer | null; onClose: () => void }) {
  const [firstName, setFirstName] = useState(seafarer?.first_name ?? '')
  const [lastName, setLastName] = useState(seafarer?.last_name ?? '')
  const [dateOfBirth, setDateOfBirth] = useState(seafarer?.date_of_birth ?? '')
  const [nationality, setNationality] = useState(seafarer?.nationality ?? '')
  const [positionId, setPositionId] = useState(seafarer ? String(seafarer.position_id) : '')
  const { data: positions } = usePositions()
  const action = useSeafarerAction()

  // Only current Positions can be picked; a held one retired since stays selectable.
  const pickable = (positions ?? []).filter(
    (p) => !p.retired || p.id === seafarer?.position_id,
  )
  const body = {
    first_name: firstName.trim(),
    last_name: lastName.trim(),
    date_of_birth: dateOfBirth || null,
    nationality: nationality || null,
    position_id: Number(positionId),
  }
  const canSubmit = !!body.first_name && !!body.last_name && !!positionId

  return (
    <FormDialog
      title={seafarer ? 'Edit seafarer' : 'Add seafarer'}
      subtitle={seafarer ? fullName(seafarer) : undefined}
      submitLabel={seafarer ? 'Save' : 'Add seafarer'}
      onSubmit={() =>
        action.mutate(
          seafarer ? { kind: 'edit', id: seafarer.id, body } : { kind: 'create', body },
          { onSuccess: onClose },
        )
      }
      onClose={onClose}
      pending={action.isPending}
      canSubmit={canSubmit}
      error={action.error}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="seafarer-first-name" label="First name">
          <input
            id="seafarer-first-name"
            required
            maxLength={100}
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            className={FIELD_CLASS}
          />
        </Field>
        <Field id="seafarer-last-name" label="Last name">
          <input
            id="seafarer-last-name"
            required
            maxLength={100}
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            className={FIELD_CLASS}
          />
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="seafarer-dob" label="Date of birth">
          <input
            id="seafarer-dob"
            type="date"
            value={dateOfBirth}
            onChange={(e) => setDateOfBirth(e.target.value)}
            className={FIELD_CLASS}
          />
        </Field>
        <Field id="seafarer-nationality" label="Nationality">
          <select
            id="seafarer-nationality"
            value={nationality}
            onChange={(e) => setNationality(e.target.value)}
            className={FIELD_CLASS}
          >
            <option value="">Not recorded</option>
            {FLAG_OPTIONS.map((c) => (
              <option key={c.code} value={c.code}>
                {c.label}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field id="seafarer-position" label="Position">
        <select
          id="seafarer-position"
          required
          value={positionId}
          onChange={(e) => setPositionId(e.target.value)}
          className={FIELD_CLASS}
        >
          <option value="" disabled>
            Pick the held Position
          </option>
          {pickable.map((p) => (
            <option key={p.id} value={p.id}>
              {p.retired ? `${p.name} (retired)` : p.name}
            </option>
          ))}
        </select>
        {seafarer && Number(positionId) !== seafarer.position_id && (
          <p className="mt-1 text-xs text-warning">
            The held Position changes from {seafarer.position_name}. The change is recorded.
          </p>
        )}
      </Field>
    </FormDialog>
  )
}

function SetInactive({ seafarer, onClose }: { seafarer: Seafarer; onClose: () => void }) {
  const [reason, setReason] = useState('')
  const action = useSeafarerAction()
  const trimmed = reason.trim()

  return (
    <FormDialog
      title="Set Inactive"
      subtitle={fullName(seafarer)}
      submitLabel="Set Inactive"
      onSubmit={() =>
        action.mutate({ kind: 'set-inactive', id: seafarer.id, reason: trimmed }, { onSuccess: onClose })
      }
      onClose={onClose}
      pending={action.isPending}
      canSubmit={!!trimmed}
      error={action.error}
    >
      <p className="text-sm text-ink-muted">
        The record is kept but drops out of the working lists. It can be reactivated later.
      </p>
      <Field id="seafarer-inactive-reason" label="Reason">
        <textarea
          id="seafarer-inactive-reason"
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

function Reactivate({ seafarer, onClose }: { seafarer: Seafarer; onClose: () => void }) {
  const action = useSeafarerAction()
  return (
    <ConfirmDialog
      title="Reactivate seafarer"
      subtitle={fullName(seafarer)}
      confirmLabel="Reactivate"
      onConfirm={() => action.mutate({ kind: 'reactivate', id: seafarer.id }, { onSuccess: onClose })}
      onClose={onClose}
      pending={action.isPending}
      error={action.error}
    >
      The seafarer is tracked actively again and shows in the working lists.
    </ConfirmDialog>
  )
}
