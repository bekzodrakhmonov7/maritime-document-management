import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { apiFetch } from '../lib/api'
import { supabase } from '../lib/supabase'
import type {
  DocumentRecord,
  DocumentUploadInput,
  DocumentVerifyInput,
} from '../types'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export function useDocuments() {
  return useQuery<DocumentRecord[]>({
    queryKey: ['documents'],
    queryFn: () => apiFetch('/documents'),
    staleTime: 30_000,
  })
}

export function useUploadDocument() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (input: DocumentUploadInput) => {
      const { data } = await supabase.auth.getSession()
      const token = data.session?.access_token

      const formData = new FormData()
      formData.append('doc_type_id', String(input.doc_type_id))
      formData.append('seafarer_id', String(input.seafarer_id))
      formData.append('document_number', input.document_number)
      formData.append('issue_date', input.issue_date)
      formData.append('expiry_date', input.expiry_date)
      formData.append('file', input.file)

      const headers: Record<string, string> = {}
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const res = await fetch(`${API_BASE}/documents`, {
        method: 'POST',
        headers,
        body: formData,
      })

      if (!res.ok) {
        const err = await res.text()
        throw new Error(err || `HTTP ${res.status}`)
      }

      return res.json() as Promise<DocumentRecord>
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['seafarers'] })
    },
  })
}

export function useVerifyDocument() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      documentId,
      input,
    }: {
      documentId: number
      input: DocumentVerifyInput
    }) => {
      return apiFetch(`/documents/${documentId}/verify`, {
        method: 'PATCH',
        body: JSON.stringify(input),
      }) as Promise<DocumentRecord>
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
  })
}

export interface DocumentPreview {
  objectUrl: string
  contentType: string
}

export function useDocumentPreview(documentId: number | null) {
  const query = useQuery<DocumentPreview>({
    queryKey: ['document-preview', documentId],
    queryFn: async () => {
      if (documentId === null) {
        throw new Error('No document selected')
      }
      const { data } = await supabase.auth.getSession()
      const token = data.session?.access_token
      if (!token) {
        throw new Error('Not authenticated')
      }

      const res = await fetch(`${API_BASE}/documents/${documentId}/preview`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        throw new Error(`Failed to load preview (HTTP ${res.status})`)
      }
      const blob = await res.blob()
      return {
        objectUrl: URL.createObjectURL(blob),
        contentType: blob.type || 'application/octet-stream',
      }
    },
    enabled: documentId !== null,
    staleTime: 60_000,
  })

  useEffect(() => {
    if (!query.data) return
    const url = query.data.objectUrl
    return () => {
      URL.revokeObjectURL(url)
    }
  }, [query.data])

  return query
}
