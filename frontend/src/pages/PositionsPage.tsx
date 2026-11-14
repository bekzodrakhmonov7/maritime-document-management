import { useState } from 'react'
import { Plus } from 'lucide-react'
import { usePositionAction, usePositions } from '../hooks/useReferenceData'
import type { Position } from '../types'
import { ActionButton } from '../components/ActionButton'
import { ErrorNote } from '../components/ErrorNote'
import { FIELD_CLASS, FormDialog, LABEL_CLASS } from '../components/FormDialog'
import { RetireDialog, type RetireKind } from '../components/RetireDialog'
import { StateBadge } from '../components/StateBadge'

type Dialog =
  | { kind: 'create' }
  | { kind: 'edit'; position: Position }
  | { kind: RetireKind; position: Position }

/** The managed list of Positions (administrators only). */
export function PositionsPage() {
  const { data: positions, isLoading, error } = usePositions()
  const [dialog, setDialog] = useState<Dialog | null>(null)

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold text-navy-50">Positions</h2>
          <p className="mt-1 text-sm text-navy-400">
            The jobs seafarers hold or are planned for. A Position in use is retired, not deleted.
          </p>
        </div>
        <ActionButton tone="primary" onClick={() => setDialog({ kind: 'create' })}>
          <Plus className="h-4 w-4" />
          Add Position
        </ActionButton>
      </div>

      {error && <ErrorNote message={error.message} />}

      <div className="overflow-x-auto rounded-xl border border-navy-800 bg-navy-900">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-navy-800 text-xs uppercase tracking-wider text-navy-400">
            <tr>
              <th scope="col" className="px-4 py-3">Name</th>
              <th scope="col" className="px-4 py-3">Status</th>
              <th scope="col" className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-navy-800">
            {isLoading && (
              <tr>
                <td colSpan={3} className="px-4 py-6 text-center text-navy-400">
                  Loading…
                </td>
              </tr>
            )}
            {positions?.length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-6 text-center text-navy-400">
                  No Positions yet.
                </td>
              </tr>
            )}
            {positions?.map((position) => (
              <tr key={position.id}>
                <td className="px-4 py-3 text-navy-50">{position.name}</td>
                <td className="px-4 py-3">
                  <StateBadge on={!position.retired} label={position.retired ? 'Retired' : 'In use'} />
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    <ActionButton onClick={() => setDialog({ kind: 'edit', position })}>Edit</ActionButton>
                    <ActionButton
                      onClick={() =>
                        setDialog({ kind: position.retired ? 'unretire' : 'retire', position })
                      }
                    >
                      {position.retired ? 'Bring back' : 'Retire'}
                    </ActionButton>
                    <ActionButton tone="danger" onClick={() => setDialog({ kind: 'delete', position })}>
                      Delete
                    </ActionButton>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {dialog?.kind === 'create' && <PositionForm position={null} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'edit' && (
        <PositionForm position={dialog.position} onClose={() => setDialog(null)} />
      )}
      {dialog && dialog.kind !== 'create' && dialog.kind !== 'edit' && (
        <RetireDialog
          collection="positions"
          noun="Position"
          row={dialog.position}
          kind={dialog.kind}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  )
}

function PositionForm({ position, onClose }: { position: Position | null; onClose: () => void }) {
  const [name, setName] = useState(position?.name ?? '')
  const action = usePositionAction()
  const body = { name: name.trim() }

  return (
    <FormDialog
      title={position ? 'Rename Position' : 'Add Position'}
      subtitle={position?.name}
      submitLabel={position ? 'Save' : 'Add Position'}
      onSubmit={() =>
        action.mutate(
          position ? { kind: 'edit', id: position.id, body } : { kind: 'create', body },
          { onSuccess: onClose },
        )
      }
      onClose={onClose}
      pending={action.isPending}
      canSubmit={!!body.name}
      error={action.error}
    >
      <div>
        <label htmlFor="position-name" className={LABEL_CLASS}>
          Name
        </label>
        <input
          id="position-name"
          required
          maxLength={200}
          value={name}
          onChange={(e) => setName(e.target.value)}
          className={FIELD_CLASS}
          placeholder="e.g. Chief Engineer"
        />
      </div>
    </FormDialog>
  )
}
