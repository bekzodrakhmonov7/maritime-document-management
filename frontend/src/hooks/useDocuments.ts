import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import type {
  DocumentDetail,
  DocumentSummary,
  FileUrl,
  ReviewDecision,
  VerificationDetails,
  VersionDetails,
} from '../types'

/** A seafarer's documents, each with its Current Version and Expiry Status. */
export function useSeafarerDocuments(seafarerId: number) {
  return useQuery({
    queryKey: ['documents', 'seafarer', seafarerId],
    queryFn: () => apiFetch<DocumentSummary[]>(`/api/seafarers/${seafarerId}/documents`),
    enabled: Number.isInteger(seafarerId),
  })
}

/** One document with its full history. */
export function useDocument(documentId: number) {
  return useQuery({
    queryKey: ['documents', documentId],
    queryFn: () => apiFetch<DocumentDetail>(`/api/documents/${documentId}`),
    enabled: Number.isInteger(documentId),
  })
}

export type VersionAction =
  | {
      kind: 'upload'
      seafarerId: number
      documentTypeId: number
      details: VersionDetails
      file: File
    }
  | { kind: 'details'; documentId: number; details: VersionDetails }

function request(action: VersionAction) {
  if (action.kind === 'details') {
    return apiFetch<DocumentDetail>(`/api/documents/${action.documentId}/versions`, {
      method: 'POST',
      body: JSON.stringify(action.details),
    })
  }
  const form = new FormData()
  Object.entries(action.details).forEach(([key, value]) => {
    if (value) form.append(key, value)
  })
  form.append('file', action.file)
  return apiFetch<DocumentDetail>(
    `/api/seafarers/${action.seafarerId}/documents?document_type_id=${action.documentTypeId}`,
    { method: 'POST', body: form },
  )
}

/** A change that answers with the whole document: keep it, and refresh the seafarer's table. */
function useDocumentChange<T>(mutationFn: (args: T) => Promise<DocumentDetail>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: (document) => {
      queryClient.setQueryData(['documents', document.id], document)
      return queryClient.invalidateQueries({ queryKey: ['documents', 'seafarer', document.seafarer_id] })
    },
  })
}

/** Upload a file with its details, or add a details-only Version. */
export function useAddVersion() {
  return useDocumentChange(request)
}

/** Accept or reject a Version with a comment (never one you uploaded). */
export function useReviewVersion() {
  return useDocumentChange(
    ({ versionId, decision, comment }: { versionId: number; decision: ReviewDecision; comment: string }) =>
      apiFetch<DocumentDetail>(`/api/versions/${versionId}/reviews`, {
        method: 'POST',
        body: JSON.stringify({ decision, comment }),
      }),
  )
}

/** Record a Verification, with an optional proof file that passes the Safety Checks. */
export function useRecordVerification() {
  return useDocumentChange(
    ({ versionId, details, proof }: { versionId: number; details: VerificationDetails; proof: File | null }) => {
      const form = new FormData()
      Object.entries(details).forEach(([key, value]) => form.append(key, value))
      if (proof) form.append('file', proof)
      return apiFetch<DocumentDetail>(`/api/versions/${versionId}/verifications`, { method: 'POST', body: form })
    },
  )
}

/** Ask for a signed URL (recorded as a download) and follow it. Storage
 * serves it as an attachment named after the cleaned filename, so the
 * browser downloads it and stays on the page. */
function useOpenSignedFile(path: (id: number) => string) {
  return useMutation({
    mutationFn: async (id: number) => {
      const file = await apiFetch<FileUrl>(path(id), { method: 'POST' })
      window.location.assign(file.url)
      return file
    },
  })
}

export function useOpenVersionFile() {
  return useOpenSignedFile((versionId) => `/api/versions/${versionId}/file-url`)
}

/** A Verification's proof file. */
export function useOpenProofFile() {
  return useOpenSignedFile((verificationId) => `/api/verifications/${verificationId}/proof-url`)
}
