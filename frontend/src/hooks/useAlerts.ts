import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import type { Alert, ThresholdConfig } from '../types'

export function useAlerts() {
  return useQuery<Alert[]>({
    queryKey: ['alerts'],
    queryFn: () => apiFetch('/alerts'),
    staleTime: 30_000,
  })
}

export function useResolveAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (alertId: number) => {
      return apiFetch(`/alerts/${alertId}/resolve`, {
        method: 'PATCH',
      }) as Promise<{ alert_id: number; is_resolved: boolean }>
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}

export function useThresholds() {
  return useQuery<ThresholdConfig>({
    queryKey: ['thresholds'],
    queryFn: () => apiFetch('/alerts/thresholds'),
    staleTime: 60_000,
  })
}

export function useUpdateThresholds() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (input: Partial<ThresholdConfig>) => {
      return apiFetch('/alerts/thresholds', {
        method: 'PATCH',
        body: JSON.stringify(input),
      }) as Promise<ThresholdConfig>
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['thresholds'] })
    },
  })
}
