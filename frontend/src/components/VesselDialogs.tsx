import { useState } from 'react'
import { useVesselAction } from '../hooks/useReferenceData'
import { FLAG_OPTIONS, flagLabel } from '../lib/flags'
import type { Vessel } from '../types'
import { ActionButton } from './ActionButton'
import { ConfirmDialog } from './ConfirmDialog'
import { FIELD_CLASS, FormDialog, LABEL_CLASS } from './FormDialog'

/** Which vessel dialog is open: add, edit, or switch active on/off. */
export type VesselDialogState =
  | { kind: 'create' }
  | { kind: 'edit'; vessel: Vessel }
  | { kind: 'toggle'; vessel: Vessel }

export function VesselDialog({
  state,
  onClose,
}: {
  state: VesselDialogState
  onClose: () => void
}) {
  return state.kind === 'toggle' ? (
    <ToggleVessel vessel={state.vessel} onClose={onClose} />
  ) : (
    <VesselForm vessel={state.kind === 'edit' ? state.vessel : null} onClose={onClose} />
  )
}

/** The administrator's Edit and Deactivate/Reactivate buttons for one vessel. */
export function VesselActions({
  vessel,
  onOpen,
}: {
  vessel: Vessel
  onOpen: (dialog: VesselDialogState) => void
}) {
  return (
    <div className="flex justify-end gap-2">
      <ActionButton onClick={() => onOpen({ kind: 'edit', vessel })}>Edit</ActionButton>
      <ActionButton
        tone={vessel.active ? 'danger' : 'default'}
        onClick={() => onOpen({ kind: 'toggle', vessel })}
      >
        {vessel.active ? 'Deactivate' : 'Reactivate'}
      </ActionButton>
    </div>
  )
}

function VesselForm({ vessel, onClose }: { vessel: Vessel | null; onClose: () => void }) {
  const [name, setName] = useState(vessel?.name ?? '')
  const [imo, setImo] = useState(vessel?.imo_number ?? '')
  const [flag, setFlag] = useState(vessel?.flag ?? '')
  const action = useVesselAction()
  const body = { name: name.trim(), imo_number: imo.trim(), flag }
  const canSubmit = !!body.name && /^[0-9]{7}$/.test(body.imo_number) && !!flag

  return (
    <FormDialog
      title={vessel ? 'Edit vessel' : 'Add vessel'}
      subtitle={vessel?.name}
      submitLabel={vessel ? 'Save' : 'Add vessel'}
      onSubmit={() =>
        action.mutate(vessel ? { kind: 'edit', id: vessel.id, body } : { kind: 'create', body }, {
          onSuccess: onClose,
        })
      }
      onClose={onClose}
      pending={action.isPending}
      canSubmit={canSubmit}
      error={action.error}
    >
      <div>
        <label htmlFor="vessel-name" className={LABEL_CLASS}>
          Name
        </label>
        <input
          id="vessel-name"
          required
          maxLength={200}
          value={name}
          onChange={(e) => setName(e.target.value)}
          className={FIELD_CLASS}
        />
      </div>
      <div>
        <label htmlFor="vessel-imo" className={LABEL_CLASS}>
          IMO number
        </label>
        <input
          id="vessel-imo"
          required
          inputMode="numeric"
          pattern="[0-9]{7}"
          maxLength={7}
          value={imo}
          onChange={(e) => setImo(e.target.value)}
          className={FIELD_CLASS}
          placeholder="7 digits"
        />
      </div>
      <div>
        <label htmlFor="vessel-flag" className={LABEL_CLASS}>
          Flag
        </label>
        <select
          id="vessel-flag"
          required
          value={flag}
          onChange={(e) => setFlag(e.target.value)}
          className={FIELD_CLASS}
        >
          <option value="" disabled>
            Pick the flag
          </option>
          {FLAG_OPTIONS.map((f) => (
            <option key={f.code} value={f.code}>
              {f.label}
            </option>
          ))}
        </select>
        {vessel && flag !== vessel.flag && (
          <p className="mt-1 text-xs text-status-expiring">
            Only the current flag is kept: {flagLabel(vessel.flag)} is replaced.
          </p>
        )}
      </div>
    </FormDialog>
  )
}

function ToggleVessel({ vessel, onClose }: { vessel: Vessel; onClose: () => void }) {
  const action = useVesselAction()
  const kind = vessel.active ? 'deactivate' : 'reactivate'
  return (
    <ConfirmDialog
      title={vessel.active ? 'Deactivate vessel' : 'Reactivate vessel'}
      subtitle={vessel.name}
      confirmLabel={vessel.active ? 'Deactivate' : 'Reactivate'}
      onConfirm={() => action.mutate({ kind, id: vessel.id }, { onSuccess: onClose })}
      onClose={onClose}
      pending={action.isPending}
      error={action.error}
    >
      {vessel.active
        ? 'The vessel and its history are kept, but it can no longer be picked for new assignments.'
        : 'The vessel can be picked for new assignments again.'}
    </ConfirmDialog>
  )
}
