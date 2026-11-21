import { useState } from 'react'
import { Plus } from 'lucide-react'
import { usePositionAction, usePositions } from '../hooks/useReferenceData'
import type { Position } from '../types'
import { ActionButton } from '../components/ActionButton'
import { ErrorNote } from '../components/ErrorNote'
import { FIELD_CLASS, FormDialog, LABEL_CLASS } from '../components/FormDialog'
import { RetirableActions, RetireDialog, type RetireKind } from '../components/RetireDialog'
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
          <h2 className="text-xl font-medium text-ink">Positions</h2>
          <p className="mt-1 text-sm text-ink-faint">
            The jobs seafarers hold or are planned for. A Position in use is retired, not deleted.
          </p>
        </div>
        <ActionButton tone="primary" onClick={() => setDialog({ kind: 'create' })}>
          <Plus className="h-4 w-4" />
          Add Position
        </ActionButton>
      </div>

      {error && <ErrorNote message={error.message} />}

      <div className="overflow-x-auto rounded-md border border-line bg-canvas">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line bg-surface text-xs text-ink-faint">
            <tr>
              <th scope="col" className="px-4 py-3">Name</th>
              <th scope="col" className="px-4 py-3">Status</th>
              <th scope="col" className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {isLoading && (
              <tr>
                <td colSpan={3} className="px-4 py-6 text-center text-ink-faint">
                  Loading…
                </td>
              </tr>
            )}
            {positions?.length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-6 text-center text-ink-faint">
                  No Positions yet.
                </td>
              </tr>
            )}
            {positions?.map((position) => (
              <tr key={position.id}>
                <td className="px-4 py-3 text-ink">{position.name}</td>
                <td className="px-4 py-3">
                  <StateBadge on={!position.retired} label={position.retired ? 'Retired' : 'In use'} />
                </td>
                <td className="px-4 py-3">
                  <RetirableActions
                    retired={position.retired}
                    onEdit={() => setDialog({ kind: 'edit', position })}
                    onRetire={(kind) => setDialog({ kind, position })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(dialog?.kind === 'create' || dialog?.kind === 'edit') && (
        <PositionForm
          position={dialog.kind === 'edit' ? dialog.position : null}
          onClose={() => setDialog(null)}
        />
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
