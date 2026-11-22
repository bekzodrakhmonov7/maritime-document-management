import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, apiSend } from '../lib/api'
import type {
  DocumentType,
  DocumentTypeWrite,
  Position,
  PositionWrite,
  Vessel,
  VesselWrite,
} from '../types'

/** The three reference-data collections and their API paths. */
const PATHS = {
  vessels: '/api/vessels',
  positions: '/api/positions',
  'document-types': '/api/document-types',
} as const

export type Collection = keyof typeof PATHS

/** POST/PUT/DELETE or a state action (retire, deactivate, ...) on one collection. */
export type ReferenceAction<W> =
  | { kind: 'create'; body: W }
  | { kind: 'edit'; id: number; body: W }
  | { kind: 'delete'; id: number }
  | { kind: 'deactivate' | 'reactivate' | 'retire' | 'unretire'; id: number }

function request<W>(collection: Collection, action: ReferenceAction<W>) {
  const base = PATHS[collection]
  switch (action.kind) {
    case 'create':
      return apiSend('POST', base, action.body)
    case 'edit':
      return apiSend('PUT', `${base}/${action.id}`, action.body)
    case 'delete':
      return apiSend('DELETE', `${base}/${action.id}`)
    default:
      return apiSend('POST', `${base}/${action.id}/${action.kind}`)
  }
}

export function useReferenceAction<W>(collection: Collection) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (action: ReferenceAction<W>) => request(collection, action),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [collection] }),
  })
}

/** The fleet; optionally only the vessels with no active Responsible Officer. */
export function useVessels(withoutActiveOfficer = false) {
  return useQuery({
    queryKey: ['vessels', { withoutActiveOfficer }],
    queryFn: () =>
      apiFetch<Vessel[]>(
        withoutActiveOfficer ? `${PATHS.vessels}?without_active_officer=true` : PATHS.vessels,
      ),
  })
}

export function useVessel(id: number) {
  return useQuery({
    queryKey: ['vessels', id],
    queryFn: () => apiFetch<Vessel>(`${PATHS.vessels}/${id}`),
    enabled: Number.isInteger(id),
  })
}

export const useVesselAction = () => useReferenceAction<VesselWrite>('vessels')

export function usePositions() {
  return useQuery({
    queryKey: ['positions'],
    queryFn: () => apiFetch<Position[]>(PATHS.positions),
  })
}

export const usePositionAction = () => useReferenceAction<PositionWrite>('positions')

export function useDocumentTypes() {
  return useQuery({
    queryKey: ['document-types'],
    queryFn: () => apiFetch<DocumentType[]>(PATHS['document-types']),
  })
}

export const useDocumentTypeAction = () => useReferenceAction<DocumentTypeWrite>('document-types')
