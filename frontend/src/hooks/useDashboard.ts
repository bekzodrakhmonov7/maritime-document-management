import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { filterParams, nextOffset, pageParams, type DashboardFilters } from '../lib/dashboardPaging'
import type { Breakdown, Dashboard, DashboardQueue, FleetTotals } from '../types'

export type { DashboardFilters } from '../lib/dashboardPaging'

/** Administrators and crewing officers: the work queues within their Scope.
 * Every queue's count comes with each page; the pages are of `queue` only,
 * read one more at a time with `fetchNextPage`. */
export function useDashboard(filters: DashboardFilters, queue: DashboardQueue) {
  const query = filterParams(filters)
  return useInfiniteQuery({
    queryKey: ['dashboard', 'queues', query, queue],
    queryFn: ({ pageParam }) => apiFetch<Dashboard>(`/api/dashboard?${pageParams(query, queue, pageParam)}`),
    initialPageParam: 0,
    getNextPageParam: (last: Dashboard) => nextOffset(last),
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
