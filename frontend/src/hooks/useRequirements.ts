import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
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
      return apiFetch(`/api/requirements/${action.positionId}/${action.documentTypeId}`, {
        method: action.kind === 'set' ? 'PUT' : 'DELETE',
      })
    case 'add-to-all':
      return apiFetch('/api/requirements/add-to-all-positions', {
        method: 'POST',
        body: JSON.stringify({ document_type_id: action.documentTypeId }),
      })
    case 'create-exception':
      return apiFetch('/api/requirement-exceptions', {
        method: 'POST',
        body: JSON.stringify(action.body),
      })
    case 'edit-exception':
      return apiFetch(`/api/requirement-exceptions/${action.id}`, {
        method: 'PUT',
        body: JSON.stringify(action.body),
      })
    case 'delete-exception':
      return apiFetch(`/api/requirement-exceptions/${action.id}`, { method: 'DELETE' })
  }
}

export function useRequirementAction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: request,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  })
}
