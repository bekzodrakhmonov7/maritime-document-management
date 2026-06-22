import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import type { Seafarer, SeafarerQueryParams, SeafarerCreateInput, SeafarerUpdateInput } from '../types'

export function useSeafarers(params: SeafarerQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.vessel_id !== undefined) {
    searchParams.set('vessel_id', String(params.vessel_id))
  }
  if (params.rank) {
    searchParams.set('rank', params.rank)
  }
  if (params.cursor !== undefined) {
    searchParams.set('cursor', String(params.cursor))
  }
  if (params.limit !== undefined) {
    searchParams.set('limit', String(params.limit))
  }

  const queryString = searchParams.toString()
  const path = `/seafarers${queryString ? `?${queryString}` : ''}`

  return useQuery<Seafarer[]>({
    queryKey: ['seafarers', params],
    queryFn: () => apiFetch(path),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })
}

export function useCreateSeafarer() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (input: SeafarerCreateInput) => {
      return apiFetch('/seafarers', {
        method: 'POST',
        body: JSON.stringify(input),
      }) as Promise<Seafarer>
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['seafarers'] })
    },
  })
}

export function useUpdateSeafarer() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      seafarerId,
      input,
    }: {
      seafarerId: number
      input: SeafarerUpdateInput
    }) => {
      return apiFetch(`/seafarers/${seafarerId}`, {
        method: 'PATCH',
        body: JSON.stringify(input),
      }) as Promise<Seafarer>
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['seafarers'] })
    },
  })
}

export function useDeleteSeafarer() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (seafarerId: number) => {
      await apiFetch(`/seafarers/${seafarerId}`, {
        method: 'DELETE',
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['seafarers'] })
    },
  })
}
