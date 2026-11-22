import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, apiSend } from '../lib/api'
import type {
  MatrixCell,
  RequirementEvaluation,
  RequirementException,
  RequirementExceptionWrite,
} from '../types'

/** Everything that depends on the requirements, invalidated after any change. */
const KEY = ['requirements'] as const

export function useMatrix() {
  return useQuery({
    queryKey: [...KEY, 'matrix'],
    queryFn: () => apiFetch<MatrixCell[]>('/api/requirements'),
  })
}

export function useRequirementExceptions() {
  return useQuery({
    queryKey: [...KEY, 'exceptions'],
    queryFn: () => apiFetch<RequirementException[]>('/api/requirement-exceptions'),
  })
}

export function useEvaluation(positionId: number | null, vesselId: number | null) {
  const params = new URLSearchParams()
  if (positionId !== null) params.set('position', String(positionId))
  if (vesselId !== null) params.set('vessel', String(vesselId))
  return useQuery({
    queryKey: [...KEY, 'evaluate', positionId, vesselId],
    queryFn: () => apiFetch<RequirementEvaluation>(`/api/requirements/evaluate?${params}`),
    enabled: positionId !== null,
  })
}

export type RequirementAction =
  | { kind: 'set' | 'clear'; positionId: number; documentTypeId: number }
  | { kind: 'add-to-all'; documentTypeId: number }
  | { kind: 'create-exception'; body: RequirementExceptionWrite }
  | { kind: 'edit-exception'; id: number; body: RequirementExceptionWrite }
  | { kind: 'delete-exception'; id: number }

function request(action: RequirementAction) {
  switch (action.kind) {
    case 'set':
    case 'clear':
      return apiSend(action.kind === 'set' ? 'PUT' : 'DELETE', `/api/requirements/${action.positionId}/${action.documentTypeId}`)
    case 'add-to-all':
      return apiSend('POST', '/api/requirements/add-to-all-positions', { document_type_id: action.documentTypeId })
    case 'create-exception':
      return apiSend('POST', '/api/requirement-exceptions', action.body)
    case 'edit-exception':
      return apiSend('PUT', `/api/requirement-exceptions/${action.id}`, action.body)
    case 'delete-exception':
      return apiSend('DELETE', `/api/requirement-exceptions/${action.id}`)
  }
}

export function useRequirementAction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: request,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  })
}
