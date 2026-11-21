import { useId, type FormEvent, type ReactNode } from 'react'
import { Loader2, X } from 'lucide-react'
import { ErrorNote } from './ErrorNote'

interface FormDialogProps {
  title: string
  subtitle?: string
  submitLabel: string
  onSubmit: () => void
  onClose: () => void
  pending: boolean
  canSubmit: boolean
  error: Error | null
  children: ReactNode
}

/** A modal form: title, fields, error, Cancel and a submit button. */
export function FormDialog({
  title,
  subtitle,
  submitLabel,
  onSubmit,
  onClose,
  pending,
  canSubmit,
  error,
  children,
}: FormDialogProps) {
  const titleId = useId()

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (canSubmit) onSubmit()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/20 px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md space-y-4 rounded-md border border-line bg-canvas p-6"
      >
        <div className="flex items-start justify-between">
          <div>
            <h3 id={titleId} className="text-lg font-medium text-ink">
              {title}
            </h3>
            {subtitle && <p className="text-sm text-ink-faint">{subtitle}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-ink-faint hover:text-ink"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {children}

        {error && <ErrorNote message={error.message} />}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="h-8 shrink-0 whitespace-nowrap rounded-md px-3 text-sm text-ink-muted hover:bg-surface-active hover:text-ink"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={pending || !canSubmit}
            className="flex h-8 shrink-0 items-center gap-2 whitespace-nowrap rounded-md bg-accent px-3 text-sm font-medium text-on-accent hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            {pending && <Loader2 className="h-4 w-4 animate-spin" />}
            {submitLabel}
          </button>
        </div>
      </form>
    </div>
  )
}

export const FIELD_CLASS =
  'w-full rounded-md border border-line-strong bg-canvas px-3 py-1.5 text-sm text-ink focus:border-accent focus:outline-none'

export const LABEL_CLASS = 'mb-1 block text-xs text-ink-muted'
