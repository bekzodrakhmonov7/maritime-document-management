import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, ChevronDown, ChevronRight, Info, UserCog } from 'lucide-react'
import { useReadiness } from '../hooks/useAssignments'
import { fullName } from '../hooks/useSeafarers'
import { flagLabel } from '../lib/flags'
import { cn } from '../lib/cn'
import { AssignmentStateBadge } from '../components/AssignmentDialogs'
import { ErrorNote } from '../components/ErrorNote'
import { NotReviewedTag, VerifiedShield } from '../components/ReviewTags'
import { COVERAGE_LABELS, type CoverageClass, type ReadinessEntry } from '../types'

const COVERAGE_STYLE: Record<CoverageClass, string> = {
  missing: 'bg-navy-800 text-navy-300',
  runs_out_before_start: 'bg-status-expired-bg/10 text-status-expired',
  runs_out_during: 'bg-status-expiring-bg/10 text-status-expiring',
  covers_all: 'bg-status-valid-bg/10 text-status-valid',
}

function CoverageBadge({ coverage }: { coverage: CoverageClass }) {
  return (
    <span
      className={cn('rounded-full px-2.5 py-1 text-xs font-medium', COVERAGE_STYLE[coverage])}
      aria-label={`Coverage: ${COVERAGE_LABELS[coverage]}`}
    >
      {COVERAGE_LABELS[coverage]}
    </span>
  )
}

function EntryRow({ entry }: { entry: ReadinessEntry }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          {entry.document_id ? (
            <Link to={`/documents/${entry.document_id}`} className="font-medium text-navy-50 hover:underline">
              {entry.name}
            </Link>
          ) : (
            <span className="font-medium text-navy-50">{entry.name}</span>
          )}
          {entry.verified && <VerifiedShield />}
          {entry.review_state === 'not_reviewed' && <NotReviewedTag />}
        </div>
        {entry.suggestion && <p className="text-sm text-navy-300">{entry.suggestion}</p>}
        {entry.expiry_date && !entry.suggestion && (
          <p className="text-sm text-navy-400">Valid through {entry.expiry_date}</p>
        )}
      </div>
      <CoverageBadge coverage={entry.coverage} />
    </li>
  )
}

function Bucket({
  title,
  entries,
  empty,
  folded = false,
}: {
  title: string
  entries: ReadinessEntry[]
  empty: string
  folded?: boolean
}) {
  const [open, setOpen] = useState(!folded)
  const Chevron = open ? ChevronDown : ChevronRight
  return (
    <section className="rounded-xl border border-navy-800 bg-navy-900">
      <h3>
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="flex w-full items-center gap-2 px-4 py-3 text-left font-semibold text-navy-50"
        >
          <Chevron className="h-4 w-4 text-navy-400" aria-hidden="true" />
          {title}
          <span className="text-sm font-normal text-navy-400">({entries.length})</span>
        </button>
      </h3>
      {open &&
        (entries.length === 0 ? (
          <p className="border-t border-navy-800 px-4 py-3 text-sm text-navy-400">{empty}</p>
        ) : (
          <ul className="divide-y divide-navy-800 border-t border-navy-800">
            {entries.map((e) => (
              <EntryRow key={e.document_type_id} entry={e} />
            ))}
          </ul>
        ))}
    </section>
  )
}

function Counter({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-navy-800 bg-navy-900 p-4">
      <dt className="text-xs uppercase tracking-wider text-navy-400">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold text-navy-50">{value}</dd>
    </div>
  )
}

/** The advice-only readiness view of one upcoming or under-way Assignment
 * (T4 variant B): header, Position notice, banner, counters, then buckets.
 * There is no overall verdict. */
export function ReadinessPage() {
  const { id } = useParams()
  const { data: view, isLoading, error } = useReadiness(Number(id))
  const a = view?.assignment
  const underWay = view?.state === 'under_way'
  const seafarerName = a && fullName({ first_name: a.seafarer_first_name, last_name: a.seafarer_last_name })

  return (
    <div className="max-w-3xl space-y-6">
      {a ? (
        <Link
          to={`/seafarers/${a.seafarer_id}`}
          className="inline-flex items-center gap-1 text-sm text-navy-300 hover:text-navy-100"
        >
          <ArrowLeft className="h-4 w-4" />
          {seafarerName}
        </Link>
      ) : (
        <Link to="/seafarers" className="inline-flex items-center gap-1 text-sm text-navy-300 hover:text-navy-100">
          <ArrowLeft className="h-4 w-4" />
          All seafarers
        </Link>
      )}

      {isLoading && <p className="text-sm text-navy-400">Loading…</p>}
      {error && <ErrorNote message={error.message} />}

      {view && a && (
        <>
          <header className="space-y-2">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="text-2xl font-semibold text-navy-50">
                Readiness: {seafarerName}
              </h2>
              <AssignmentStateBadge state={view.state} />
            </div>
            <p className="text-sm text-navy-300">
              {a.position_name} on{' '}
              <Link to={`/vessels/${a.vessel_id}`} className="hover:underline">
                {a.vessel_name}
              </Link>{' '}
              ({flagLabel(a.vessel_flag)}), {a.start_date} → {a.end_date}
            </p>
          </header>

          {view.position_notice && (
            <p className="flex items-start gap-2 rounded-lg border border-status-expiring/40 bg-status-expiring-bg/10 p-3 text-sm text-status-expiring">
              <UserCog className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              {view.position_notice}
            </p>
          )}

          <p
            role="note"
            className="flex items-start gap-2 rounded-lg border border-navy-600 bg-navy-800 p-3 text-sm text-navy-100"
          >
            <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            This view only advises: it flags gaps and suggests renewals. It approves and blocks
            nothing; whether the seafarer may serve is decided by crewing staff.
          </p>

          <dl className="grid gap-3 sm:grid-cols-3">
            <Counter label={view.before_joining_label} value={view.counters.before_joining} />
            <Counter label="Can be renewed at sea" value={view.counters.renewable_at_sea} />
            <Counter label="Not reviewed" value={view.counters.not_reviewed} />
          </dl>

          <div className="space-y-4">
            <Bucket
              title={underWay ? 'Act now: sort out as soon as possible' : 'Before joining'}
              entries={view.buckets.before_joining}
              empty="Nothing to sort out first."
            />
            <Bucket
              title="Can be renewed at sea"
              entries={view.buckets.renewable_at_sea}
              empty="Nothing to renew at sea."
            />
            <Bucket
              title="Uploaded, not yet reviewed"
              entries={view.buckets.not_reviewed}
              empty="Nothing awaits review."
            />
            <Bucket
              title="Covers the whole assignment"
              entries={view.buckets.covers_all}
              empty="Nothing else."
              folded
            />
          </div>
        </>
      )}
    </div>
  )
}
