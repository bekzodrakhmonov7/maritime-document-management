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
      className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/70 px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md space-y-4 rounded-xl border border-navy-800 bg-navy-900 p-6 shadow-2xl"
      >
        <div className="flex items-start justify-between">
          <div>
            <h3 id={titleId} className="text-lg font-semibold text-navy-50">
              {title}
            </h3>
            {subtitle && <p className="text-sm text-navy-400">{subtitle}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-navy-400 hover:text-navy-100"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {children}

        {error && <ErrorNote message={error.message} />}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm font-medium text-navy-300 hover:bg-navy-800"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={pending || !canSubmit}
            className="flex items-center gap-2 rounded-lg bg-navy-600 px-4 py-2 text-sm font-medium text-navy-50 hover:bg-navy-500 disabled:cursor-not-allowed disabled:opacity-50"
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
  'w-full rounded-lg border border-navy-700 bg-navy-950 px-3 py-2 text-navy-50 focus:border-navy-400 focus:outline-none'

export const LABEL_CLASS = 'mb-1 block text-sm font-medium text-navy-100'
