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

const COLUMNS = 4

/** The seafarers in the caller's Scope (FR-04): the landing page until the dashboard. */
export function SeafarersPage() {
  const [search, setSearch] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const { data: seafarers, isLoading, error } = useSeafarers({ search, showInactive })
  const [dialog, setDialog] = useState<SeafarerDialogState | null>(null)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold text-navy-50">Seafarers</h2>
          <p className="mt-1 text-sm text-navy-400">
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
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-navy-400" />
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
        <label className="flex items-center gap-2 text-sm text-navy-300">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
            className="h-4 w-4 rounded border-navy-700 bg-navy-950"
          />
          Show inactive
        </label>
      </div>

      {error && <ErrorNote message={error.message} />}

      <div className="overflow-x-auto rounded-xl border border-navy-800 bg-navy-900">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-navy-800 text-xs uppercase tracking-wider text-navy-400">
            <tr>
              <th scope="col" className="px-4 py-3">Name</th>
              <th scope="col" className="px-4 py-3">Position</th>
              <th scope="col" className="px-4 py-3">Nationality</th>
              <th scope="col" className="px-4 py-3">Status</th>
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
            {seafarers?.length === 0 && (
              <tr>
                <td colSpan={COLUMNS} className="px-4 py-6 text-center text-navy-400">
                  {search.trim() ? 'No seafarer matches that name.' : 'No seafarers yet.'}
                </td>
              </tr>
            )}
            {seafarers?.map((seafarer) => (
              <tr key={seafarer.id}>
                <td className="px-4 py-3">
                  <Link
                    to={`/seafarers/${seafarer.id}`}
                    className="font-medium text-navy-50 underline-offset-2 hover:underline"
                  >
                    {fullName(seafarer)}
                  </Link>
                </td>
                <td className="px-4 py-3 text-navy-200">{seafarer.position_name}</td>
                <td className="px-4 py-3 text-navy-200">
                  {seafarer.nationality ? flagLabel(seafarer.nationality) : '—'}
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
