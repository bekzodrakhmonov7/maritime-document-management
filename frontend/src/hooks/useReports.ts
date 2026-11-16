import { useMutation, useQuery } from '@tanstack/react-query'
import { useAuth } from '../context/AuthContext'
import { apiDownload, apiFetch } from '../lib/api'

export type ReportKind = 'assignment' | 'vessel'
export type ReportFormat = 'pdf' | 'csv'

export interface ReportRequest {
  kind: ReportKind
  id: number
  format: ReportFormat
}

const reportPath = ({ kind, id, format }: ReportRequest) =>
  `/api/${kind === 'assignment' ? 'assignments' : 'vessels'}/${id}/report?format=${format}`

/** Downloads a Status Report (FR-21), as of today; the API audits each one. */
export function useDownloadReport() {
  return useMutation({
    mutationFn: (request: ReportRequest) =>
      apiDownload(reportPath(request), `status-report-${request.kind}-${request.id}.${request.format}`),
  })
}

/** Whether the signed-in Account may download a vessel's report:
 * administrators any vessel, crewing officers the ones they are a Responsible
 * Officer for, managers none. */
export function useCanReportOnVessel(): (vesselId: number) => boolean {
  const { role } = useAuth()
  const isOfficer = role === 'crewing_officer'
  const { data: mine } = useQuery({
    queryKey: ['me', 'vessels'],
    queryFn: () => apiFetch<number[]>('/api/me/vessels'),
    enabled: isOfficer,
  })
  return (vesselId) =>
    role === 'administrator' || (isOfficer && (mine ?? []).includes(vesselId))
}
