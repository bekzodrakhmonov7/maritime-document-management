import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useAccountAction, useAccounts, usePendingCount, type AccountAction } from '../hooks/useAccounts'
import { useVessels } from '../hooks/useReferenceData'
import { cn } from '../lib/cn'
import { BADGE_TONE } from '../lib/badgeTone'
import { ErrorNote } from '../components/ErrorNote'
import { Field, FIELD_CLASS, FormDialog, LABEL_CLASS } from '../components/FormDialog'
import { ROLE_LABELS, type Account, type AccountStatus, type UserRole } from '../types'
import { Table } from '../components/Table'

type Filter = AccountStatus | 'all'
type FormKind = AccountAction['kind']

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'pending', label: 'Pending' },
  { value: 'active', label: 'Active' },
  { value: 'deactivated', label: 'Deactivated' },
  { value: 'all', label: 'All' },
]

const STATUS_STYLE: Record<AccountStatus, string> = {
  pending: BADGE_TONE.warn,
  active: BADGE_TONE.ok,
  deactivated: BADGE_TONE.neutral,
}

const FORM_TITLE: Record<FormKind, string> = {
  approve: 'Approve account',
  role: 'Change role',
  deactivate: 'Switch off account',
  reactivate: 'Switch account back on',
  'second-factor/reset': 'Reset authenticator',
}

const ROLES = Object.keys(ROLE_LABELS) as UserRole[]

/** The actions offered for an account in each status, in display order. */
const ACTIONS: Record<AccountStatus, { kind: FormKind; label: string }[]> = {
  pending: [
    { kind: 'approve', label: 'Approve' },
    { kind: 'second-factor/reset', label: 'Reset authenticator' },
    { kind: 'deactivate', label: 'Reject' },
  ],
  active: [
    { kind: 'role', label: 'Change role' },
    { kind: 'second-factor/reset', label: 'Reset authenticator' },
    { kind: 'deactivate', label: 'Switch off' },
  ],
  deactivated: [{ kind: 'reactivate', label: 'Switch on' }],
}

/** Administrators approve, re-role and switch accounts off/on (FR-02), and
 * reset a lost authenticator (SR-03). */
export function AccountsPage() {
  const [filter, setFilter] = useState<Filter>('pending')
  const [form, setForm] = useState<{ account: Account; kind: FormKind } | null>(null)
  const { data: accounts, isLoading, error } = useAccounts(filter)
  const { data: pending } = usePendingCount(true)
  const { user } = useAuth()

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-medium text-ink">Accounts</h2>
        <p className="mt-1 text-sm text-ink-faint">
          New sign-ups wait here until you approve them with a role. Accounts are never deleted:
          switch them off instead.
        </p>
      </div>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Filter accounts by status">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            role="tab"
            aria-selected={filter === f.value}
            onClick={() => setFilter(f.value)}
            className={cn(
              'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium',
              filter === f.value
                ? 'bg-surface-active text-ink'
                : 'text-ink-muted hover:bg-surface-active hover:text-ink',
            )}
          >
            {f.label}
            {f.value === 'pending' && (pending ?? 0) > 0 && (
              <span className="text-xs font-medium text-warning">
                {pending}
              </span>
            )}
          </button>
        ))}
      </div>

      {error && <ErrorNote message={error.message} />}

      <Table
        head={['Name', 'E-mail', 'Status', 'Role', 'Last reason', { label: 'Actions', className: 'text-right' }]}
        loading={isLoading}
        empty={accounts?.length === 0 ? 'No accounts here.' : null}
      >
        {accounts?.map((account) => {
          const isSelf = account.id === user?.id
          return (
            <tr key={account.id}>
              <td className="px-4 py-3 text-ink">{account.full_name}</td>
              <td className="px-4 py-3 text-ink-muted">{account.email}</td>
              <td className="px-4 py-3">
                <span
                  className={cn(
                    'rounded-full px-2.5 py-1 text-xs font-medium capitalize',
                    STATUS_STYLE[account.status],
                  )}
                >
                  {account.status}
                </span>
              </td>
              <td className="px-4 py-3 text-ink-muted">
                {account.role ? ROLE_LABELS[account.role] : '—'}
              </td>
              <td className="max-w-xs truncate px-4 py-3 text-ink-faint" title={account.status_reason ?? ''}>
                {account.status_reason ?? '—'}
              </td>
              <td className="px-4 py-3 text-right">
                {isSelf ? (
                  <span className="text-xs text-ink-faint">You</span>
                ) : (
                  <div className="flex justify-end gap-2">
                    {ACTIONS[account.status].map(({ kind, label }) => (
                      <button
                        key={kind}
                        type="button"
                        onClick={() => setForm({ account, kind })}
                        className={cn(
                          'h-8 shrink-0 whitespace-nowrap rounded-md border border-line-strong bg-canvas px-3 text-sm font-medium hover:bg-surface-active focus:outline-none focus:ring-2 focus:ring-accent/40',
                          kind === 'deactivate' ? 'text-danger' : 'text-ink',
                        )}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                )}
              </td>
            </tr>
          )
        })}
      </Table>

      {form && (
        <AccountForm
          key={`${form.account.id}-${form.kind}`}
          account={form.account}
          kind={form.kind}
          onClose={() => setForm(null)}
        />
      )}
    </div>
  )
}

/** The request body for a form; null when a required role is missing. */
function buildAction(
  kind: FormKind,
  reason: string,
  role: UserRole | undefined,
  vesselIds: number[],
): AccountAction | null {
  switch (kind) {
    case 'deactivate':
    case 'second-factor/reset':
      return { kind, reason }
    case 'reactivate':
      return role ? { kind, reason, role } : { kind, reason }
    case 'approve':
      if (!role) return null
      // Only a crewing officer is given vessels (Responsible Officer links).
      return role === 'crewing_officer'
        ? { kind, reason, role, vessel_ids: vesselIds }
        : { kind, reason, role }
    case 'role':
      return role ? { kind, reason, role } : null
  }
}

function AccountForm({
  account,
  kind,
  onClose,
}: {
  account: Account
  kind: FormKind
  onClose: () => void
}) {
  const needsRole = kind === 'approve' || kind === 'role' || (kind === 'reactivate' && !account.role)
  const [role, setRole] = useState<UserRole | ''>(kind === 'role' ? '' : (account.role ?? ''))
  const [reason, setReason] = useState('')
  const [vesselIds, setVesselIds] = useState<number[]>([])
  const action = useAccountAction()
  const pickVessels = kind === 'approve' && role === 'crewing_officer'
  const { data: vessels } = useVessels()
  const trimmedReason = reason.trim()
  const payload = buildAction(kind, trimmedReason, needsRole && role ? role : undefined, vesselIds)
  const canSubmit = !!trimmedReason && (!needsRole || !!role) && payload !== null

  return (
    <FormDialog
      title={FORM_TITLE[kind]}
      subtitle={`${account.full_name} · ${account.email}`}
      submitLabel={FORM_TITLE[kind]}
      onSubmit={() => payload && action.mutate({ id: account.id, action: payload }, { onSuccess: onClose })}
      onClose={onClose}
      pending={action.isPending}
      canSubmit={canSubmit}
      error={action.error}
    >
      {needsRole && (
        <Field id="account-role" label="Role">
          <select
            id="account-role"
            required
            value={role}
            onChange={(e) => setRole(e.target.value as UserRole)}
            className={FIELD_CLASS}
          >
            <option value="" disabled>
              Pick a role
            </option>
            {ROLES.filter((r) => kind !== 'role' || r !== account.role).map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r]}
              </option>
            ))}
          </select>
          {kind === 'role' && account.role === 'crewing_officer' && (
            <p className="mt-1 text-xs text-warning">
              Changing a crewing officer's role removes their vessel links.
            </p>
          )}
        </Field>
      )}

      {pickVessels && (
        <fieldset>
          <legend className={LABEL_CLASS}>Vessels (Responsible Officer)</legend>
          <p className="mb-2 text-xs text-ink-faint">
            Leave empty to start with the Unassigned Pool only.
          </p>
          <div className="max-h-40 space-y-1 overflow-y-auto rounded-md border border-line-strong bg-canvas p-2">
            {(vessels ?? [])
              .filter((v) => v.active)
              .map((v) => (
                <label key={v.id} className="flex items-center gap-2 text-sm text-ink">
                  <input
                    type="checkbox"
                    checked={vesselIds.includes(v.id)}
                    onChange={(e) =>
                      setVesselIds((ids) =>
                        e.target.checked ? [...ids, v.id] : ids.filter((id) => id !== v.id),
                      )
                    }
                    className="h-4 w-4 rounded border-line-strong bg-canvas"
                  />
                  {v.name}
                </label>
              ))}
          </div>
        </fieldset>
      )}

      {kind === 'second-factor/reset' && (
        <p className="text-sm text-ink-muted">
          Use this when they have lost their authenticator app. They are signed out, and at their
          next sign-in they set up a new authenticator with their password.
        </p>
      )}

      {kind === 'deactivate' && (
        <p className="text-sm text-ink-muted">
          {account.status === 'pending'
            ? 'The sign-up is kept as a deactivated account. It can be switched on later.'
            : 'They are refused and signed out on their next request.'}
        </p>
      )}

      <Field id="account-reason" label="Reason">
        <textarea
          id="account-reason"
          required
          rows={3}
          maxLength={1000}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className={FIELD_CLASS}
          placeholder="Recorded in the Audit Log"
        />
      </Field>
    </FormDialog>
  )
}
