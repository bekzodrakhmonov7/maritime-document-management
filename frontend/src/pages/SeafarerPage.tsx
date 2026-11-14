import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { fullName, useSeafarer } from '../hooks/useSeafarers'
import { flagLabel } from '../lib/flags'
import { ErrorNote } from '../components/ErrorNote'
import {
  SeafarerActions,
  SeafarerDialog,
  SeafarerStatusBadge,
  type SeafarerDialogState,
} from '../components/SeafarerDialogs'

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-navy-400">{label}</dt>
      <dd className="mt-1 text-navy-50">{children}</dd>
    </div>
  )
}

/** One seafarer's record: personal details and held Position. Later slices add
 * the Current Vessel and Assignments (S6), documents (S7) and missing documents (S10). */
export function SeafarerPage() {
  const { id } = useParams()
  const { data: seafarer, isLoading, error } = useSeafarer(Number(id))
  const [dialog, setDialog] = useState<SeafarerDialogState | null>(null)

  return (
    <div className="max-w-3xl space-y-6">
      <Link
        to="/seafarers"
        className="inline-flex items-center gap-1 text-sm text-navy-300 hover:text-navy-100"
      >
        <ArrowLeft className="h-4 w-4" />
        All seafarers
      </Link>

      {isLoading && <p className="text-sm text-navy-400">Loading…</p>}
      {error && <ErrorNote message={error.message} />}

      {seafarer && (
        <>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <h2 className="text-2xl font-semibold text-navy-50">{fullName(seafarer)}</h2>
              <SeafarerStatusBadge seafarer={seafarer} />
            </div>
            <SeafarerActions seafarer={seafarer} onOpen={setDialog} />
          </div>

          {seafarer.inactive_since && (
            <p className="rounded-lg border border-navy-700 bg-navy-900 p-3 text-sm text-navy-300">
              Inactive since {new Date(seafarer.inactive_since).toLocaleDateString()}:{' '}
              {seafarer.inactive_reason}
            </p>
          )}

          <dl className="grid gap-4 rounded-xl border border-navy-800 bg-navy-900 p-6 sm:grid-cols-2">
            <Detail label="Position">
              {seafarer.position_name}
              {seafarer.position_retired && (
                <span className="ml-2 text-xs text-navy-400">(retired Position)</span>
              )}
            </Detail>
            <Detail label="Nationality">
              {seafarer.nationality ? flagLabel(seafarer.nationality) : '—'}
            </Detail>
            <Detail label="Date of birth">{seafarer.date_of_birth ?? '—'}</Detail>
          </dl>
        </>
      )}

      {dialog && <SeafarerDialog state={dialog} onClose={() => setDialog(null)} />}
    </div>
  )
}
