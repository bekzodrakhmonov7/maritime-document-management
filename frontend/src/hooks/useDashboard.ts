import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import type { Breakdown, Dashboard, FleetTotals } from '../types'

/** The name text and click-to-add tags. Tags of one kind widen (any of them);
 * kinds narrow each other. `ashore` is the "Ashore / Unassigned" vessel value. */
export interface DashboardFilters {
  name: string
  positionIds: number[]
  vesselIds: number[]
  ashore: boolean
  documentTypeIds: number[]
  showInactive: boolean
}

function params(filters: DashboardFilters): string {
  const p = new URLSearchParams()
  if (filters.name.trim()) p.set('name', filters.name.trim())
  filters.positionIds.forEach((id) => p.append('position_id', String(id)))
  filters.vesselIds.forEach((id) => p.append('vessel_id', String(id)))
  if (filters.ashore) p.set('ashore', 'true')
  filters.documentTypeIds.forEach((id) => p.append('document_type_id', String(id)))
  if (filters.showInactive) p.set('show_inactive', 'true')
  return p.toString()
}

/** Administrators and crewing officers: the work queues within their Scope. */
export function useDashboard(filters: DashboardFilters) {
  const query = params(filters)
  return useQuery({
    queryKey: ['dashboard', 'queues', query],
    queryFn: () => apiFetch<Dashboard>(query ? `/api/dashboard?${query}` : '/api/dashboard'),
    placeholderData: (previous) => previous,
  })
}

/** Managers (and administrators): fleet totals with one breakdown, no names. */
export function useFleetTotals(breakdown: Breakdown) {
  return useQuery({
    queryKey: ['dashboard', 'totals', breakdown],
    queryFn: () => apiFetch<FleetTotals>(`/api/dashboard/totals?breakdown=${breakdown}`),
    placeholderData: (previous) => previous,
  })
}
