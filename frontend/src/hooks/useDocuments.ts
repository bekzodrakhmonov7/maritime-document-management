import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import type { DocumentDetail, DocumentSummary, FileUrl, VersionDetails } from '../types'

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

/** Upload a file with its details, or add a details-only Version. */
export function useAddVersion() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: request,
    onSuccess: (document) => {
      queryClient.setQueryData(['documents', document.id], document)
      return queryClient.invalidateQueries({ queryKey: ['documents', 'seafarer', document.seafarer_id] })
    },
  })
}

/** Ask for a signed URL (recorded as a download) and follow it. Storage
 * serves it as an attachment named after the cleaned filename, so the
 * browser downloads it and stays on the page. */
export function useOpenVersionFile() {
  return useMutation({
    mutationFn: async (versionId: number) => {
      const file = await apiFetch<FileUrl>(`/api/versions/${versionId}/file-url`, { method: 'POST' })
      window.location.assign(file.url)
      return file
    },
  })
}
