import { useMutation, useQuery } from '@tanstack/react-query'
import { apiDownload, apiFetch } from '../lib/api'
import type { AuditFilters, AuditPage } from '../types'

const BASE = '/api/audit'

export const EMPTY_AUDIT_FILTERS: AuditFilters = {
  date_from: '',
  date_to: '',
  actor_email: '',
  actions: [],
  seafarer_id: '',
  target_type: '',
  target_id: '',
  outcome: '',
}

/** The filters as query parameters (`action` repeated), leaving out empty ones. */
function toParams(filters: AuditFilters): URLSearchParams {
  const params = new URLSearchParams()
  const { actions, ...single } = filters
  for (const [key, value] of Object.entries(single)) {
    if (value.trim()) params.set(key, value.trim())
  }
  for (const action of actions) params.append('action', action)
  return params
}

/** One page of the Audit Log. Every fetch is itself recorded, so it only runs
 * when the filters are applied or the page changes. */
export function useAuditLog(filters: AuditFilters, page: number, pageSize: number) {
  const params = toParams(filters)
  params.set('page', String(page))
  params.set('page_size', String(pageSize))
  return useQuery({
    queryKey: ['audit', filters, page, pageSize],
    queryFn: () => apiFetch<AuditPage>(`${BASE}?${params}`),
    placeholderData: (previous) => previous,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })
}

/** Downloads the current search as CSV; says whether it hit the row cap. */
export function useExportAuditLog() {
  return useMutation({
    mutationFn: async (filters: AuditFilters) => {
      const headers = await apiDownload(`${BASE}/export.csv?${toParams(filters)}`, 'audit-log.csv')
      return {
        rows: Number(headers.get('x-export-rows') ?? 0),
        truncated: headers.get('x-export-truncated') === 'true',
      }
    },
  })
}
