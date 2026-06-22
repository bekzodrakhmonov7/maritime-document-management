import { useCallback, type DragEvent } from 'react'
import { useDropzone, type FileRejection } from 'react-dropzone'
import { UploadCloud, FileText, X, AlertCircle } from 'lucide-react'
import { cn } from '../lib/cn'

const MAX_SIZE = 10 * 1024 * 1024

const ACCEPTED_TYPES = {
  'application/pdf': ['.pdf'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
} as const

interface DocumentDropzoneProps {
  file: File | null
  onFileAccepted: (file: File) => void
  onClear: () => void
  className?: string
}

export function DocumentDropzone({
  file,
  onFileAccepted,
  onClear,
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
    maxSize: MAX_SIZE,
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
          'flex items-center justify-between rounded-lg border border-navy-700 bg-navy-800 px-4 py-3',
          className,
        )}
      >
        <div className="flex items-center gap-3">
          <FileText className="h-5 w-5 shrink-0 text-navy-300" aria-hidden="true" />
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-navy-50">{file.name}</p>
            <p className="text-xs text-navy-400">
              {(file.size / 1024).toFixed(0)} KB
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClear}
          className="rounded-lg p-1.5 text-navy-400 transition-colors hover:bg-navy-700 hover:text-navy-100 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
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
          'flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-center transition-colors focus:outline-none focus:ring-2 focus:ring-navy-400/40',
          isDragActive && !isDragReject
            ? 'border-navy-400 bg-navy-800/60'
            : isDragReject
              ? 'border-status-expired bg-status-expired-bg/10'
              : 'border-navy-700 bg-navy-950 hover:border-navy-500 hover:bg-navy-800/40',
        )}
        role="button"
        tabIndex={0}
        aria-label="Upload document file. Drag and drop or click to browse. Accepted formats: PDF, JPEG, PNG. Maximum size: 10MB."
      >
        <input {...getInputProps()} />
        <UploadCloud
          className={cn(
            'mb-3 h-8 w-8',
            isDragReject ? 'text-status-expired' : 'text-navy-400',
          )}
          aria-hidden="true"
        />
        <p className="text-sm font-medium text-navy-100">
          {isDragActive
            ? isDragReject
              ? 'Unsupported file type'
              : 'Drop the file here'
            : 'Drag and drop a file, or click to browse'}
        </p>
        <p className="mt-1 text-xs text-navy-400">
          PDF, JPEG, or PNG up to 10MB
        </p>
      </div>

      {error && (
        <div
          role="alert"
          className="mt-3 flex items-center gap-2 rounded-lg border border-status-expired/40 bg-status-expired-bg/10 p-3"
        >
          <AlertCircle className="h-4 w-4 shrink-0 text-status-expired" aria-hidden="true" />
          <p className="text-xs text-status-expired">
            {error.code === 'file-too-large'
              ? 'File exceeds maximum size of 10MB.'
              : error.code === 'file-invalid-type'
                ? 'Unsupported file type. Only PDF, JPEG, and PNG are allowed.'
                : error.message}
          </p>
        </div>
      )}
    </div>
  )
}
