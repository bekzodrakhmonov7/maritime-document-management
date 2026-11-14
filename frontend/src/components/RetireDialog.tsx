import { useReferenceAction } from '../hooks/useReferenceData'
import { ActionButton } from './ActionButton'
import { ConfirmDialog } from './ConfirmDialog'

export type RetireKind = 'retire' | 'unretire' | 'delete'

const TITLE: Record<RetireKind, string> = {
  retire: 'Retire',
  unretire: 'Bring back',
  delete: 'Delete',
}

const EXPLANATION: Record<RetireKind, string> = {
  retire:
    'It disappears from pickers and new records, but everything that already uses it stays as it is.',
  unretire: 'It can be picked again.',
  delete:
    'Only something that has never been used can be deleted. If it is in use, retire it instead.',
}

/** Retire, bring back or delete a Position or Document Type. */
export function RetireDialog({
  collection,
  noun,
  row,
  kind,
  onClose,
}: {
  collection: 'positions' | 'document-types'
  noun: string
  row: { id: number; name: string }
  kind: RetireKind
  onClose: () => void
}) {
  const action = useReferenceAction(collection)
  return (
    <ConfirmDialog
      title={`${TITLE[kind]} ${noun}`}
      subtitle={row.name}
      confirmLabel={TITLE[kind]}
      onConfirm={() => action.mutate({ kind, id: row.id }, { onSuccess: onClose })}
      onClose={onClose}
      pending={action.isPending}
      error={action.error}
    >
      {EXPLANATION[kind]}
    </ConfirmDialog>
  )
}

/** A Position or Document Type row's Edit, Retire/Bring back and Delete buttons. */
export function RetirableActions({
  retired,
  onEdit,
  onRetire,
}: {
  retired: boolean
  onEdit: () => void
  onRetire: (kind: RetireKind) => void
}) {
  return (
    <div className="flex justify-end gap-2">
      <ActionButton onClick={onEdit}>Edit</ActionButton>
      <ActionButton onClick={() => onRetire(retired ? 'unretire' : 'retire')}>
        {retired ? TITLE.unretire : TITLE.retire}
      </ActionButton>
      <ActionButton tone="danger" onClick={() => onRetire('delete')}>
        {TITLE.delete}
      </ActionButton>
    </div>
  )
}
