import { useCallback, type DragEvent } from 'react'
import { useDropzone, type FileRejection } from 'react-dropzone'
import { UploadCloud, FileText, X, AlertCircle } from 'lucide-react'
import { cn } from '../lib/cn'

const ACCEPTED_TYPES = {
  'application/pdf': ['.pdf'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
} as const

interface DocumentDropzoneProps {
  file: File | null
  onFileAccepted: (file: File) => void
  onClear: () => void
  /** The file-size limit from Settings, in MB. */
  maxSizeMb: number
  /** The current limits, shown under the drop area. */
  hint: string
  className?: string
}

export function DocumentDropzone({
  file,
  onFileAccepted,
  onClear,
  maxSizeMb,
  hint,
  className,
}: DocumentDropzoneProps) {
  const onDrop = useCallback(
    (acceptedFiles: File[], rejections: FileRejection[]) => {
      if (rejections.length > 0) {
        return
      }
      if (acceptedFiles.length > 0) {
        onFileAccepted(acceptedFiles[0])
      }
    },
    [onFileAccepted],
  )

  const {
    getRootProps,
    getInputProps,
    isDragActive,
    isDragReject,
    fileRejections,
  } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    maxSize: maxSizeMb * 1024 * 1024,
    multiple: false,
  })

  const error = fileRejections[0]?.errors[0]

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
  }

  if (file) {
    return (
      <div
        className={cn(
          'flex items-center justify-between rounded-md border border-line-strong bg-surface-active px-4 py-3',
          className,
        )}
      >
        <div className="flex items-center gap-3">
          <FileText className="h-5 w-5 shrink-0 text-ink-muted" aria-hidden="true" />
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-ink">{file.name}</p>
            <p className="text-xs text-ink-faint">
              {(file.size / 1024).toFixed(0)} KB
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClear}
          className="rounded-md p-1.5 text-ink-faint transition-colors hover:bg-surface-active hover:text-ink focus:outline-none focus:ring-2 focus:ring-accent/40"
          aria-label="Remove selected file"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    )
  }

  return (
    <div className={className}>
      <div
        {...getRootProps({
          onDragOver: handleDragOver,
        })}
        className={cn(
          'flex cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed p-8 text-center transition-colors focus:outline-none focus:ring-2 focus:ring-accent/40',
          isDragActive && !isDragReject
            ? 'border-accent bg-surface-active'
            : isDragReject
              ? 'border-danger'
              : 'border-line-strong bg-canvas hover:border-line-strong hover:bg-surface-active',
        )}
        role="button"
        tabIndex={0}
        aria-label={`Upload document file. Drag and drop or click to browse. ${hint}`}
      >
        <input {...getInputProps()} />
        <UploadCloud
          className={cn(
            'mb-3 h-8 w-8',
            isDragReject ? 'text-danger' : 'text-ink-faint',
          )}
          aria-hidden="true"
        />
        <p className="text-sm font-medium text-ink">
          {isDragActive
            ? isDragReject
              ? 'Unsupported file type'
              : 'Drop the file here'
            : 'Drag and drop a file, or click to browse'}
        </p>
        <p className="mt-1 text-xs text-ink-faint">{hint}</p>
      </div>

      {error && (
        <div
          role="alert"
          className="mt-3 flex items-center gap-2 rounded-md border border-danger/40 p-3"
        >
          <AlertCircle className="h-4 w-4 shrink-0 text-danger" aria-hidden="true" />
          <p className="text-xs text-danger">
            {error.code === 'file-too-large'
              ? `File exceeds the maximum size of ${maxSizeMb} MB.`
              : error.code === 'file-invalid-type'
                ? 'Unsupported file type. Only PDF, JPEG, and PNG are allowed.'
                : error.message}
          </p>
        </div>
      )}
    </div>
  )
}
