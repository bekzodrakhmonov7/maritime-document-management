import { Link } from 'react-router-dom'
import { useAlerts } from '../hooks/useAlerts'
import { ErrorNote } from '../components/ErrorNote'
import { NotReviewedTag } from '../components/ReviewTags'
import { cn } from '../lib/cn'
import type { Alert } from '../types'

const COLUMNS = 5

function urgency(alert: Alert): { label: string; className: string } {
  const days = alert.days_left
  if (days < 0) {
    return { label: `Expired ${-days} day${days === -1 ? '' : 's'} ago`, className: 'text-status-expired' }
  }
  if (days === 0) return { label: 'Expires today', className: 'text-status-expired' }
  return { label: `${days} day${days === 1 ? '' : 's'} left`, className: 'text-status-expiring' }
}

/** Open Alerts within the caller's Scope, most urgent first. An alert closes
 * by itself when the document gets a different expiry date or the seafarer
 * becomes Inactive. */
export function AlertsPage() {
  const { data: alerts, isLoading, error } = useAlerts()

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-navy-50">Alerts</h2>
        <p className="mt-1 text-sm text-navy-400">
          Documents that reached an alert step for their current expiry date. Nobody resolves them
          by hand: a renewal with a new expiry date closes them.
        </p>
      </div>

      {error && <ErrorNote message={error.message} />}

      <div className="overflow-x-auto rounded-xl border border-navy-800 bg-navy-900">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-navy-800 text-xs uppercase tracking-wider text-navy-400">
            <tr>
              <th scope="col" className="px-4 py-3">Seafarer</th>
              <th scope="col" className="px-4 py-3">Document</th>
              <th scope="col" className="px-4 py-3">Expiry date</th>
              <th scope="col" className="px-4 py-3">Urgency</th>
              <th scope="col" className="px-4 py-3">Alert step</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-navy-800">
            {isLoading && (
              <tr>
                <td colSpan={COLUMNS} className="px-4 py-6 text-center text-navy-400">
                  Loading…
                </td>
              </tr>
            )}
            {alerts?.length === 0 && (
              <tr>
                <td colSpan={COLUMNS} className="px-4 py-6 text-center text-navy-400">
                  No open alerts.
                </td>
              </tr>
            )}
            {alerts?.map((alert) => {
              const { label, className } = urgency(alert)
              return (
                <tr key={alert.id}>
                  <td className="px-4 py-3">
                    <Link
                      to={`/seafarers/${alert.seafarer_id}`}
                      className="font-medium text-navy-50 underline-offset-2 hover:underline"
                    >
                      {alert.seafarer_name}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        to={`/documents/${alert.document_id}`}
                        className="text-navy-100 underline-offset-2 hover:underline"
                      >
                        {alert.document_type_name}
                      </Link>
                      {alert.awaiting_review && <NotReviewedTag label="Awaiting review" />}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-navy-200">{alert.expiry_date}</td>
                  <td className={cn('px-4 py-3 font-medium', className)}>{label}</td>
                  <td className="px-4 py-3 text-navy-300">
                    {alert.step === 0 ? 'Expiry day' : `${alert.step} days before`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
