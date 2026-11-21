import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Search } from 'lucide-react'
import { fullName, useSeafarers } from '../hooks/useSeafarers'
import { flagLabel } from '../lib/flags'
import { ActionButton } from '../components/ActionButton'
import { ErrorNote } from '../components/ErrorNote'
import { FIELD_CLASS } from '../components/FormDialog'
import {
  SeafarerDialog,
  SeafarerStatusBadge,
  type SeafarerDialogState,
} from '../components/SeafarerDialogs'

const COLUMNS = 5

/** The seafarers in the caller's Scope (FR-04). */
export function SeafarersPage() {
  const [search, setSearch] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const { data: seafarers, isLoading, error } = useSeafarers({ search, showInactive })
  const [dialog, setDialog] = useState<SeafarerDialogState | null>(null)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-medium text-ink">Seafarers</h2>
          <p className="mt-1 text-sm text-ink-faint">
            Seafarers are set Inactive, never deleted.
          </p>
        </div>
        <ActionButton tone="primary" onClick={() => setDialog({ kind: 'create' })}>
          <Plus className="h-4 w-4" />
          Add seafarer
        </ActionButton>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
          <label htmlFor="seafarer-search" className="sr-only">
            Search by name
          </label>
          <input
            id="seafarer-search"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name"
            maxLength={200}
            className={`${FIELD_CLASS} pl-9`}
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-ink-muted">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
            className="h-4 w-4 rounded border-line-strong bg-canvas"
          />
          Show inactive
        </label>
      </div>

      {error && <ErrorNote message={error.message} />}

      <div className="overflow-x-auto rounded-md border border-line bg-canvas">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line bg-surface text-xs text-ink-faint">
            <tr>
              <th scope="col" className="px-4 py-3">Name</th>
              <th scope="col" className="px-4 py-3">Position</th>
              <th scope="col" className="px-4 py-3">Nationality</th>
              <th scope="col" className="px-4 py-3">Current vessel</th>
              <th scope="col" className="px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {isLoading && (
              <tr>
                <td colSpan={COLUMNS} className="px-4 py-6 text-center text-ink-faint">
                  Loading…
                </td>
              </tr>
            )}
            {seafarers?.length === 0 && (
              <tr>
                <td colSpan={COLUMNS} className="px-4 py-6 text-center text-ink-faint">
                  {search.trim() ? 'No seafarer matches that name.' : 'No seafarers yet.'}
                </td>
              </tr>
            )}
            {seafarers?.map((seafarer) => (
              <tr key={seafarer.id}>
                <td className="px-4 py-3">
                  <Link
                    to={`/seafarers/${seafarer.id}`}
                    className="font-medium text-ink underline-offset-2 hover:underline"
                  >
                    {fullName(seafarer)}
                  </Link>
                </td>
                <td className="px-4 py-3 text-ink-muted">{seafarer.position_name}</td>
                <td className="px-4 py-3 text-ink-muted">
                  {seafarer.nationality ? flagLabel(seafarer.nationality) : '—'}
                </td>
                <td className="px-4 py-3 text-ink-muted">
                  {seafarer.current_vessel_name ?? 'Ashore'}
                </td>
                <td className="px-4 py-3">
                  <SeafarerStatusBadge seafarer={seafarer} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {dialog && <SeafarerDialog state={dialog} onClose={() => setDialog(null)} />}
    </div>
  )
}
