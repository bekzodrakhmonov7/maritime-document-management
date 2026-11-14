import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import type { Settings, SettingsWrite } from '../types'

export function useSettings() {
  return useQuery({ queryKey: ['settings'], queryFn: () => apiFetch<Settings>('/api/settings') })
}

export function useSaveSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: SettingsWrite) =>
      apiFetch<Settings>('/api/settings', { method: 'PUT', body: JSON.stringify(body) }),
    onSuccess: (saved) => queryClient.setQueryData(['settings'], saved),
  })
}
