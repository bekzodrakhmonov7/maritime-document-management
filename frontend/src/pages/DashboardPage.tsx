import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, X } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useDashboard, useFleetTotals, type DashboardFilters } from '../hooks/useDashboard'
import { useCanReportOnVessel } from '../hooks/useReports'
import { fullName } from '../hooks/useSeafarers'
import { cn } from '../lib/cn'
import { ErrorNote } from '../components/ErrorNote'
import { ReportDownloads } from '../components/ReportDownloads'
import { ExpiryStatusBadge } from '../components/ExpiryStatusBadge'
import { EndorsementCapNote } from '../components/EndorsementCapNote'
import { effectiveExpiryOf, hasCapNote } from '../lib/effectiveExpiry'
import { FIELD_CLASS } from '../components/FormDialog'
import { NotReviewedTag } from '../components/ReviewTags'
import {
  DASHBOARD_QUEUE_LABELS,
  EXPIRY_STATUS_LABELS,
  type Breakdown,
  type DashboardQueue,
  type DashboardSeafarer,
  type QueueEntry,
  type SeafarerGroup,
  type StartingSoonEntry,
  type TotalsColumn,
  type UserRole,
} from '../types'

const QUEUES: DashboardQueue[] = [
  'missing',
  'expired',
  'expiring_soon',
  'expiry_not_stated',
  'waiting_for_review',
  'starting_soon',
  'in_order',
]

// --- Click-to-filter tags ---------------------------------------------------------------

type TagKind = 'position' | 'vessel' | 'document_type'

/** A removable filter tag. A vessel tag with id null is "Ashore / Unassigned". */
interface Tag {
  kind: TagKind
  id: number | null
  name: string
}

const TAG_KIND_LABELS: Record<TagKind, string> = {
  position: 'Position',
  vessel: 'Vessel',
  document_type: 'Document type',
}

const ASHORE = 'Ashore / Unassigned'

function sameTag(a: Tag, b: Tag) {
  return a.kind === b.kind && a.id === b.id
}

function toFilters(name: string, tags: Tag[], showInactive: boolean): DashboardFilters {
  const ids = (kind: TagKind) =>
    tags.filter((t) => t.kind === kind && t.id !== null).map((t) => t.id as number)
  return {
    name,
    positionIds: ids('position'),
    vesselIds: ids('vessel'),
    ashore: tags.some((t) => t.kind === 'vessel' && t.id === null),
    documentTypeIds: ids('document_type'),
    showInactive,
  }
}

/** A value in the list that adds itself as a filter tag when clicked. */
function TagButton({ tag, onAdd, className }: { tag: Tag; onAdd: (tag: Tag) => void; className?: string }) {
  return (
    <button
      type="button"
      onClick={() => onAdd(tag)}
      title={`Filter by this ${TAG_KIND_LABELS[tag.kind].toLowerCase()}`}
      className={cn(
        'rounded-full border border-navy-700 px-2 py-0.5 text-xs text-navy-300 hover:border-navy-500 hover:text-navy-100',
        className,
      )}
    >
      {tag.name}
    </button>
  )
}

function vesselTag(seafarer: DashboardSeafarer): Tag {
  return seafarer.current_vessel_id === null
    ? { kind: 'vessel', id: null, name: ASHORE }
    : { kind: 'vessel', id: seafarer.current_vessel_id, name: seafarer.current_vessel_name ?? '' }
}

// --- Work queues -------------------------------------------------------------------------

const ACTION_LABELS = { upload: 'Upload', review: 'Review', open: 'Open' } as const

function actionLink(seafarerId: number, entry: QueueEntry): string {
  // A missing type with no Document yet is uploaded from the seafarer record.
  return entry.document_id === null ? `/seafarers/${seafarerId}` : `/documents/${entry.document_id}`
}

function GroupCard({ group, onAdd }: { group: SeafarerGroup; onAdd: (tag: Tag) => void }) {
  const s = group.seafarer
  return (
    <li className="rounded-xl border border-navy-800 bg-navy-900">
      <div className="flex flex-wrap items-center gap-2 border-b border-navy-800 px-4 py-3">
        <Link to={`/seafarers/${s.id}`} className="font-medium text-navy-50 hover:underline">
          {fullName(s)}
        </Link>
        {s.inactive && <span className="text-xs text-navy-400">(Inactive)</span>}
        <TagButton tag={{ kind: 'position', id: s.position_id, name: s.position_name }} onAdd={onAdd} />
        <TagButton tag={vesselTag(s)} onAdd={onAdd} />
      </div>
      <ul className="divide-y divide-navy-800">
        {group.entries.map((entry) => (
          <li
            key={entry.document_type_id}
            className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5"
          >
            <div className="flex flex-wrap items-center gap-2">
              <ExpiryStatusBadge status={entry.expiry_status} />
              <TagButton
                tag={{ kind: 'document_type', id: entry.document_type_id, name: entry.document_type_name }}
                onAdd={onAdd}
                className="border-transparent text-sm font-medium text-navy-100"
              />
              {entry.review_state === 'not_reviewed' && <NotReviewedTag />}
              <QueueExpiry entry={entry} />
            </div>
            <Link
              to={actionLink(s.id, entry)}
              className="rounded-lg bg-navy-700 px-3 py-1.5 text-xs font-medium text-navy-50 hover:bg-navy-600"
            >
              {ACTION_LABELS[entry.action]}
            </Link>
          </li>
        ))}
      </ul>
    </li>
  )
}

function Counter({ label, value }: { label: string; value: number }) {
  return (
    <span className="text-xs text-navy-300">
      {label} <strong className={cn(value > 0 ? 'text-navy-50' : 'text-navy-500')}>{value}</strong>
    </span>
  )
}

function StartingSoonRow({ entry, onAdd }: { entry: StartingSoonEntry; onAdd: (tag: Tag) => void }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-navy-800 bg-navy-900 px-4 py-3">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-navy-200">{entry.start_date}</span>
          <Link to={`/seafarers/${entry.seafarer.id}`} className="font-medium text-navy-50 hover:underline">
            {fullName(entry.seafarer)}
          </Link>
          <TagButton tag={{ kind: 'position', id: entry.position_id, name: entry.position_name }} onAdd={onAdd} />
          <TagButton tag={{ kind: 'vessel', id: entry.vessel_id, name: entry.vessel_name }} onAdd={onAdd} />
          <span className="text-xs text-navy-400">until {entry.end_date}</span>
        </div>
        <div className="flex flex-wrap gap-4">
          <Counter label="Before joining" value={entry.counters.before_joining} />
          <Counter label="Can be renewed at sea" value={entry.counters.renewable_at_sea} />
          <Counter label={EXPIRY_STATUS_LABELS.expiry_not_stated} value={entry.counters.expiry_not_stated} />
          <Counter label="Not reviewed" value={entry.counters.not_reviewed} />
        </div>
      </div>
      <Link
        to={`/assignments/${entry.assignment_id}/readiness`}
        className="rounded-lg bg-navy-700 px-3 py-1.5 text-xs font-medium text-navy-50 hover:bg-navy-600"
      >
        Readiness
      </Link>
    </li>
  )
}

/** Administrators (the whole fleet) and crewing officers (their Scope): work
 * queues as tabs, each entry grouped by seafarer (T10 variant C). */
function WorkQueues() {
  const [queue, setQueue] = useState<DashboardQueue>('missing')
  const [name, setName] = useState('')
  const [tags, setTags] = useState<Tag[]>([])
  const [showInactive, setShowInactive] = useState(false)
  const { data, isLoading, error } = useDashboard(toFilters(name, tags, showInactive))

  const addTag = (tag: Tag) => setTags((held) => (held.some((t) => sameTag(t, tag)) ? held : [...held, tag]))
  const removeTag = (tag: Tag) => setTags((held) => held.filter((t) => !sameTag(t, tag)))
  const canReport = useCanReportOnVessel()
  // The vessel report is offered when exactly one vessel filter is active.
  const vesselTags = tags.filter((t) => t.kind === 'vessel')
  const reportVessel =
    vesselTags.length === 1 && vesselTags[0].id !== null ? { id: vesselTags[0].id, name: vesselTags[0].name } : null

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-4">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-navy-400" />
          <label htmlFor="dashboard-search" className="sr-only">
            Filter by seafarer name
          </label>
          <input
            id="dashboard-search"
            type="search"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Seafarer name"
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

      <div className="flex flex-wrap items-center gap-2" aria-live="polite">
        {tags.length === 0 ? (
          <p className="text-xs text-navy-500">
            Click a Position, vessel or document type in the list to filter by it.
          </p>
        ) : (
          <>
            {tags.map((tag) => (
              <span
                key={`${tag.kind}-${tag.id}`}
                className="inline-flex items-center gap-1 rounded-full bg-navy-700 py-0.5 pl-2.5 pr-1 text-xs text-navy-50"
              >
                <span className="text-navy-300">{TAG_KIND_LABELS[tag.kind]}:</span> {tag.name}
                <button
                  type="button"
                  onClick={() => removeTag(tag)}
                  className="rounded-full p-0.5 hover:bg-navy-600"
                  aria-label={`Remove filter ${tag.name}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            <button type="button" onClick={() => setTags([])} className="text-xs text-navy-400 hover:text-navy-200">
              Clear all
            </button>
            {reportVessel && canReport(reportVessel.id) && (
              <span className="ml-auto inline-flex items-center gap-2 text-xs text-navy-300">
                Status Report for {reportVessel.name}:
                <ReportDownloads
                  kind="vessel"
                  id={reportVessel.id}
                  label={`${reportVessel.name}'s Status Report`}
                />
              </span>
            )}
          </>
        )}
      </div>

      <div role="tablist" aria-label="Work queues" className="flex flex-wrap gap-1 border-b border-navy-800">
        {QUEUES.map((q) => (
          <button
            key={q}
            type="button"
            role="tab"
            aria-selected={queue === q}
            onClick={() => setQueue(q)}
            className={cn(
              '-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium',
              queue === q
                ? 'border-navy-300 text-navy-50'
                : 'border-transparent text-navy-400 hover:text-navy-200',
            )}
          >
            {DASHBOARD_QUEUE_LABELS[q]}
            <span className="rounded-full bg-navy-800 px-2 py-0.5 text-xs text-navy-200">
              {data?.counts[q] ?? '–'}
            </span>
          </button>
        ))}
      </div>

      {error && <ErrorNote message={error.message} />}
      {isLoading && <p className="text-sm text-navy-400">Loading…</p>}

      {data && queue === 'starting_soon' && (
        <>
          <p className="text-xs text-navy-400">
            Upcoming assignments starting within the next {data.planning_horizon_days} days, by start date.
            Position and vessel tags match the assignment; document type tags don't apply here.
          </p>
          {data.queues.starting_soon.length === 0 ? (
            <p className="text-sm text-navy-400">No assignments starting soon.</p>
          ) : (
            <ul className="space-y-2">
              {data.queues.starting_soon.map((entry) => (
                <StartingSoonRow key={entry.assignment_id} entry={entry} onAdd={addTag} />
              ))}
            </ul>
          )}
        </>
      )}

      {data && queue !== 'starting_soon' && (
        data.queues[queue].length === 0 ? (
          <p className="text-sm text-navy-400">Nothing in this queue.</p>
        ) : (
          <ul className="space-y-3">
            {data.queues[queue].map((group) => (
              <GroupCard key={group.seafarer.id} group={group} onAdd={addTag} />
            ))}
          </ul>
        )
      )}
    </div>
  )
}

// --- Fleet totals ------------------------------------------------------------------------

const TOTALS_COLUMNS: { key: TotalsColumn; label: string }[] = [
  { key: 'missing', label: 'Missing' },
  { key: 'expired', label: EXPIRY_STATUS_LABELS.expired },
  { key: 'expiring_soon', label: EXPIRY_STATUS_LABELS.expiring_soon },
  { key: 'unexpired', label: EXPIRY_STATUS_LABELS.unexpired },
  { key: 'expiry_not_stated', label: EXPIRY_STATUS_LABELS.expiry_not_stated },
  { key: 'no_expiry_date', label: EXPIRY_STATUS_LABELS.no_expiry_date },
]

const BREAKDOWN_LABELS: Record<Breakdown, string> = {
  vessel: 'Vessel',
  position: 'Position',
  document_type: 'Document type',
}

/** Managers (and administrators): fleet totals per Expiry Status plus Missing,
 * and one breakdown table. Counts only, no names. */
function FleetTotalsView() {
  const [breakdown, setBreakdown] = useState<Breakdown>('vessel')
  const { data, isLoading, error } = useFleetTotals(breakdown)

  return (
    <div className="space-y-6">
      {error && <ErrorNote message={error.message} />}
      {isLoading && <p className="text-sm text-navy-400">Loading…</p>}
      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            {TOTALS_COLUMNS.map((c) => (
              <div key={c.key} className="rounded-xl border border-navy-800 bg-navy-900 px-4 py-3">
                <p className="text-xs text-navy-400">{c.label}</p>
                <p className="text-2xl font-semibold text-navy-50">{data.totals[c.key]}</p>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <label htmlFor="breakdown" className="text-sm text-navy-300">
              Break down by
            </label>
            <select
              id="breakdown"
              value={breakdown}
              onChange={(e) => setBreakdown(e.target.value as Breakdown)}
              className={`${FIELD_CLASS} w-auto`}
            >
              {Object.entries(BREAKDOWN_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          <div className="overflow-x-auto rounded-xl border border-navy-800 bg-navy-900">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-navy-800 text-xs uppercase tracking-wider text-navy-400">
                <tr>
                  <th scope="col" className="px-4 py-3">{BREAKDOWN_LABELS[data.breakdown]}</th>
                  {TOTALS_COLUMNS.map((c) => (
                    <th key={c.key} scope="col" className="px-4 py-3 text-right">
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-navy-800">
                {data.rows.length === 0 && (
                  <tr>
                    <td colSpan={TOTALS_COLUMNS.length + 1} className="px-4 py-6 text-center text-navy-400">
                      Nothing to count yet.
                    </td>
                  </tr>
                )}
                {data.rows.map((row) => (
                  <tr key={row.id ?? 'none'}>
                    <th scope="row" className="px-4 py-3 font-medium text-navy-100">{row.name}</th>
                    {TOTALS_COLUMNS.map((c) => (
                      <td key={c.key} className="px-4 py-3 text-right text-navy-200">
                        {row.counts[c.key]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

function subtitle(shown: 'queues' | 'totals', role: UserRole | null): string {
  if (shown === 'totals') {
    return 'Fleet totals per expiry status plus missing documents. Inactive seafarers are not counted.'
  }
  if (role === 'crewing_officer') return 'Your work queues, for the seafarers in your scope.'
  return 'Work queues for the whole fleet.'
}

/** The landing page (FR-20). Administrators and crewing officers get the work
 * queues (administrators can switch to the fleet totals); managers get the
 * fleet totals only. */
export function DashboardPage() {
  const { role } = useAuth()
  const [view, setView] = useState<'queues' | 'totals'>('queues')
  const isManager = role === 'manager'
  const shown = isManager ? 'totals' : view

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold text-navy-50">Dashboard</h2>
          <p className="mt-1 text-sm text-navy-400">
            {subtitle(shown, role)}
          </p>
        </div>
        {role === 'administrator' && (
          <div className="flex gap-1 rounded-lg bg-navy-900 p-1">
            {(['queues', 'totals'] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setView(v)}
                aria-pressed={view === v}
                className={cn(
                  'rounded-md px-3 py-1.5 text-xs font-medium',
                  view === v ? 'bg-navy-700 text-navy-50' : 'text-navy-400 hover:text-navy-200',
                )}
              >
                {v === 'queues' ? 'Work queues' : 'Fleet totals'}
              </button>
            ))}
          </div>
        )}
      </div>
      {shown === 'totals' ? <FleetTotalsView /> : <WorkQueues />}
    </div>
  )
}

/** A queue entry's expiry: the own date, or the Endorsement cap note. */
function QueueExpiry({ entry }: { entry: QueueEntry }) {
  const cap = effectiveExpiryOf(entry, entry.expiry_date)
  if (entry.expiry_status && hasCapNote(cap)) return <EndorsementCapNote {...cap} />
  if (!entry.expiry_date) return null
  return <span className="text-sm text-navy-400">Expiry {entry.expiry_date}</span>
}
