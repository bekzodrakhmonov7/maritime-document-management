import { useState } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useDocumentTypes, usePositions, useVessels } from '../hooks/useReferenceData'
import {
  useEvaluation,
  useMatrix,
  useRequirementAction,
  useRequirementExceptions,
} from '../hooks/useRequirements'
import type {
  ExceptionEffect,
  RequirementException,
  RequirementExceptionWrite,
} from '../types'
import { cn } from '../lib/cn'
import { FLAG_OPTIONS, flagLabel } from '../lib/flags'
import { ActionButton } from '../components/ActionButton'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { ErrorNote } from '../components/ErrorNote'
import { FIELD_CLASS, FormDialog, LABEL_CLASS } from '../components/FormDialog'

type Tab = 'matrix' | 'exceptions' | 'preview'

const TABS: { id: Tab; label: string }[] = [
  { id: 'matrix', label: 'Matrix' },
  { id: 'exceptions', label: 'Exceptions' },
  { id: 'preview', label: 'Preview' },
]

const TABLE_CLASS = 'overflow-x-auto rounded-xl border border-navy-800 bg-navy-900'
const HEAD_CLASS = 'border-b border-navy-800 text-xs uppercase tracking-wider text-navy-400'

/** Which documents each Position needs, and the local exceptions (administrators only). */
export function RequirementsPage() {
  const [tab, setTab] = useState<Tab>('matrix')

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-navy-50">Requirements</h2>
        <p className="mt-1 text-sm text-navy-400">
          The matrix says which Document Types each Position needs. Exceptions add or remove one for
          a vessel or a flag: a vessel exception beats a flag one, and one for a single Position beats
          one for all.
        </p>
      </div>

      <div role="tablist" aria-label="Requirements" className="flex gap-1 border-b border-navy-800">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            onClick={() => setTab(t.id)}
            className={cn(
              '-mb-px border-b-2 px-4 py-2 text-sm font-medium',
              tab === t.id
                ? 'border-navy-300 text-navy-50'
                : 'border-transparent text-navy-400 hover:text-navy-100',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === 'matrix' && <MatrixTab />}
        {tab === 'exceptions' && <ExceptionsTab />}
        {tab === 'preview' && <PreviewTab />}
      </div>
    </div>
  )
}

// --- Matrix ---------------------------------------------------------------------------

function MatrixTab() {
  const positions = usePositions()
  const types = useDocumentTypes()
  const matrix = useMatrix()
  const action = useRequirementAction()

  const activePositions = positions.data?.filter((p) => !p.retired) ?? []
  const activeTypes = types.data?.filter((t) => !t.retired) ?? []
  const cells = new Set(matrix.data?.map((c) => `${c.position_id}/${c.document_type_id}`))
  const error = positions.error ?? types.error ?? matrix.error ?? action.error

  if (positions.isLoading || types.isLoading || matrix.isLoading) {
    return <p className="text-sm text-navy-400">Loading…</p>
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-navy-400">
        Tick a box to require a type for a Position. Retired Positions and types are not shown and
        never count as required. Clearing a certificate leaves its Endorsements as they are.
      </p>
      {error && <ErrorNote message={error.message} />}
      {activePositions.length === 0 || activeTypes.length === 0 ? (
        <p className="text-sm text-navy-400">Add Positions and Document Types first.</p>
      ) : (
        <div className={TABLE_CLASS}>
          <table className="w-full text-left text-sm">
            <thead className={HEAD_CLASS}>
              <tr>
                <th scope="col" className="px-4 py-3">
                  Document Type
                </th>
                {activePositions.map((p) => (
                  <th key={p.id} scope="col" className="px-3 py-3 text-center">
                    {p.name}
                  </th>
                ))}
                <th scope="col" className="px-4 py-3 text-right">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-navy-800">
              {activeTypes.map((t) => {
                const missing = activePositions.filter((p) => !cells.has(`${p.id}/${t.id}`))
                return (
                  <tr key={t.id}>
                    <th scope="row" className="px-4 py-3 font-normal text-navy-50">
                      {t.name}
                      {t.depends_on_id !== null && (
                        <span className="ml-2 text-xs text-navy-400">Endorsement</span>
                      )}
                    </th>
                    {activePositions.map((p) => {
                      const set = cells.has(`${p.id}/${t.id}`)
                      return (
                        <td key={p.id} className="px-3 py-3 text-center">
                          <input
                            type="checkbox"
                            checked={set}
                            disabled={action.isPending}
                            aria-label={`${p.name} needs ${t.name}`}
                            onChange={() =>
                              action.mutate({
                                kind: set ? 'clear' : 'set',
                                positionId: p.id,
                                documentTypeId: t.id,
                              })
                            }
                            className="h-4 w-4 accent-navy-400"
                          />
                        </td>
                      )
                    })}
                    <td className="px-4 py-3 text-right">
                      <ActionButton
                        disabled={missing.length === 0 || action.isPending}
                        onClick={() => action.mutate({ kind: 'add-to-all', documentTypeId: t.id })}
                      >
                        Add to all positions
                      </ActionButton>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// --- Exceptions -----------------------------------------------------------------------

type ExceptionDialog =
  | { kind: 'create' }
  | { kind: 'edit' | 'delete'; exception: RequirementException }

function scopeLabel(e: Pick<RequirementException, 'vessel_name' | 'flag'>): string {
  return e.flag ? `Flag: ${flagLabel(e.flag)}` : `Vessel: ${e.vessel_name}`
}

function EffectBadge({ effect }: { effect: ExceptionEffect }) {
  return (
    <span
      className={cn(
        'rounded-full px-2 py-0.5 text-xs font-semibold',
        effect === 'add' ? 'bg-status-valid/20 text-status-valid' : 'bg-status-expired/20 text-status-expired',
      )}
    >
      {effect === 'add' ? 'Add' : 'Remove'}
    </span>
  )
}

function ExceptionsTab() {
  const { data: exceptions, isLoading, error } = useRequirementExceptions()
  const [dialog, setDialog] = useState<ExceptionDialog | null>(null)

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <ActionButton tone="primary" onClick={() => setDialog({ kind: 'create' })}>
          <Plus className="h-4 w-4" />
          Add exception
        </ActionButton>
      </div>
      {error && <ErrorNote message={error.message} />}
      <div className={TABLE_CLASS}>
        <table className="w-full text-left text-sm">
          <thead className={HEAD_CLASS}>
            <tr>
              <th scope="col" className="px-4 py-3">Where</th>
              <th scope="col" className="px-4 py-3">Position</th>
              <th scope="col" className="px-4 py-3">Document Type</th>
              <th scope="col" className="px-4 py-3">Effect</th>
              <th scope="col" className="px-4 py-3">Reason</th>
              <th scope="col" className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-navy-800">
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-navy-400">
                  Loading…
                </td>
              </tr>
            )}
            {exceptions?.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-navy-400">
                  No exceptions: the matrix applies everywhere.
                </td>
              </tr>
            )}
            {exceptions?.map((e) => (
              <tr key={e.id}>
                <td className="px-4 py-3 text-navy-50">{scopeLabel(e)}</td>
                <td className="px-4 py-3 text-navy-300">{e.position_name ?? 'All positions'}</td>
                <td className="px-4 py-3 text-navy-50">{e.document_type_name}</td>
                <td className="px-4 py-3">
                  <EffectBadge effect={e.effect} />
                </td>
                <td className="px-4 py-3 text-navy-300">{e.reason}</td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    <ActionButton onClick={() => setDialog({ kind: 'edit', exception: e })}>
                      <Pencil className="h-3.5 w-3.5" />
                      Edit
                    </ActionButton>
                    <ActionButton tone="danger" onClick={() => setDialog({ kind: 'delete', exception: e })}>
                      <Trash2 className="h-3.5 w-3.5" />
                      Delete
                    </ActionButton>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(dialog?.kind === 'create' || dialog?.kind === 'edit') && (
        <ExceptionForm
          exception={dialog.kind === 'edit' ? dialog.exception : null}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === 'delete' && (
        <DeleteException exception={dialog.exception} onClose={() => setDialog(null)} />
      )}
    </div>
  )
}

/** Picker options: rows that can be newly picked, plus the one already held. */
function pickable<T extends { id: number }>(rows: T[] | undefined, ok: (row: T) => boolean, held: number | null) {
  return rows?.filter((row) => ok(row) || row.id === held) ?? []
}

function ExceptionForm({
  exception,
  onClose,
}: {
  exception: RequirementException | null
  onClose: () => void
}) {
  const { data: vessels } = useVessels()
  const { data: positions } = usePositions()
  const { data: types } = useDocumentTypes()
  const action = useRequirementAction()

  const [scope, setScope] = useState<'flag' | 'vessel'>(exception?.vessel_id ? 'vessel' : 'flag')
  const [flag, setFlag] = useState(exception?.flag ?? '')
  const [vesselId, setVesselId] = useState(exception?.vessel_id ? String(exception.vessel_id) : '')
  const [positionId, setPositionId] = useState(exception?.position_id ? String(exception.position_id) : '')
  const [typeId, setTypeId] = useState(exception ? String(exception.document_type_id) : '')
  const [effect, setEffect] = useState<ExceptionEffect>(exception?.effect ?? 'add')
  const [reason, setReason] = useState(exception?.reason ?? '')

  const body: RequirementExceptionWrite = {
    vessel_id: scope === 'vessel' && vesselId ? Number(vesselId) : null,
    flag: scope === 'flag' && flag ? flag : null,
    position_id: positionId ? Number(positionId) : null,
    document_type_id: Number(typeId),
    effect,
    reason: reason.trim(),
  }
  const canSubmit = (body.vessel_id !== null || body.flag !== null) && !!typeId && !!body.reason

  const vesselOptions = pickable(vessels, (v) => v.active, exception?.vessel_id ?? null)
  const positionOptions = pickable(positions, (p) => !p.retired, exception?.position_id ?? null)
  const typeOptions = pickable(types, (t) => !t.retired, exception?.document_type_id ?? null)

  return (
    <FormDialog
      title={exception ? 'Edit exception' : 'Add exception'}
      submitLabel={exception ? 'Save' : 'Add exception'}
      onSubmit={() =>
        action.mutate(
          exception
            ? { kind: 'edit-exception', id: exception.id, body }
            : { kind: 'create-exception', body },
          { onSuccess: onClose },
        )
      }
      onClose={onClose}
      pending={action.isPending}
      canSubmit={canSubmit}
      error={action.error}
    >
      <fieldset>
        <legend className={LABEL_CLASS}>Applies to</legend>
        <div className="flex gap-4 text-sm text-navy-100">
          {(['flag', 'vessel'] as const).map((s) => (
            <label key={s} className="flex items-center gap-2">
              <input
                type="radio"
                name="exception-scope"
                checked={scope === s}
                onChange={() => setScope(s)}
                className="accent-navy-400"
              />
              {s === 'flag' ? 'Every vessel of a flag' : 'One vessel'}
            </label>
          ))}
        </div>
      </fieldset>

      {scope === 'flag' ? (
        <div>
          <label htmlFor="exception-flag" className={LABEL_CLASS}>
            Flag
          </label>
          <select
            id="exception-flag"
            value={flag}
            onChange={(e) => setFlag(e.target.value)}
            className={FIELD_CLASS}
          >
            <option value="">Pick a flag</option>
            {FLAG_OPTIONS.map((f) => (
              <option key={f.code} value={f.code}>
                {f.label}
              </option>
            ))}
          </select>
        </div>
      ) : (
        <div>
          <label htmlFor="exception-vessel" className={LABEL_CLASS}>
            Vessel
          </label>
          <select
            id="exception-vessel"
            value={vesselId}
            onChange={(e) => setVesselId(e.target.value)}
            className={FIELD_CLASS}
          >
            <option value="">Pick a vessel</option>
            {vesselOptions.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name} ({v.flag})
              </option>
            ))}
          </select>
        </div>
      )}

      <div>
        <label htmlFor="exception-position" className={LABEL_CLASS}>
          Position
        </label>
        <select
          id="exception-position"
          value={positionId}
          onChange={(e) => setPositionId(e.target.value)}
          className={FIELD_CLASS}
        >
          <option value="">All positions</option>
          {positionOptions.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="exception-type" className={LABEL_CLASS}>
          Document Type
        </label>
        <select
          id="exception-type"
          value={typeId}
          onChange={(e) => setTypeId(e.target.value)}
          className={FIELD_CLASS}
        >
          <option value="">Pick a Document Type</option>
          {typeOptions.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </div>

      <fieldset>
        <legend className={LABEL_CLASS}>Effect</legend>
        <div className="flex gap-4 text-sm text-navy-100">
          {(['add', 'remove'] as const).map((e) => (
            <label key={e} className="flex items-center gap-2">
              <input
                type="radio"
                name="exception-effect"
                checked={effect === e}
                onChange={() => setEffect(e)}
                className="accent-navy-400"
              />
              {e === 'add' ? 'Add: require it' : 'Remove: don’t require it'}
            </label>
          ))}
        </div>
      </fieldset>

      <div>
        <label htmlFor="exception-reason" className={LABEL_CLASS}>
          Reason
        </label>
        <textarea
          id="exception-reason"
          required
          maxLength={500}
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className={FIELD_CLASS}
          placeholder="e.g. Flag state requires it"
        />
      </div>
    </FormDialog>
  )
}

function DeleteException({ exception, onClose }: { exception: RequirementException; onClose: () => void }) {
  const action = useRequirementAction()
  return (
    <ConfirmDialog
      title="Delete exception"
      subtitle={`${scopeLabel(exception)} · ${exception.document_type_name}`}
      confirmLabel="Delete"
      onConfirm={() => action.mutate({ kind: 'delete-exception', id: exception.id }, { onSuccess: onClose })}
      onClose={onClose}
      pending={action.isPending}
      error={action.error}
    >
      The matrix and any other exceptions decide this type again from now on.
    </ConfirmDialog>
  )
}

// --- Preview --------------------------------------------------------------------------

function PreviewTab() {
  const { data: positions } = usePositions()
  const { data: vessels } = useVessels()
  const [positionId, setPositionId] = useState('')
  const [vesselId, setVesselId] = useState('')
  const evaluation = useEvaluation(
    positionId ? Number(positionId) : null,
    vesselId ? Number(vesselId) : null,
  )
  const result = evaluation.data

  return (
    <div className="max-w-3xl space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="preview-position" className={LABEL_CLASS}>
            Position
          </label>
          <select
            id="preview-position"
            value={positionId}
            onChange={(e) => setPositionId(e.target.value)}
            className={FIELD_CLASS}
          >
            <option value="">Pick a Position</option>
            {positions?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.retired ? ' (retired)' : ''}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="preview-vessel" className={LABEL_CLASS}>
            Vessel
          </label>
          <select
            id="preview-vessel"
            value={vesselId}
            onChange={(e) => setVesselId(e.target.value)}
            className={FIELD_CLASS}
          >
            <option value="">None (matrix only)</option>
            {vessels?.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name} ({v.flag})
              </option>
            ))}
          </select>
        </div>
      </div>

      {evaluation.error && <ErrorNote message={evaluation.error.message} />}
      {!positionId && <p className="text-sm text-navy-400">Pick a Position to see what it needs.</p>}

      {result && (
        <div className="space-y-4">
          <section className="rounded-xl border border-navy-800 bg-navy-900 p-4">
            <h3 className="text-sm font-semibold text-navy-100">
              Required ({result.required.length})
              {result.vessel && (
                <span className="font-normal text-navy-400">
                  {' '}
                  on {result.vessel.name}, flag {flagLabel(result.vessel.flag)}
                </span>
              )}
            </h3>
            {result.required.length === 0 ? (
              <p className="mt-2 text-sm text-navy-400">Nothing is required.</p>
            ) : (
              <ul className="mt-2 space-y-1 text-sm">
                {result.required.map((t) => (
                  <li key={t.id} className="flex justify-between gap-4">
                    <span className="text-navy-50">{t.name}</span>
                    <span className="text-xs text-navy-400">
                      {t.exception_id === null ? 'Matrix' : 'Added by an exception'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {result.vessel && (
            <section className="rounded-xl border border-navy-800 bg-navy-900 p-4">
              <h3 className="text-sm font-semibold text-navy-100">Exceptions applied</h3>
              {result.applied_exceptions.length === 0 ? (
                <p className="mt-2 text-sm text-navy-400">None: the matrix applies as it is.</p>
              ) : (
                <ul className="mt-2 space-y-2 text-sm">
                  {result.applied_exceptions.map((e) => (
                    <li key={e.id} className="flex flex-wrap items-center gap-2">
                      <EffectBadge effect={e.effect} />
                      <span className="text-navy-50">{e.document_type_name}</span>
                      <span className="text-navy-400">
                        · {scopeLabel(e)} · {e.position_name ?? 'All positions'} · {e.reason}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </div>
      )}
    </div>
  )
}
