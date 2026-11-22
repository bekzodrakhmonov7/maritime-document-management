import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, apiSend, invalidate } from '../lib/api'
import type { Seafarer, SeafarerRecord, SeafarerWrite } from '../types'

const BASE = '/api/seafarers'

export interface SeafarerFilters {
  search: string
  showInactive: boolean
}

/** The seafarers in the caller's Scope; Inactive ones only when asked for. */
export function useSeafarers({ search, showInactive }: SeafarerFilters) {
  const params = new URLSearchParams()
  if (search.trim()) params.set('search', search.trim())
  if (showInactive) params.set('show_inactive', 'true')
  const query = params.toString()
  return useQuery({
    queryKey: ['seafarers', { search: search.trim(), showInactive }],
    queryFn: () => apiFetch<Seafarer[]>(query ? `${BASE}?${query}` : BASE),
    placeholderData: (previous) => previous,
  })
}

/** One seafarer's record, with its missing documents. */
export function useSeafarer(id: number) {
  return useQuery({
    queryKey: ['seafarers', id],
    queryFn: () => apiFetch<SeafarerRecord>(`${BASE}/${id}`),
    enabled: Number.isInteger(id),
  })
}

/** Create, edit, set Inactive (with a reason) or reactivate. There is no delete. */
export type SeafarerAction =
  | { kind: 'create'; body: SeafarerWrite }
  | { kind: 'edit'; id: number; body: SeafarerWrite }
  | { kind: 'set-inactive'; id: number; reason: string }
  | { kind: 'reactivate'; id: number }

function request(action: SeafarerAction) {
  switch (action.kind) {
    case 'create':
      return apiSend<Seafarer>('POST', BASE, action.body)
    case 'edit':
      return apiSend<Seafarer>('PUT', `${BASE}/${action.id}`, action.body)
    case 'set-inactive':
      return apiSend<Seafarer>('POST', `${BASE}/${action.id}/set-inactive`, { reason: action.reason })
    case 'reactivate':
      return apiSend<Seafarer>('POST', `${BASE}/${action.id}/reactivate`)
  }
}

export function useSeafarerAction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: request,
    // A changed held Position changes the readiness view's Position notice.
    onSuccess: () =>
      invalidate(queryClient, ['seafarers'], ['readiness'], ['dashboard']),
  })
}

export function fullName(seafarer: Pick<Seafarer, 'first_name' | 'last_name'>): string {
  return `${seafarer.first_name} ${seafarer.last_name}`
}
