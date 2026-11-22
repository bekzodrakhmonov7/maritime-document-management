import { Link } from 'react-router-dom'
import { useAlerts } from '../hooks/useAlerts'
import { ErrorNote } from '../components/ErrorNote'
import { NotReviewedTag } from '../components/ReviewTags'
import { cn } from '../lib/cn'
import type { Alert } from '../types'
import { Table } from '../components/Table'

function urgency(alert: Alert): { label: string; className: string } {
  const days = alert.days_left
  if (days < 0) {
    return { label: `Expired ${-days} day${days === -1 ? '' : 's'} ago`, className: 'text-danger' }
  }
  if (days === 0) return { label: 'Expires today', className: 'text-danger' }
  return { label: `${days} day${days === 1 ? '' : 's'} left`, className: 'text-warning' }
}

/** Open Alerts within the caller's Scope, most urgent first. An alert closes
 * by itself when the document gets a different expiry date or the seafarer
 * becomes Inactive. */
export function AlertsPage() {
  const { data: alerts, isLoading, error } = useAlerts()

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-medium text-ink">Alerts</h2>
        <p className="mt-1 text-sm text-ink-faint">
          Documents that reached an alert step for their current expiry date. Nobody resolves them
          by hand: a renewal with a new expiry date closes them.
        </p>
      </div>

      {error && <ErrorNote message={error.message} />}

      <Table
        head={['Seafarer', 'Document', 'Expiry date', 'Urgency', 'Alert step']}
        loading={isLoading}
        empty={alerts?.length === 0 ? 'No open alerts.' : null}
      >
        {alerts?.map((alert) => {
          const { label, className } = urgency(alert)
          return (
            <tr key={alert.id}>
              <td className="px-4 py-3">
                <Link
                  to={`/seafarers/${alert.seafarer_id}`}
                  className="font-medium text-ink underline-offset-2 hover:underline"
                >
                  {alert.seafarer_name}
                </Link>
              </td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    to={`/documents/${alert.document_id}`}
                    className="text-ink underline-offset-2 hover:underline"
                  >
                    {alert.document_type_name}
                  </Link>
                  {alert.awaiting_review && <NotReviewedTag label="Awaiting review" />}
                </div>
              </td>
              <td className="px-4 py-3 text-ink-muted">{alert.expiry_date}</td>
              <td className={cn('px-4 py-3 font-medium', className)}>{label}</td>
              <td className="px-4 py-3 text-ink-muted">
                {alert.step === 0 ? 'Expiry day' : `${alert.step} days before`}
              </td>
            </tr>
          )
        })}
      </Table>
    </div>
  )
}
