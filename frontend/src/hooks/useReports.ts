import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import type { MissingMandatoryDoc, FleetSummary } from '../types'

export function useMissingMandatory() {
  return useQuery<MissingMandatoryDoc[]>({
    queryKey: ['reports', 'missing-mandatory'],
    queryFn: () => apiFetch('/reports/missing-mandatory'),
    staleTime: 60_000,
  })
}

export function useFleetSummary() {
  return useQuery<FleetSummary>({
    queryKey: ['reports', 'fleet-summary'],
    queryFn: () => apiFetch('/reports/fleet-summary'),
    staleTime: 60_000,
  })
}
