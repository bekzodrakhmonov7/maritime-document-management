import { useState, type FormEvent } from 'react'
import { AlertCircle, Loader2, X } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useAccountAction, useAccounts, usePendingCount, type AccountAction } from '../hooks/useAccounts'
import { cn } from '../lib/cn'
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
                        {actionsFor(account).map((kind) => (
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
                            {ACTION_LABEL[account.status][kind]}
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

function actionsFor(account: Account): FormKind[] {
  switch (account.status) {
    case 'pending':
      return ['approve', 'deactivate']
    case 'active':
      return ['role', 'deactivate']
    case 'deactivated':
      return ['reactivate']
  }
}

const ACTION_LABEL: Record<AccountStatus, Partial<Record<FormKind, string>>> = {
  pending: { approve: 'Approve', deactivate: 'Reject' },
  active: { role: 'Change role', deactivate: 'Switch off' },
  deactivated: { reactivate: 'Switch on' },
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

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    const trimmed = reason.trim()
    if (!trimmed || (needsRole && !role)) return
    const payload = buildAction(kind, trimmed, needsRole && role ? role : undefined)
    if (!payload) return
    action.mutate({ id: account.id, action: payload }, { onSuccess: onClose })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/70 px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="account-form-title"
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md space-y-4 rounded-xl border border-navy-800 bg-navy-900 p-6 shadow-2xl"
      >
        <div className="flex items-start justify-between">
          <div>
            <h3 id="account-form-title" className="text-lg font-semibold text-navy-50">
              {FORM_TITLE[kind]}
            </h3>
            <p className="text-sm text-navy-400">
              {account.full_name} · {account.email}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-navy-400 hover:text-navy-100"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {needsRole && (
          <div>
            <label htmlFor="account-role" className="mb-1 block text-sm font-medium text-navy-100">
              Role
            </label>
            <select
              id="account-role"
              required
              value={role}
              onChange={(e) => setRole(e.target.value as UserRole)}
              className="w-full rounded-lg border border-navy-700 bg-navy-950 px-3 py-2 text-navy-50 focus:border-navy-400 focus:outline-none"
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
          <label htmlFor="account-reason" className="mb-1 block text-sm font-medium text-navy-100">
            Reason
          </label>
          <textarea
            id="account-reason"
            required
            rows={3}
            maxLength={1000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="w-full rounded-lg border border-navy-700 bg-navy-950 px-3 py-2 text-navy-50 focus:border-navy-400 focus:outline-none"
            placeholder="Recorded in the Audit Log"
          />
        </div>

        {action.error && <ErrorNote message={action.error.message} />}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm font-medium text-navy-300 hover:bg-navy-800"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={action.isPending || !reason.trim() || (needsRole && !role)}
            className="flex items-center gap-2 rounded-lg bg-navy-600 px-4 py-2 text-sm font-medium text-navy-50 hover:bg-navy-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {action.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {FORM_TITLE[kind]}
          </button>
        </div>
      </form>
    </div>
  )
}

function ErrorNote({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-lg border border-status-expired/40 bg-status-expired-bg/10 p-3"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-status-expired" />
      <p className="text-sm text-status-expired">{message}</p>
    </div>
  )
}
