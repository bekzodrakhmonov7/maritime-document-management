import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import type { Vessel, VesselCreateInput, VesselUpdateInput } from '../types'

export function useVessels() {
  return useQuery<Vessel[]>({
    queryKey: ['vessels'],
    queryFn: () => apiFetch('/vessels'),
    staleTime: 30_000,
  })
}

export function useCreateVessel() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (input: VesselCreateInput) => {
      return apiFetch('/vessels', {
        method: 'POST',
        body: JSON.stringify(input),
      }) as Promise<Vessel>
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vessels'] })
    },
  })
}

export function useUpdateVessel() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      vesselId,
      input,
    }: {
      vesselId: number
      input: VesselUpdateInput
    }) => {
      return apiFetch(`/vessels/${vesselId}`, {
        method: 'PATCH',
        body: JSON.stringify(input),
      }) as Promise<Vessel>
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vessels'] })
    },
  })
}

export function useDeleteVessel() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (vesselId: number) => {
      await apiFetch(`/vessels/${vesselId}`, {
        method: 'DELETE',
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vessels'] })
    },
  })
}
