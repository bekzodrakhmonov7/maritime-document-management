import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, apiSend } from '../lib/api'
import type { Settings, SettingsWrite } from '../types'

export function useSettings() {
  return useQuery({ queryKey: ['settings'], queryFn: () => apiFetch<Settings>('/api/settings') })
}

export function useSaveSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: SettingsWrite) => apiSend<Settings>('PUT', '/api/settings', body),
    onSuccess: (saved) => queryClient.setQueryData(['settings'], saved),
  })
}
