import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, apiSend } from '../lib/api'
import type { Alert, DailyCheckResult } from '../types'

const KEY = ['alerts'] as const

export function useAlerts() {
  return useQuery({ queryKey: [...KEY, 'list'], queryFn: () => apiFetch<Alert[]>('/api/alerts') })
}

export function useAlertCount(enabled: boolean) {
  return useQuery({
    queryKey: [...KEY, 'count'],
    queryFn: () => apiFetch<{ open: number }>('/api/alerts/count'),
    select: (data) => data.open,
    enabled,
    refetchInterval: 60_000,
  })
}

/** Administrators: run the daily check now (not counted as the day's run). */
export function useRunDailyCheck() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiSend<DailyCheckResult>('POST', '/api/admin/daily-check/run'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  })
}
