import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import type { Account, AccountStatus, UserRole } from '../types'

const KEY = ['accounts'] as const

export function useAccounts(status: AccountStatus | 'all', enabled = true) {
  return useQuery({
    queryKey: [...KEY, 'list', status],
    queryFn: () =>
      apiFetch<Account[]>(status === 'all' ? '/api/accounts' : `/api/accounts?status=${status}`),
    enabled,
  })
}

export function usePendingCount(enabled: boolean) {
  return useQuery({
    queryKey: [...KEY, 'pending-count'],
    queryFn: () => apiFetch<{ pending: number }>('/api/accounts/pending-count'),
    select: (data) => data.pending,
    enabled,
    refetchInterval: 60_000,
  })
}

export type AccountAction =
  | { kind: 'approve'; role: UserRole; reason: string; vessel_ids?: number[] }
  | { kind: 'role'; role: UserRole; reason: string }
  | { kind: 'deactivate'; reason: string }
  | { kind: 'reactivate'; reason: string; role?: UserRole }
  /** A lost authenticator: the Account enrols a new one at its next sign-in (SR-03). */
  | { kind: 'second-factor/reset'; reason: string }

export function useAccountAction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: AccountAction }) => {
      const { kind, ...body } = action
      return apiFetch<Account>(`/api/accounts/${id}/${kind}`, {
        method: 'POST',
        body: JSON.stringify(body),
      })
    },
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: KEY }),
        // Approval and role changes add or drop Responsible Officer links.
        queryClient.invalidateQueries({ queryKey: ['responsible-officers'] }),
        queryClient.invalidateQueries({ queryKey: ['vessels'] }),
      ]),
  })
}
