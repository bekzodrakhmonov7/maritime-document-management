import { useMemo, useState, useEffect, type FormEvent } from 'react'
import {
  FileText,
  Upload,
  X,
  Loader2,
  AlertCircle,
  Check,
  Ban,
  Eye,
} from 'lucide-react'
import { useDocuments, useUploadDocument, useVerifyDocument } from '../hooks/useDocuments'
import { useSeafarers } from '../hooks/useSeafarers'
import { useAuth } from '../context/AuthContext'
import { StatusBadge } from '../components/StatusBadge'
import { DocumentDropzone } from '../components/DocumentDropzone'
import { DocumentPreviewModal } from '../components/DocumentPreviewModal'
import { DOC_TYPE_OPTIONS, getDocTypeName } from '../lib/docTypes'
import { cn } from '../lib/cn'
import type { DocumentRecord } from '../types'

function formatDate(value: string | null): string {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

export function DocumentsPage() {
  const { role } = useAuth()
  const documentsQuery = useDocuments()
  const seafarersQuery = useSeafarers({ limit: 100 })
  const uploadMutation = useUploadDocument()
  const verifyMutation = useVerifyDocument()

  const [isModalOpen, setIsModalOpen] = useState(false)
  const [previewDoc, setPreviewDoc] = useState<DocumentRecord | null>(null)

  const canVerify = role === 'administrator' || role === 'crewing_officer'

  const seafarerMap = useMemo(() => {
    const map = new Map<number, string>()
    for (const s of seafarersQuery.data ?? []) {
      map.set(s.seafarer_id, `${s.first_name} ${s.last_name}`)
    }
    return map
  }, [seafarersQuery.data])

  const documents = documentsQuery.data ?? []

  const handleVerify = (doc: DocumentRecord, status: 'verified' | 'rejected') => {
    verifyMutation.mutate({ documentId: doc.document_id, input: { status } })
  }

  const handlePreviewVerify = async (
    doc: DocumentRecord,
    status: 'verified' | 'rejected'
  ) => {
    await verifyMutation.mutateAsync({
      documentId: doc.document_id,
      input: { status },
    })
    setPreviewDoc(null)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-navy-300" aria-hidden="true" />
            <h1 className="text-xl font-bold tracking-tight text-navy-50">
              Document Registry
            </h1>
          </div>
          <p className="mt-1 text-sm text-navy-400">
            Track and manage crew document expiry dates
          </p>
        </div>
        <button
          type="button"
          onClick={() => setIsModalOpen(true)}
          className="inline-flex items-center gap-2 rounded-lg bg-navy-600 px-4 py-2.5 text-sm font-medium text-navy-50 transition-colors hover:bg-navy-500 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
        >
          <Upload className="h-4 w-4" aria-hidden="true" />
          Upload Document
        </button>
      </div>

      {documentsQuery.isLoading && (
        <div className="flex items-center justify-center rounded-xl border border-navy-800 bg-navy-900 p-12">
          <Loader2 className="h-6 w-6 animate-spin text-navy-300" />
          <span className="ml-3 text-sm text-navy-300">Loading documents...</span>
        </div>
      )}

      {documentsQuery.isError && (
        <div
          role="alert"
          className="flex items-center gap-3 rounded-xl border border-status-expired/40 bg-status-expired-bg/10 p-6"
        >
          <AlertCircle className="h-5 w-5 shrink-0 text-status-expired" />
          <p className="text-sm text-status-expired">
            Failed to load documents. Please try again later.
          </p>
        </div>
      )}

      {!documentsQuery.isLoading && !documentsQuery.isError && documents.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-xl border border-navy-800 bg-navy-900 p-12">
          <FileText className="mb-3 h-8 w-8 text-navy-500" />
          <p className="text-sm text-navy-400">No documents found.</p>
        </div>
      )}

      {!documentsQuery.isLoading && !documentsQuery.isError && documents.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-navy-800 bg-navy-900">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-navy-800 bg-navy-800">
                <tr>
                  <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                    Seafarer
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                    Document Type
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                    Document Number
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                    Issue Date
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                    Expiry Date
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                    Status
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-navy-800">
                {documents.map((doc) => (
                  <tr
                    key={doc.document_id}
                    className={cn(
                      'transition-colors hover:bg-navy-800/50',
                      doc.status === 'expired' && 'bg-status-expired-bg/5',
                      doc.status === 'expiring_soon' && 'bg-status-expiring-bg/5',
                    )}
                  >
                    <td className="px-4 py-3 whitespace-nowrap font-medium text-navy-50">
                      {seafarerMap.get(doc.seafarer_id) ?? `Seafarer #${doc.seafarer_id}`}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-navy-200">
                      {getDocTypeName(doc.doc_type_id)}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-navy-200">
                      {doc.document_number}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-navy-200">
                      {formatDate(doc.issue_date)}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-navy-200">
                      {formatDate(doc.expiry_date)}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <StatusBadge status={doc.status} />
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => setPreviewDoc(doc)}
                          className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-navy-300 transition-colors hover:bg-navy-700 hover:text-navy-100 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
                          aria-label={`Preview document ${doc.document_number}`}
                        >
                          <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                          Preview
                        </button>
                        {canVerify && doc.status === 'pending' && (
                          <>
                            <button
                              type="button"
                              onClick={() => handleVerify(doc, 'verified')}
                              disabled={verifyMutation.isPending}
                              className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-status-valid transition-colors hover:bg-status-valid-bg/20 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50"
                              aria-label={`Verify document ${doc.document_number}`}
                            >
                              <Check className="h-3.5 w-3.5" aria-hidden="true" />
                              Verify
                            </button>
                            <button
                              type="button"
                              onClick={() => handleVerify(doc, 'rejected')}
                              disabled={verifyMutation.isPending}
                              className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-status-rejected transition-colors hover:bg-status-rejected-bg/20 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50"
                              aria-label={`Reject document ${doc.document_number}`}
                            >
                              <Ban className="h-3.5 w-3.5" aria-hidden="true" />
                              Reject
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {isModalOpen && (
        <UploadModal
          onClose={() => setIsModalOpen(false)}
          uploadMutation={uploadMutation}
          seafarers={seafarersQuery.data ?? []}
        />
      )}

      {previewDoc && (
        <DocumentPreviewModal
          doc={previewDoc}
          seafarerName={seafarerMap.get(previewDoc.seafarer_id) ?? `Seafarer #${previewDoc.seafarer_id}`}
          onClose={() => setPreviewDoc(null)}
          onVerify={handlePreviewVerify}
          isVerifying={verifyMutation.isPending}
        />
      )}
    </div>
  )
}

interface UploadModalProps {
  onClose: () => void
  uploadMutation: ReturnType<typeof useUploadDocument>
  seafarers: { seafarer_id: number; first_name: string; last_name: string }[]
}

function UploadModal({ onClose, uploadMutation, seafarers }: UploadModalProps) {
  const [file, setFile] = useState<File | null>(null)
  const [seafarerId, setSeafarerId] = useState('')
  const [docTypeId, setDocTypeId] = useState('')
  const [documentNumber, setDocumentNumber] = useState('')
  const [issueDate, setIssueDate] = useState('')
  const [expiryDate, setExpiryDate] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [onClose])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setFormError(null)

    if (!file) {
      setFormError('Please select a file to upload.')
      return
    }
    if (!seafarerId) {
      setFormError('Please select a seafarer.')
      return
    }
    if (!docTypeId) {
      setFormError('Please select a document type.')
      return
    }
    if (!documentNumber.trim()) {
      setFormError('Please enter a document number.')
      return
    }
    if (!issueDate || !expiryDate) {
      setFormError('Please provide both issue and expiry dates.')
      return
    }
    if (new Date(expiryDate) <= new Date(issueDate)) {
      setFormError('Expiry date must be after the issue date.')
      return
    }

    try {
      await uploadMutation.mutateAsync({
        file,
        seafarer_id: Number(seafarerId),
        doc_type_id: Number(docTypeId),
        document_number: documentNumber.trim(),
        issue_date: issueDate,
        expiry_date: expiryDate,
      })
      onClose()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Upload failed.')
    }
  }

  const inputClass =
    'w-full rounded-lg border border-navy-700 bg-navy-950 px-4 py-2.5 text-navy-50 placeholder-navy-500 transition-colors focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50'

  const labelClass = 'mb-2 block text-sm font-medium text-navy-100'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/80 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="upload-modal-title"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-navy-800 bg-navy-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Upload className="h-5 w-5 text-navy-300" aria-hidden="true" />
            <h2
              id="upload-modal-title"
              className="text-lg font-semibold text-navy-50"
            >
              Upload Document
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-navy-400 transition-colors hover:bg-navy-800 hover:text-navy-100 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
            aria-label="Close upload dialog"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          {formError && (
            <div
              role="alert"
              className="flex items-start gap-3 rounded-lg border border-status-expired/40 bg-status-expired-bg/10 p-4"
            >
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-status-expired" />
              <p className="text-sm text-status-expired">{formError}</p>
            </div>
          )}

          {uploadMutation.isError && !formError && (
            <div
              role="alert"
              className="flex items-start gap-3 rounded-lg border border-status-expired/40 bg-status-expired-bg/10 p-4"
            >
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-status-expired" />
              <p className="text-sm text-status-expired">
                {uploadMutation.error instanceof Error
                  ? uploadMutation.error.message
                  : 'Upload failed.'}
              </p>
            </div>
          )}

          <DocumentDropzone
            file={file}
            onFileAccepted={setFile}
            onClear={() => setFile(null)}
          />

          <div>
            <label htmlFor="seafarer" className={labelClass}>
              Seafarer
            </label>
            <select
              id="seafarer"
              value={seafarerId}
              onChange={(e) => setSeafarerId(e.target.value)}
              disabled={uploadMutation.isPending}
              required
              className={inputClass}
              aria-required="true"
            >
              <option value="">Select a seafarer</option>
              {seafarers.map((s) => (
                <option key={s.seafarer_id} value={s.seafarer_id}>
                  {s.first_name} {s.last_name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="docType" className={labelClass}>
              Document Type
            </label>
            <select
              id="docType"
              value={docTypeId}
              onChange={(e) => setDocTypeId(e.target.value)}
              disabled={uploadMutation.isPending}
              required
              className={inputClass}
              aria-required="true"
            >
              <option value="">Select a document type</option>
              {DOC_TYPE_OPTIONS.map((dt) => (
                <option key={dt.doc_type_id} value={dt.doc_type_id}>
                  {dt.type_name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="docNumber" className={labelClass}>
              Document Number
            </label>
            <input
              id="docNumber"
              type="text"
              value={documentNumber}
              onChange={(e) => setDocumentNumber(e.target.value)}
              disabled={uploadMutation.isPending}
              required
              className={inputClass}
              placeholder="e.g. COC-2024-001"
              aria-required="true"
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="issueDate" className={labelClass}>
                Issue Date
              </label>
              <input
                id="issueDate"
                type="date"
                value={issueDate}
                onChange={(e) => setIssueDate(e.target.value)}
                disabled={uploadMutation.isPending}
                required
                className={inputClass}
                aria-required="true"
              />
            </div>
            <div>
              <label htmlFor="expiryDate" className={labelClass}>
                Expiry Date
              </label>
              <input
                id="expiryDate"
                type="date"
                value={expiryDate}
                onChange={(e) => setExpiryDate(e.target.value)}
                disabled={uploadMutation.isPending}
                required
                className={inputClass}
                aria-required="true"
              />
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={uploadMutation.isPending}
              className="rounded-lg px-4 py-2.5 text-sm font-medium text-navy-300 transition-colors hover:bg-navy-800 hover:text-navy-100 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={uploadMutation.isPending}
              className="inline-flex items-center gap-2 rounded-lg bg-navy-600 px-4 py-2.5 text-sm font-medium text-navy-50 transition-colors hover:bg-navy-500 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {uploadMutation.isPending && (
                <Loader2 className="h-4 w-4 animate-spin" />
              )}
              {uploadMutation.isPending ? 'Uploading...' : 'Upload'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
