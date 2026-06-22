import { useState, useEffect, type FormEvent } from 'react'
import {
  Ship,
  Plus,
  Pencil,
  Trash2,
  X,
  Loader2,
  AlertCircle,
} from 'lucide-react'
import {
  useVessels,
  useCreateVessel,
  useUpdateVessel,
  useDeleteVessel,
} from '../hooks/useVessels'
import { useAuth } from '../context/AuthContext'
import { cn } from '../lib/cn'
import type { Vessel, VesselCreateInput } from '../types'

const IMO_PATTERN = /^[0-9]{7}$/

export function VesselsPage() {
  const { role } = useAuth()
  const vesselsQuery = useVessels()
  const createMutation = useCreateVessel()
  const updateMutation = useUpdateVessel()
  const deleteMutation = useDeleteVessel()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingVessel, setEditingVessel] = useState<Vessel | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Vessel | null>(null)

  const canManage = role === 'administrator'
  const vessels = vesselsQuery.data ?? []

  const openCreate = () => {
    setEditingVessel(null)
    setDialogOpen(true)
  }

  const openEdit = (vessel: Vessel) => {
    setEditingVessel(vessel)
    setDialogOpen(true)
  }

  const handleDelete = (vessel: Vessel) => {
    deleteMutation.mutate(vessel.vessel_id, {
      onSuccess: () => setDeleteTarget(null),
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Ship className="h-5 w-5 text-navy-300" aria-hidden="true" />
            <h1 className="text-xl font-bold tracking-tight text-navy-50">
              Vessels
            </h1>
          </div>
          <p className="mt-1 text-sm text-navy-400">
            Manage vessels in your fleet
          </p>
        </div>
        {canManage && (
          <button
            type="button"
            onClick={openCreate}
            className="inline-flex items-center gap-2 rounded-lg bg-navy-600 px-4 py-2.5 text-sm font-medium text-navy-50 transition-colors hover:bg-navy-500 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add Vessel
          </button>
        )}
      </div>

      {vesselsQuery.isLoading && (
        <div className="flex items-center justify-center rounded-xl border border-navy-800 bg-navy-900 p-12">
          <Loader2 className="h-6 w-6 animate-spin text-navy-300" />
          <span className="ml-3 text-sm text-navy-300">Loading vessels...</span>
        </div>
      )}

      {vesselsQuery.isError && (
        <div
          role="alert"
          className="flex items-center gap-3 rounded-xl border border-status-expired/40 bg-status-expired-bg/10 p-6"
        >
          <AlertCircle className="h-5 w-5 shrink-0 text-status-expired" />
          <p className="text-sm text-status-expired">
            Failed to load vessels. Please try again later.
          </p>
        </div>
      )}

      {!vesselsQuery.isLoading && !vesselsQuery.isError && vessels.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-xl border border-navy-800 bg-navy-900 p-12">
          <Ship className="mb-3 h-8 w-8 text-navy-500" />
          <p className="text-sm text-navy-400">No vessels found.</p>
        </div>
      )}

      {!vesselsQuery.isLoading && !vesselsQuery.isError && vessels.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-navy-800 bg-navy-900">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-navy-800 bg-navy-800">
                <tr>
                  <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                    Vessel Name
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                    IMO Number
                  </th>
                  {canManage && (
                    <th scope="col" className="px-4 py-3 font-semibold text-navy-200 whitespace-nowrap">
                      Actions
                    </th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-navy-800">
                {vessels.map((vessel) => (
                  <tr
                    key={vessel.vessel_id}
                    className="transition-colors hover:bg-navy-800/50"
                  >
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        <Ship className="h-4 w-4 text-navy-400" aria-hidden="true" />
                        <span className="font-medium text-navy-50">{vessel.vessel_name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-navy-200 tabular-nums">
                      {vessel.imo_number}
                    </td>
                    {canManage && (
                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => openEdit(vessel)}
                            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-navy-300 transition-colors hover:bg-navy-700 hover:text-navy-100 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
                            aria-label={`Edit vessel ${vessel.vessel_name}`}
                          >
                            <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => setDeleteTarget(vessel)}
                            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-status-expired transition-colors hover:bg-status-expired-bg/20 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
                            aria-label={`Delete vessel ${vessel.vessel_name}`}
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
        <VesselDialog
          vessel={editingVessel}
          onClose={() => setDialogOpen(false)}
          onCreate={createMutation.mutateAsync}
          onUpdate={updateMutation.mutateAsync}
          isPending={createMutation.isPending || updateMutation.isPending}
          error={createMutation.error ?? updateMutation.error}
        />
      )}

      {deleteTarget && (
        <DeleteConfirmDialog
          vessel={deleteTarget}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => handleDelete(deleteTarget)}
          isPending={deleteMutation.isPending}
          error={deleteMutation.error}
        />
      )}
    </div>
  )
}

interface VesselDialogProps {
  vessel: Vessel | null
  onClose: () => void
  onCreate: (input: VesselCreateInput) => Promise<unknown>
  onUpdate: (args: { vesselId: number; input: Partial<VesselCreateInput> }) => Promise<unknown>
  isPending: boolean
  error: Error | null
}

function VesselDialog({
  vessel,
  onClose,
  onCreate,
  onUpdate,
  isPending,
  error,
}: VesselDialogProps) {
  const [vesselName, setVesselName] = useState(vessel?.vessel_name ?? '')
  const [imoNumber, setImoNumber] = useState(vessel?.imo_number ?? '')
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

    if (!vesselName.trim()) {
      setFormError('Vessel name is required.')
      return
    }
    if (!IMO_PATTERN.test(imoNumber)) {
      setFormError('IMO number must be exactly 7 digits.')
      return
    }

    try {
      if (vessel) {
        await onUpdate({
          vesselId: vessel.vessel_id,
          input: { vessel_name: vesselName.trim(), imo_number: imoNumber },
        })
      } else {
        await onCreate({
          vessel_name: vesselName.trim(),
          imo_number: imoNumber,
        })
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
      aria-labelledby="vessel-dialog-title"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl border border-navy-800 bg-navy-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Ship className="h-5 w-5 text-navy-300" aria-hidden="true" />
            <h2 id="vessel-dialog-title" className="text-lg font-semibold text-navy-50">
              {vessel ? 'Edit Vessel' : 'Add Vessel'}
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

          <div>
            <label htmlFor="vesselName" className={labelClass}>
              Vessel Name
            </label>
            <input
              id="vesselName"
              type="text"
              value={vesselName}
              onChange={(e) => setVesselName(e.target.value)}
              disabled={isPending}
              required
              maxLength={255}
              className={inputClass}
              placeholder="e.g. MV Maritime Star"
              aria-required="true"
            />
          </div>

          <div>
            <label htmlFor="imoNumber" className={labelClass}>
              IMO Number
            </label>
            <input
              id="imoNumber"
              type="text"
              value={imoNumber}
              onChange={(e) => setImoNumber(e.target.value.replace(/[^0-9]/g, '').slice(0, 7))}
              disabled={isPending}
              required
              pattern="[0-9]{7}"
              className={cn(inputClass, 'tabular-nums')}
              placeholder="7-digit number"
              aria-required="true"
              inputMode="numeric"
            />
            <p className="mt-1.5 text-xs text-navy-500">
              International Maritime Organization number (exactly 7 digits)
            </p>
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
              {isPending ? 'Saving...' : vessel ? 'Save Changes' : 'Add Vessel'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

interface DeleteConfirmDialogProps {
  vessel: Vessel
  onCancel: () => void
  onConfirm: () => void
  isPending: boolean
  error: Error | null
}

function DeleteConfirmDialog({
  vessel,
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
      aria-labelledby="delete-vessel-title"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md rounded-xl border border-navy-800 bg-navy-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center gap-2">
          <Trash2 className="h-5 w-5 text-status-expired" aria-hidden="true" />
          <h2 id="delete-vessel-title" className="text-lg font-semibold text-navy-50">
            Delete Vessel
          </h2>
        </div>

        <p className="text-sm text-navy-300">
          Are you sure you want to delete{' '}
          <span className="font-semibold text-navy-50">{vessel.vessel_name}</span>{' '}
          (IMO: {vessel.imo_number})? This action cannot be undone.
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
