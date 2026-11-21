import { Download } from 'lucide-react'
import { useDownloadReport, type ReportFormat, type ReportKind } from '../hooks/useReports'
import { ActionButton } from './ActionButton'

const FORMATS: ReportFormat[] = ['pdf', 'csv']

/** "Download PDF / CSV" for one Status Report. `label` names what it covers. */
export function ReportDownloads({ kind, id, label }: { kind: ReportKind; id: number; label: string }) {
  const download = useDownloadReport()
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      {FORMATS.map((format) => (
        <ActionButton
          key={format}
          disabled={download.isPending}
          onClick={() => download.mutate({ kind, id, format })}
          aria-label={`Download ${label} as ${format.toUpperCase()}`}
          title={`Status Report as of today (${format.toUpperCase()})`}
        >
          <Download className="h-3.5 w-3.5" aria-hidden="true" />
          {format.toUpperCase()}
        </ActionButton>
      ))}
      {download.error && (
        <span role="alert" className="text-xs text-danger">
          {download.error.message}
        </span>
      )}
    </span>
  )
}
