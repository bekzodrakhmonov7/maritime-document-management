/** The work queues are read one queue and one page at a time (NFR-07):
 * GET /api/dashboard?queue=…&offset=…&limit=… returns every queue's count
 * plus `limit` items of the asked queue from `offset`. An item is a seafarer
 * group for a document queue and an Assignment for starting soon. */

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

/** What paging reads of a page (a subset of the `Dashboard` type). */
export interface PageInfo {
  offset: number
  limit: number
  total: number
}

export function filterParams(filters: DashboardFilters): string {
  const p = new URLSearchParams()
  if (filters.name.trim()) p.set('name', filters.name.trim())
  filters.positionIds.forEach((id) => p.append('position_id', String(id)))
  filters.vesselIds.forEach((id) => p.append('vessel_id', String(id)))
  if (filters.ashore) p.set('ashore', 'true')
  filters.documentTypeIds.forEach((id) => p.append('document_type_id', String(id)))
  if (filters.showInactive) p.set('show_inactive', 'true')
  return p.toString()
}

/** The query string for one page of one queue, after the filters'. */
export function pageParams(filters: string, queue: string, offset: number): string {
  const p = new URLSearchParams(filters)
  p.set('queue', queue)
  if (offset > 0) p.set('offset', String(offset))
  return p.toString()
}

/** The offset of the page after `last`, or undefined when it was the last one. */
export function nextOffset(last: PageInfo): number | undefined {
  const next = last.offset + last.limit
  return next < last.total ? next : undefined
}

/** The items of the pages read so far, in queue order. */
export function pageItems<P, T>(pages: P[], pick: (page: P) => T[]): T[] {
  return pages.flatMap(pick)
}
