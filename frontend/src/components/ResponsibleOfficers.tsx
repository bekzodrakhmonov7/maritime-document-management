import { useState } from 'react'
import { useAccounts } from '../hooks/useAccounts'
import { useResponsibleOfficerAction, useResponsibleOfficers } from '../hooks/useAssignments'
import { ActionButton } from './ActionButton'
import { ErrorNote } from './ErrorNote'
import { FIELD_CLASS } from './FormDialog'
import { StateBadge } from './StateBadge'

/** A vessel's Responsible Officers. Administrators link and unlink active
 * crewing officers; a deactivated officer's link is kept but ignored. */
export function ResponsibleOfficers({ vesselId, isAdmin }: { vesselId: number; isAdmin: boolean }) {
  const { data: officers, error } = useResponsibleOfficers(vesselId)
  const action = useResponsibleOfficerAction(vesselId)
  const [picked, setPicked] = useState('')
  const { data: accounts } = useAccounts('active', isAdmin)
  const linked = new Set(officers?.map((o) => o.id))
  const candidates = (accounts ?? []).filter((a) => a.role === 'crewing_officer' && !linked.has(a.id))

  return (
    <section className="space-y-3">
      <h3 className="text-lg font-semibold text-navy-50">Responsible Officers</h3>
      {error && <ErrorNote message={error.message} />}
      {action.error && <ErrorNote message={action.error.message} />}
      <ul className="divide-y divide-navy-800 rounded-xl border border-navy-800 bg-navy-900">
        {officers?.length === 0 && (
          <li className="px-4 py-3 text-sm text-navy-400">
            No Responsible Officer: only administrators manage this vessel's crew.
          </li>
        )}
        {officers?.map((officer) => (
          <li key={officer.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
            <div className="flex items-center gap-3">
              <span className="text-navy-50">{officer.full_name || officer.email}</span>
              <span className="text-navy-400">{officer.email}</span>
              {officer.status !== 'active' && (
                <StateBadge on={false} label="Deactivated: link ignored" />
              )}
            </div>
            {isAdmin && (
              <ActionButton
                tone="danger"
                disabled={action.isPending}
                onClick={() => action.mutate({ kind: 'remove', accountId: officer.id })}
              >
                Remove
              </ActionButton>
            )}
          </li>
        ))}
      </ul>
      {isAdmin && (
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (picked)
              action.mutate({ kind: 'add', accountId: picked }, { onSuccess: () => setPicked('') })
          }}
        >
          <label htmlFor="responsible-officer-pick" className="sr-only">
            Crewing officer
          </label>
          <select
            id="responsible-officer-pick"
            value={picked}
            onChange={(e) => setPicked(e.target.value)}
            className={`${FIELD_CLASS} max-w-xs`}
          >
            <option value="">Pick a crewing officer</option>
            {candidates.map((a) => (
              <option key={a.id} value={a.id}>
                {a.full_name || a.email}
              </option>
            ))}
          </select>
          <ActionButton type="submit" disabled={!picked || action.isPending}>
            Add Responsible Officer
          </ActionButton>
        </form>
      )}
    </section>
  )
}
