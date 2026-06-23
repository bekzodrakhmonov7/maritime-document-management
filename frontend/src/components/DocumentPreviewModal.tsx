import { useEffect } from 'react'
import {
  X,
  Eye,
  Loader2,
  AlertCircle,
  Check,
  Ban,
} from 'lucide-react'
import { useDocumentPreview } from '../hooks/useDocuments'
import { StatusBadge } from './StatusBadge'
import { getDocTypeName } from '../lib/docTypes'
import type { DocumentRecord } from '../types'

function formatDate(value: string | null): string {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

interface DocumentPreviewModalProps {
  doc: DocumentRecord
  seafarerName: string
  onClose: () => void
  onVerify: (doc: DocumentRecord, status: 'verified' | 'rejected') => void
  isVerifying: boolean
}

export function DocumentPreviewModal({
  doc,
  seafarerName,
  onClose,
  onVerify,
  isVerifying,
}: DocumentPreviewModalProps) {
  const previewQuery = useDocumentPreview(doc.document_id)

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [onClose])

  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = ''
    }
  }, [])

  const isImage =
    previewQuery.data?.contentType.startsWith('image/') ?? false
  const canAct = doc.status === 'pending' && !isVerifying

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/80 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="preview-modal-title"
      onClick={onClose}
    >
      <div
        className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-navy-800 bg-navy-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-navy-800 px-6 py-4">
          <div className="flex min-w-0 items-center gap-3">
            <Eye className="h-5 w-5 shrink-0 text-navy-300" aria-hidden="true" />
            <div className="min-w-0">
              <h2
                id="preview-modal-title"
                className="truncate text-lg font-semibold text-navy-50"
              >
                Review Document
              </h2>
              <p className="truncate text-xs text-navy-400">
                {getDocTypeName(doc.doc_type_id)} · {doc.document_number}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-lg p-1.5 text-navy-400 transition-colors hover:bg-navy-800 hover:text-navy-100 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
            aria-label="Close preview"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <div className="grid shrink-0 grid-cols-2 gap-x-6 gap-y-2 border-b border-navy-800 bg-navy-950/40 px-6 py-4 text-sm sm:grid-cols-4">
          <MetadataField label="Seafarer" value={seafarerName} />
          <MetadataField
            label="Issue Date"
            value={formatDate(doc.issue_date)}
          />
          <MetadataField
            label="Expiry Date"
            value={formatDate(doc.expiry_date)}
          />
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-navy-500">
              Status
            </div>
            <div className="mt-1">
              <StatusBadge status={doc.status} />
            </div>
          </div>
        </div>

        <div
          className="flex-1 overflow-auto bg-navy-950"
          onContextMenu={(e) => e.preventDefault()}
        >
          {previewQuery.isLoading && <LoadingState />}
          {previewQuery.isError && (
            <ErrorState
              message={
                previewQuery.error instanceof Error
                  ? previewQuery.error.message
                  : 'Failed to load document preview.'
              }
            />
          )}
          {previewQuery.data && (
            <div className="flex h-full min-h-[400px] items-center justify-center p-4">
              {isImage ? (
                <img
                  src={previewQuery.data.objectUrl}
                  alt={`Document ${doc.document_number}`}
                  draggable={false}
                  className="max-h-full max-w-full rounded object-contain shadow-lg"
                />
              ) : (
                <iframe
                  src={previewQuery.data.objectUrl}
                  title={`Document ${doc.document_number}`}
                  className="h-[70vh] w-full rounded border border-navy-800 bg-white shadow-lg"
                />
              )}
            </div>
          )}
        </div>

        <div className="flex shrink-0 items-center justify-end gap-3 border-t border-navy-800 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            disabled={isVerifying}
            className="rounded-lg px-4 py-2.5 text-sm font-medium text-navy-300 transition-colors hover:bg-navy-800 hover:text-navy-100 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50"
          >
            Close
          </button>
          {canAct && (
            <>
              <button
                type="button"
                onClick={() => onVerify(doc, 'rejected')}
                className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-medium text-status-rejected transition-colors hover:bg-status-rejected-bg/20 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
              >
                <Ban className="h-4 w-4" aria-hidden="true" />
                Reject
              </button>
              <button
                type="button"
                onClick={() => onVerify(doc, 'verified')}
                className="inline-flex items-center gap-1.5 rounded-lg bg-status-valid/90 px-4 py-2.5 text-sm font-medium text-navy-50 transition-colors hover:bg-status-valid focus:outline-none focus:ring-2 focus:ring-navy-400/40"
              >
                <Check className="h-4 w-4" aria-hidden="true" />
                Verify
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function MetadataField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-xs font-medium uppercase tracking-wide text-navy-500">
        {label}
      </div>
      <div className="mt-1 truncate text-navy-100" title={value}>
        {value}
      </div>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="flex h-full min-h-[400px] items-center justify-center">
      <Loader2 className="h-6 w-6 animate-spin text-navy-300" />
      <span className="ml-3 text-sm text-navy-300">Loading preview...</span>
    </div>
  )
}

function ErrorState({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="m-6 flex items-start gap-3 rounded-lg border border-status-expired/40 bg-status-expired-bg/10 p-4"
    >
      <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-status-expired" />
      <p className="text-sm text-status-expired">{message}</p>
    </div>
  )
}
