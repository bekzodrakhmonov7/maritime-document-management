import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useAccountAction, useAccounts, usePendingCount, type AccountAction } from '../hooks/useAccounts'
import { cn } from '../lib/cn'
import { ErrorNote } from '../components/ErrorNote'
import { FIELD_CLASS, FormDialog, LABEL_CLASS } from '../components/FormDialog'
import { ROLE_LABELS, type Account, type AccountStatus, type UserRole } from '../types'

type Filter = AccountStatus | 'all'
type FormKind = AccountAction['kind']

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'pending', label: 'Pending' },
  { value: 'active', label: 'Active' },
  { value: 'deactivated', label: 'Deactivated' },
  { value: 'all', label: 'All' },
]

const STATUS_STYLE: Record<AccountStatus, string> = {
  pending: 'bg-status-expiring-bg/10 text-status-expiring',
  active: 'bg-status-valid-bg/10 text-status-valid',
  deactivated: 'bg-status-expired-bg/10 text-status-expired',
}

const FORM_TITLE: Record<FormKind, string> = {
  approve: 'Approve account',
  role: 'Change role',
  deactivate: 'Switch off account',
  reactivate: 'Switch account back on',
}

const ROLES = Object.keys(ROLE_LABELS) as UserRole[]

/** The actions offered for an account in each status, in display order. */
const ACTIONS: Record<AccountStatus, { kind: FormKind; label: string }[]> = {
  pending: [
    { kind: 'approve', label: 'Approve' },
    { kind: 'deactivate', label: 'Reject' },
  ],
  active: [
    { kind: 'role', label: 'Change role' },
    { kind: 'deactivate', label: 'Switch off' },
  ],
  deactivated: [{ kind: 'reactivate', label: 'Switch on' }],
}

/** Administrators approve, re-role and switch accounts off/on (FR-02). */
export function AccountsPage() {
  const [filter, setFilter] = useState<Filter>('pending')
  const [form, setForm] = useState<{ account: Account; kind: FormKind } | null>(null)
  const { data: accounts, isLoading, error } = useAccounts(filter)
  const { data: pending } = usePendingCount(true)
  const { user } = useAuth()

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-navy-50">Accounts</h2>
        <p className="mt-1 text-sm text-navy-400">
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
              'flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium',
              filter === f.value
                ? 'bg-navy-700 text-navy-50'
                : 'text-navy-300 hover:bg-navy-800 hover:text-navy-100',
            )}
          >
            {f.label}
            {f.value === 'pending' && (pending ?? 0) > 0 && (
              <span className="rounded-full bg-status-expiring px-2 py-0.5 text-xs font-semibold text-navy-950">
                {pending}
              </span>
            )}
          </button>
        ))}
      </div>

      {error && <ErrorNote message={error.message} />}

      <div className="overflow-x-auto rounded-xl border border-navy-800 bg-navy-900">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-navy-800 text-xs uppercase tracking-wider text-navy-400">
            <tr>
              <th scope="col" className="px-4 py-3">Name</th>
              <th scope="col" className="px-4 py-3">E-mail</th>
              <th scope="col" className="px-4 py-3">Status</th>
              <th scope="col" className="px-4 py-3">Role</th>
              <th scope="col" className="px-4 py-3">Last reason</th>
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
            {accounts?.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-navy-400">
                  No accounts here.
                </td>
              </tr>
            )}
            {accounts?.map((account) => {
              const isSelf = account.id === user?.id
              return (
                <tr key={account.id}>
                  <td className="px-4 py-3 text-navy-50">{account.full_name}</td>
                  <td className="px-4 py-3 text-navy-200">{account.email}</td>
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
                  <td className="px-4 py-3 text-navy-200">
                    {account.role ? ROLE_LABELS[account.role] : '—'}
                  </td>
                  <td className="max-w-xs truncate px-4 py-3 text-navy-400" title={account.status_reason ?? ''}>
                    {account.status_reason ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {isSelf ? (
                      <span className="text-xs text-navy-500">You</span>
                    ) : (
                      <div className="flex justify-end gap-2">
                        {ACTIONS[account.status].map(({ kind, label }) => (
                          <button
                            key={kind}
                            type="button"
                            onClick={() => setForm({ account, kind })}
                            className={cn(
                              'rounded-lg px-3 py-1.5 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-navy-400/40',
                              kind === 'deactivate'
                                ? 'bg-navy-800 text-status-expired hover:bg-navy-700'
                                : 'bg-navy-700 text-navy-50 hover:bg-navy-600',
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
          </tbody>
        </table>
      </div>

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
): AccountAction | null {
  switch (kind) {
    case 'deactivate':
      return { kind, reason }
    case 'reactivate':
      return role ? { kind, reason, role } : { kind, reason }
    case 'approve':
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
  const action = useAccountAction()
  const trimmedReason = reason.trim()
  const payload = buildAction(kind, trimmedReason, needsRole && role ? role : undefined)
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
        <div>
          <label htmlFor="account-role" className={LABEL_CLASS}>
            Role
          </label>
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
            <p className="mt-1 text-xs text-status-expiring">
              Changing a crewing officer's role removes their vessel links.
            </p>
          )}
        </div>
      )}

      {kind === 'deactivate' && (
        <p className="text-sm text-navy-300">
          {account.status === 'pending'
            ? 'The sign-up is kept as a deactivated account. It can be switched on later.'
            : 'They are refused and signed out on their next request.'}
        </p>
      )}

      <div>
        <label htmlFor="account-reason" className={LABEL_CLASS}>
          Reason
        </label>
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
      </div>
    </FormDialog>
  )
}
