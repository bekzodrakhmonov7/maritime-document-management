import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
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
      return apiFetch<Seafarer>(BASE, { method: 'POST', body: JSON.stringify(action.body) })
    case 'edit':
      return apiFetch<Seafarer>(`${BASE}/${action.id}`, {
        method: 'PUT',
        body: JSON.stringify(action.body),
      })
    case 'set-inactive':
      return apiFetch<Seafarer>(`${BASE}/${action.id}/set-inactive`, {
        method: 'POST',
        body: JSON.stringify({ reason: action.reason }),
      })
    case 'reactivate':
      return apiFetch<Seafarer>(`${BASE}/${action.id}/reactivate`, { method: 'POST' })
  }
}

export function useSeafarerAction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: request,
    // A changed held Position changes the readiness view's Position notice.
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['seafarers'] }),
        queryClient.invalidateQueries({ queryKey: ['readiness'] }),
      ]),
  })
}

export function fullName(seafarer: Pick<Seafarer, 'first_name' | 'last_name'>): string {
  return `${seafarer.first_name} ${seafarer.last_name}`
}
