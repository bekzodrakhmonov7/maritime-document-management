import { useMemo, useState, type FormEvent } from 'react'
import { ChevronLeft, ChevronRight, Download, Search } from 'lucide-react'
import { EMPTY_AUDIT_FILTERS, useAuditLog, useExportAuditLog } from '../hooks/useAuditLog'
import { ActionButton } from '../components/ActionButton'
import { ErrorNote } from '../components/ErrorNote'
import { Field, FIELD_CLASS, LABEL_CLASS } from '../components/FormDialog'
import { cn } from '../lib/cn'
import {
  AUDIT_ACTION_LABELS,
  type AuditAction,
  type AuditFilters,
  type AuditRecord,
} from '../types'
import { Table } from '../components/Table'

const PAGE_SIZE = 50
const ACTIONS = Object.entries(AUDIT_ACTION_LABELS) as [AuditAction, string][]

function actionLabel(action: string): string {
  return AUDIT_ACTION_LABELS[action as AuditAction] ?? action
}

function actor(record: AuditRecord): string {
  if (record.actor_email !== null) return record.actor_email
  return record.actor_role === 'system' ? 'System' : '—'
}

function target(record: AuditRecord): string {
  if (!record.target_type) return '—'
  return record.target_id ? `${record.target_type} ${record.target_id}` : record.target_type
}

function changes(record: AuditRecord): string | null {
  const parts: string[] = []
  if (record.before) parts.push(`before ${JSON.stringify(record.before)}`)
  if (record.after) parts.push(`after ${JSON.stringify(record.after)}`)
  return parts.length ? parts.join(' · ') : null
}

/** Search and export the Audit Log (administrators only). Each search and
 * export is itself recorded. */
export function AuditLogPage() {
  const [draft, setDraft] = useState<AuditFilters>(EMPTY_AUDIT_FILTERS)
  const [applied, setApplied] = useState<AuditFilters>(EMPTY_AUDIT_FILTERS)
  const [page, setPage] = useState(1)
  const { data, isLoading, isFetching, error } = useAuditLog(applied, page, PAGE_SIZE)
  const exportLog = useExportAuditLog()

  const formatTime = useMemo(() => {
    const format = new Intl.DateTimeFormat('en-GB', {
      dateStyle: 'medium',
      timeStyle: 'medium',
      timeZone: data?.time_zone ?? 'UTC',
    })
    return (iso: string) => format.format(new Date(iso))
  }, [data?.time_zone])

  const set = <K extends keyof AuditFilters>(key: K, value: AuditFilters[K]) =>
    setDraft((current) => ({ ...current, [key]: value }))

  const toggleAction = (action: AuditAction) =>
    set(
      'actions',
      draft.actions.includes(action)
        ? draft.actions.filter((a) => a !== action)
        : [...draft.actions, action],
    )

  const onSearch = (e: FormEvent) => {
    e.preventDefault()
    setApplied(draft)
    setPage(1)
  }

  const onClear = () => {
    setDraft(EMPTY_AUDIT_FILTERS)
    setApplied(EMPTY_AUDIT_FILTERS)
    setPage(1)
  }

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  const exported = exportLog.data

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-medium text-ink">Audit Log</h2>
          <p className="mt-1 text-sm text-ink-faint">
            Who did what and when. Nobody can change it; each search and export is recorded too.
            Times are in the company time zone{data ? ` (${data.time_zone})` : ''}.
          </p>
        </div>
        <ActionButton
          tone="primary"
          onClick={() => exportLog.mutate(applied)}
          disabled={exportLog.isPending}
        >
          <Download className="h-4 w-4" />
          {exportLog.isPending ? 'Exporting…' : 'Export CSV'}
        </ActionButton>
      </div>

      <form
        onSubmit={onSearch}
        className="space-y-4 rounded-md border border-line bg-canvas p-4"
        aria-label="Audit Log filters"
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field id="audit-from" label="From">
            <input
              id="audit-from"
              type="date"
              value={draft.date_from}
              onChange={(e) => set('date_from', e.target.value)}
              className={FIELD_CLASS}
            />
          </Field>
          <Field id="audit-to" label="To">
            <input
              id="audit-to"
              type="date"
              value={draft.date_to}
              min={draft.date_from || undefined}
              onChange={(e) => set('date_to', e.target.value)}
              className={FIELD_CLASS}
            />
          </Field>
          <Field id="audit-actor" label="Actor e-mail">
            <input
              id="audit-actor"
              type="search"
              value={draft.actor_email}
              maxLength={320}
              onChange={(e) => set('actor_email', e.target.value)}
              placeholder="Part of the e-mail"
              className={FIELD_CLASS}
            />
          </Field>
          <Field id="audit-outcome" label="Outcome">
            <select
              id="audit-outcome"
              value={draft.outcome}
              onChange={(e) => set('outcome', e.target.value as AuditFilters['outcome'])}
              className={FIELD_CLASS}
            >
              <option value="">Any</option>
              <option value="succeeded">Succeeded</option>
              <option value="refused">Refused</option>
            </select>
          </Field>
          <Field id="audit-seafarer" label="Seafarer id">
            <input
              id="audit-seafarer"
              type="number"
              min={1}
              value={draft.seafarer_id}
              onChange={(e) => set('seafarer_id', e.target.value)}
              className={FIELD_CLASS}
            />
          </Field>
          <Field id="audit-target-type" label="Target type">
            <input
              id="audit-target-type"
              value={draft.target_type}
              maxLength={100}
              onChange={(e) => set('target_type', e.target.value)}
              placeholder="e.g. vessel"
              className={FIELD_CLASS}
            />
          </Field>
          <Field id="audit-target-id" label="Target id">
            <input
              id="audit-target-id"
              value={draft.target_id}
              maxLength={200}
              onChange={(e) => set('target_id', e.target.value)}
              className={FIELD_CLASS}
            />
          </Field>
        </div>

        <fieldset>
          <legend className={LABEL_CLASS}>
            Actions {draft.actions.length > 0 && `(${draft.actions.length} chosen)`}
          </legend>
          <div className="grid max-h-48 gap-1 overflow-y-auto rounded-md border border-line p-2 sm:grid-cols-2 lg:grid-cols-3">
            {ACTIONS.map(([action, label]) => (
              <label key={action} className="flex items-center gap-2 text-sm text-ink-muted">
                <input
                  type="checkbox"
                  checked={draft.actions.includes(action)}
                  onChange={() => toggleAction(action)}
                  className="h-4 w-4 rounded border-line-strong bg-canvas"
                />
                {label}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="flex gap-2">
          <ActionButton type="submit" tone="primary">
            <Search className="h-4 w-4" />
            Search
          </ActionButton>
          <ActionButton onClick={onClear}>Clear filters</ActionButton>
        </div>
      </form>

      {error && <ErrorNote message={error.message} />}
      {exportLog.error && <ErrorNote message={exportLog.error.message} />}
      {exported && (
        <p role="status" className="text-sm text-ink-muted">
          Exported {exported.rows.toLocaleString()} records.
          {exported.truncated &&
            ' That is the export limit: narrow the search to export the rest.'}
        </p>
      )}

      <Table
        className={isFetching ? 'opacity-70' : undefined}
        head={['When', 'Actor', 'Action', 'Outcome', 'Target', 'Details']}
        loading={isLoading}
        empty={data?.items.length === 0 ? 'No Audit Records match these filters.' : null}
      >
        {data?.items.map((record) => (
          <tr key={record.id} className="align-top">
            <td className="whitespace-nowrap px-4 py-3 text-ink-muted">
              {formatTime(record.occurred_at)}
            </td>
            <td className="px-4 py-3 text-ink-muted">
              <div>{actor(record)}</div>
              {record.actor_role && record.actor_role !== 'system' && (
                <div className="text-xs text-ink-faint">{record.actor_role}</div>
              )}
            </td>
            <td className="px-4 py-3 text-ink">{actionLabel(record.action)}</td>
            <td className="px-4 py-3">
              <span
                className={cn(
                  'text-xs font-medium',
                  record.outcome === 'refused' ? 'text-danger' : 'text-ink-muted',
                )}
              >
                {record.outcome === 'refused' ? 'Refused' : 'Succeeded'}
              </span>
            </td>
            <td className="px-4 py-3 text-ink-muted">
              <div>{target(record)}</div>
              {record.seafarer_id !== null && (
                <div className="text-xs text-ink-faint">Seafarer {record.seafarer_id}</div>
              )}
            </td>
            <td className="max-w-md px-4 py-3 text-xs text-ink-muted">
              {record.reason && <div>Reason: {record.reason}</div>}
              {changes(record) && <div className="break-all font-mono">{changes(record)}</div>}
              {record.ip && <div className="text-ink-faint">IP {record.ip}</div>}
            </td>
          </tr>
        ))}
      </Table>

      {data && data.total > 0 && (
        <nav className="flex items-center justify-between text-sm text-ink-muted" aria-label="Pages">
          <span>
            {data.total.toLocaleString()} records · page {data.page} of {pages}
          </span>
          <div className="flex gap-2">
            <ActionButton disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              <ChevronLeft className="h-4 w-4" />
              Newer
            </ActionButton>
            <ActionButton disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
              Older
              <ChevronRight className="h-4 w-4" />
            </ActionButton>
          </div>
        </nav>
      )}
    </div>
  )
}
