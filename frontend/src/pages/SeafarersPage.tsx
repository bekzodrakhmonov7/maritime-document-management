import { useState, useEffect, useMemo, type FormEvent } from 'react'
import {
  Users,
  Plus,
  Pencil,
  Trash2,
  X,
  Loader2,
  AlertCircle,
  Filter,
} from 'lucide-react'
import {
  useSeafarers,
  useCreateSeafarer,
  useUpdateSeafarer,
  useDeleteSeafarer,
} from '../hooks/useSeafarers'
import { useVessels } from '../hooks/useVessels'
import { useAuth } from '../context/AuthContext'
import type { Seafarer, SeafarerCreateInput, SeafarerQueryParams } from '../types'

const COMMON_RANKS = [
  'Master',
  'Chief Officer',
  'Chief Engineer',
  'Second Officer',
  'Third Officer',
  'Bosun',
  'AB Seaman',
  'Oiler',
  'Cook',
  'Ordinary Seaman',
]

export function SeafarersPage() {
  const { role } = useAuth()
  const [vesselFilter, setVesselFilter] = useState<string>('')
  const [rankFilter, setRankFilter] = useState<string>('')

  const params: SeafarerQueryParams = useMemo(() => {
    const p: SeafarerQueryParams = { limit: 100 }
    if (vesselFilter) p.vessel_id = Number(vesselFilter)
    if (rankFilter) p.rank = rankFilter
    return p
  }, [vesselFilter, rankFilter])

  const seafarersQuery = useSeafarers(params)
  const vesselsQuery = useVessels()
  const createMutation = useCreateSeafarer()
  const updateMutation = useUpdateSeafarer()
  const deleteMutation = useDeleteSeafarer()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingSeafarer, setEditingSeafarer] = useState<Seafarer | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Seafarer | null>(null)

  const canManage = role === 'administrator' || role === 'crewing_officer'
  const seafarers = seafarersQuery.data ?? []
  const vessels = vesselsQuery.data ?? []

  const availableRanks = useMemo(() => {
    const ranks = new Set<string>(COMMON_RANKS)
    for (const s of seafarers) {
      ranks.add(s.rank)
    }
    return Array.from(ranks).sort()
  }, [seafarers])

  const openCreate = () => {
    setEditingSeafarer(null)
    setDialogOpen(true)
  }

  const openEdit = (seafarer: Seafarer) => {
    setEditingSeafarer(seafarer)
    setDialogOpen(true)
  }

  const handleDelete = (seafarer: Seafarer) => {
    deleteMutation.mutate(seafarer.seafarer_id, {
      onSuccess: () => setDeleteTarget(null),
    })
  }

  const hasFilters = vesselFilter !== '' || rankFilter !== ''

  const clearFilters = () => {
    setVesselFilter('')
    setRankFilter('')
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Users className="h-5 w-5 text-navy-300" aria-hidden="true" />
            <h1 className="text-xl font-bold tracking-tight text-navy-50">
              Seafarers
            </h1>
          </div>
          <p className="mt-1 text-sm text-navy-400">
            Manage seafarer crew records
          </p>
        </div>
        {canManage && (
          <button
            type="button"
            onClick={openCreate}
            disabled={vessels.length === 0}
            className="inline-flex items-center gap-2 rounded-lg bg-navy-600 px-4 py-2.5 text-sm font-medium text-navy-50 transition-colors hover:bg-navy-500 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:cursor-not-allowed disabled:opacity-50"
            title={vessels.length === 0 ? 'Add a vessel first' : undefined}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add Seafarer
          </button>
        )}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex items-center gap-2 text-sm text-navy-300">
          <Filter className="h-4 w-4" aria-hidden="true" />
          <span className="font-medium">Filters</span>
        </div>
        <div className="flex-1">
          <label htmlFor="vessel-filter" className="mb-1.5 block text-xs font-medium text-navy-400">
            Vessel
          </label>
          <select
            id="vessel-filter"
            value={vesselFilter}
            onChange={(e) => setVesselFilter(e.target.value)}
            className="w-full rounded-lg border border-navy-700 bg-navy-950 px-3 py-2 text-sm text-navy-50 transition-colors focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
          >
            <option value="">All vessels</option>
            {vessels.map((v) => (
              <option key={v.vessel_id} value={v.vessel_id}>
                {v.vessel_name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1">
          <label htmlFor="rank-filter" className="mb-1.5 block text-xs font-medium text-navy-400">
            Rank
          </label>
          <select
            id="rank-filter"
            value={rankFilter}
            onChange={(e) => setRankFilter(e.target.value)}
            className="w-full rounded-lg border border-navy-700 bg-navy-950 px-3 py-2 text-sm text-navy-50 transition-colors focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
          >
            <option value="">All ranks</option>
            {availableRanks.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
        {hasFilters && (
          <button
            type="button"
            onClick={clearFilters}
            className="rounded-lg px-3 py-2 text-sm font-medium text-navy-300 transition-colors hover:bg-navy-800 hover:text-navy-100 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
          >
            Clear
          </button>
        )}
      </div>

      {seafarersQuery.isLoading && (
        <div className="flex items-center justify-center rounded-xl border border-navy-800 bg-navy-900 p-12">
          <Loader2 className="h-6 w-6 animate-spin text-navy-300" />
          <span className="ml-3 text-sm text-navy-300">Loading seafarers...</span>
        </div>
      )}

      {seafarersQuery.isError && (
        <div
          role="alert"
          className="flex items-center gap-3 rounded-xl border border-status-expired/40 bg-status-expired-bg/10 p-6"
        >
          <AlertCircle className="h-5 w-5 shrink-0 text-status-expired" />
          <p className="text-sm text-status-expired">
            Failed to load seafarers. Please try again later.
          </p>
        </div>
      )}

      {!seafarersQuery.isLoading && !seafarersQuery.isError && seafarers.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-xl border border-navy-800 bg-navy-900 p-12">
          <Users className="mb-3 h-8 w-8 text-navy-500" />
          <p className="text-sm text-navy-400">
            {hasFilters ? 'No seafarers match the current filters.' : 'No seafarers found.'}
          </p>
        </div>
      )}

      {!seafarersQuery.isLoading && !seafarersQuery.isError && seafarers.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-navy-800 bg-navy-900">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-navy-800 bg-navy-800">
                <tr>
                  <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                    Name
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                    Rank
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                    Vessel
                  </th>
                  {canManage && (
                    <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                      Actions
                    </th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-navy-800">
                {seafarers.map((seafarer) => (
                  <tr
                    key={seafarer.seafarer_id}
                    className="transition-colors hover:bg-navy-800/50"
                  >
                    <td className="px-4 py-3 whitespace-nowrap font-medium text-navy-50">
                      {seafarer.first_name} {seafarer.last_name}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-navy-200">
                      {seafarer.rank}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-navy-200">
                      {seafarer.vessel_name}
                    </td>
                    {canManage && (
                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => openEdit(seafarer)}
                            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-navy-300 transition-colors hover:bg-navy-700 hover:text-navy-100 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
                            aria-label={`Edit seafarer ${seafarer.first_name} ${seafarer.last_name}`}
                          >
                            <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => setDeleteTarget(seafarer)}
                            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-status-expired transition-colors hover:bg-status-expired-bg/20 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
                            aria-label={`Delete seafarer ${seafarer.first_name} ${seafarer.last_name}`}
                          >
                            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                            Delete
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {dialogOpen && (
        <SeafarerDialog
          seafarer={editingSeafarer}
          vessels={vessels}
          onClose={() => setDialogOpen(false)}
          onCreate={createMutation.mutateAsync}
          onUpdate={updateMutation.mutateAsync}
          isPending={createMutation.isPending || updateMutation.isPending}
          error={createMutation.error ?? updateMutation.error}
        />
      )}

      {deleteTarget && (
        <DeleteConfirmDialog
          seafarer={deleteTarget}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => handleDelete(deleteTarget)}
          isPending={deleteMutation.isPending}
          error={deleteMutation.error}
        />
      )}
    </div>
  )
}

interface SeafarerDialogProps {
  seafarer: Seafarer | null
  vessels: { vessel_id: number; vessel_name: string }[]
  onClose: () => void
  onCreate: (input: SeafarerCreateInput) => Promise<unknown>
  onUpdate: (args: { seafarerId: number; input: Partial<SeafarerCreateInput> }) => Promise<unknown>
  isPending: boolean
  error: Error | null
}

function SeafarerDialog({
  seafarer,
  vessels,
  onClose,
  onCreate,
  onUpdate,
  isPending,
  error,
}: SeafarerDialogProps) {
  const [firstName, setFirstName] = useState(seafarer?.first_name ?? '')
  const [lastName, setLastName] = useState(seafarer?.last_name ?? '')
  const [rank, setRank] = useState(seafarer?.rank ?? '')
  const [vesselId, setVesselId] = useState(
    seafarer ? String(seafarer.vessel_id) : '',
  )
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [onClose])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setFormError(null)

    if (!firstName.trim()) {
      setFormError('First name is required.')
      return
    }
    if (!lastName.trim()) {
      setFormError('Last name is required.')
      return
    }
    if (!rank.trim()) {
      setFormError('Rank is required.')
      return
    }
    if (!vesselId) {
      setFormError('Please assign a vessel.')
      return
    }

    try {
      const payload = {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        rank: rank.trim(),
        vessel_id: Number(vesselId),
      }

      if (seafarer) {
        await onUpdate({ seafarerId: seafarer.seafarer_id, input: payload })
      } else {
        await onCreate(payload)
      }
      onClose()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Operation failed.')
    }
  }

  const inputClass =
    'w-full rounded-lg border border-navy-700 bg-navy-950 px-4 py-2.5 text-navy-50 placeholder-navy-500 transition-colors focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50'
  const labelClass = 'mb-2 block text-sm font-medium text-navy-100'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/80 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="seafarer-dialog-title"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-navy-800 bg-navy-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Users className="h-5 w-5 text-navy-300" aria-hidden="true" />
            <h2 id="seafarer-dialog-title" className="text-lg font-semibold text-navy-50">
              {seafarer ? 'Edit Seafarer' : 'Add Seafarer'}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-navy-400 transition-colors hover:bg-navy-800 hover:text-navy-100 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
            aria-label="Close dialog"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          {(formError || error) && (
            <div
              role="alert"
              className="flex items-start gap-3 rounded-lg border border-status-expired/40 bg-status-expired-bg/10 p-4"
            >
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-status-expired" />
              <p className="text-sm text-status-expired">{formError ?? error?.message}</p>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="firstName" className={labelClass}>
                First Name
              </label>
              <input
                id="firstName"
                type="text"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                disabled={isPending}
                required
                maxLength={255}
                className={inputClass}
                placeholder="e.g. John"
                aria-required="true"
              />
            </div>
            <div>
              <label htmlFor="lastName" className={labelClass}>
                Last Name
              </label>
              <input
                id="lastName"
                type="text"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                disabled={isPending}
                required
                maxLength={255}
                className={inputClass}
                placeholder="e.g. Smith"
                aria-required="true"
              />
            </div>
          </div>

          <div>
            <label htmlFor="rank" className={labelClass}>
              Rank
            </label>
            <input
              id="rank"
              type="text"
              value={rank}
              onChange={(e) => setRank(e.target.value)}
              disabled={isPending}
              required
              maxLength={255}
              className={inputClass}
              placeholder="e.g. Chief Officer"
              aria-required="true"
              list="common-ranks"
            />
            <datalist id="common-ranks">
              {COMMON_RANKS.map((r) => (
                <option key={r} value={r} />
              ))}
            </datalist>
          </div>

          <div>
            <label htmlFor="vesselAssign" className={labelClass}>
              Vessel
            </label>
            <select
              id="vesselAssign"
              value={vesselId}
              onChange={(e) => setVesselId(e.target.value)}
              disabled={isPending}
              required
              className={inputClass}
              aria-required="true"
            >
              <option value="">Select a vessel</option>
              {vessels.map((v) => (
                <option key={v.vessel_id} value={v.vessel_id}>
                  {v.vessel_name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isPending}
              className="rounded-lg px-4 py-2.5 text-sm font-medium text-navy-300 transition-colors hover:bg-navy-800 hover:text-navy-100 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="inline-flex items-center gap-2 rounded-lg bg-navy-600 px-4 py-2.5 text-sm font-medium text-navy-50 transition-colors hover:bg-navy-500 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {isPending ? 'Saving...' : seafarer ? 'Save Changes' : 'Add Seafarer'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

interface DeleteConfirmDialogProps {
  seafarer: Seafarer
  onCancel: () => void
  onConfirm: () => void
  isPending: boolean
  error: Error | null
}

function DeleteConfirmDialog({
  seafarer,
  onCancel,
  onConfirm,
  isPending,
  error,
}: DeleteConfirmDialogProps) {
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [onCancel])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/80 p-4"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="delete-seafarer-title"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md rounded-xl border border-navy-800 bg-navy-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center gap-2">
          <Trash2 className="h-5 w-5 text-status-expired" aria-hidden="true" />
          <h2 id="delete-seafarer-title" className="text-lg font-semibold text-navy-50">
            Delete Seafarer
          </h2>
        </div>

        <p className="text-sm text-navy-300">
          Are you sure you want to delete{' '}
          <span className="font-semibold text-navy-50">
            {seafarer.first_name} {seafarer.last_name}
          </span>{' '}
          ({seafarer.rank})? This action cannot be undone.
        </p>

        {error && (
          <div
            role="alert"
            className="mt-4 flex items-start gap-3 rounded-lg border border-status-expired/40 bg-status-expired-bg/10 p-4"
          >
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-status-expired" />
            <p className="text-sm text-status-expired">{error.message}</p>
          </div>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={isPending}
            className="rounded-lg px-4 py-2.5 text-sm font-medium text-navy-300 transition-colors hover:bg-navy-800 hover:text-navy-100 focus:outline-none focus:ring-2 focus:ring-navy-400/40 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isPending}
            className="inline-flex items-center gap-2 rounded-lg bg-status-expired px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-status-expired/90 focus:outline-none focus:ring-2 focus:ring-status-expired/40 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {isPending ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  )
}
