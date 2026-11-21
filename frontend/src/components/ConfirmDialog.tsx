import type { ReactNode } from 'react'
import { FormDialog } from './FormDialog'

interface ConfirmDialogProps {
  title: string
  subtitle?: string
  confirmLabel: string
  onConfirm: () => void
  onClose: () => void
  pending: boolean
  error: Error | null
  children: ReactNode
}

/** A yes/no question for state changes such as retire, deactivate or delete. */
export function ConfirmDialog({ confirmLabel, onConfirm, children, ...rest }: ConfirmDialogProps) {
  return (
    <FormDialog {...rest} submitLabel={confirmLabel} onSubmit={onConfirm} canSubmit>
      <div className="text-sm text-ink-muted">{children}</div>
    </FormDialog>
  )
}
