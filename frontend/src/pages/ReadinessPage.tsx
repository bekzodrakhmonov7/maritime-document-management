import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, ChevronDown, ChevronRight, Info, UserCog } from 'lucide-react'
import { useReadiness } from '../hooks/useAssignments'
import { fullName } from '../hooks/useSeafarers'
import { flagLabel } from '../lib/flags'
import { cn } from '../lib/cn'
import { BADGE_TONE } from '../lib/badgeTone'
import { AssignmentStateBadge } from '../components/AssignmentDialogs'
import { ErrorNote } from '../components/ErrorNote'
import { EndorsementCapNote } from '../components/EndorsementCapNote'
import { ReportDownloads } from '../components/ReportDownloads'
import { effectiveExpiryOf, hasCapNote } from '../lib/effectiveExpiry'
import { missingUploadPath } from '../lib/missingUpload'
import { NotReviewedTag } from '../components/ReviewTags'
import { VerificationBadge } from '../components/verificationBadge.ts'
import { COVERAGE_LABELS, EXPIRY_STATUS_LABELS, type CoverageClass, type ReadinessEntry } from '../types'

const COVERAGE_STYLE: Record<CoverageClass, string> = {
  missing: BADGE_TONE.bad,
  runs_out_before_start: BADGE_TONE.bad,
  runs_out_during: BADGE_TONE.bad,
  expiry_not_stated: BADGE_TONE.warn,
  covers_all: BADGE_TONE.ok,
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

function EntryRow({ entry, seafarerId }: { entry: ReadinessEntry; seafarerId: number }) {
  const cap = effectiveExpiryOf(entry, entry.expiry_date)
  const capped = entry.document_id !== null && hasCapNote(cap)
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          {entry.document_id ? (
            <Link to={`/documents/${entry.document_id}`} className="font-medium text-ink hover:underline">
              {entry.name}
            </Link>
          ) : (
            <span className="font-medium text-ink">{entry.name}</span>
          )}
          {entry.document_id !== null && <VerificationBadge verified={entry.verified} />}
          {entry.review_state === 'not_reviewed' && <NotReviewedTag />}
        </div>
        {entry.suggestion && <p className="text-sm text-ink-muted">{entry.suggestion}</p>}
        {capped ? (
          <p>
            <EndorsementCapNote {...cap} />
          </p>
        ) : (
          // Always, next to the suggestion: not every suggestion names the date (FR-19).
          entry.expiry_date && <p className="text-sm text-ink-faint">Valid through {entry.expiry_date}</p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {entry.coverage === 'missing' && entry.document_id === null && (
          <Link
            to={missingUploadPath(seafarerId, entry.document_type_id)}
            className="h-8 shrink-0 whitespace-nowrap rounded-md border border-line-strong bg-canvas px-3 text-sm font-medium text-ink hover:bg-surface-active"
          >
            Upload
          </Link>
        )}
        <CoverageBadge coverage={entry.coverage} />
      </div>
    </li>
  )
}

function Bucket({
  title,
  entries,
  empty,
  seafarerId,
  folded = false,
}: {
  title: string
  seafarerId: number
  entries: ReadinessEntry[]
  empty: string
  folded?: boolean
}) {
  const [open, setOpen] = useState(!folded)
  const Chevron = open ? ChevronDown : ChevronRight
  return (
    <section className="rounded-md border border-line bg-canvas">
      <h3>
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="flex w-full items-center gap-2 px-4 py-3 text-left font-medium text-ink"
        >
          <Chevron className="h-4 w-4 text-ink-faint" aria-hidden="true" />
          {title}
          <span className="text-sm font-normal text-ink-faint">({entries.length})</span>
        </button>
      </h3>
      {open &&
        (entries.length === 0 ? (
          <p className="border-t border-line px-4 py-3 text-sm text-ink-faint">{empty}</p>
        ) : (
          <ul className="divide-y divide-line border-t border-line">
            {entries.map((e) => (
              <EntryRow key={e.document_type_id} entry={e} seafarerId={seafarerId} />
            ))}
          </ul>
        ))}
    </section>
  )
}

function Counter({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-line bg-canvas p-4">
      <dt className="text-xs text-ink-faint">{label}</dt>
      <dd className="mt-1 text-xl font-medium text-ink">{value}</dd>
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
          className="inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" />
          {seafarerName}
        </Link>
      ) : (
        <Link to="/seafarers" className="inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink">
          <ArrowLeft className="h-4 w-4" />
          All seafarers
        </Link>
      )}

      {isLoading && <p className="text-sm text-ink-faint">Loading…</p>}
      {error && <ErrorNote message={error.message} />}

      {view && a && (
        <>
          <header className="space-y-2">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="text-xl font-medium text-ink">
                Readiness: {seafarerName}
              </h2>
              <AssignmentStateBadge state={view.state} />
            </div>
            <p className="text-sm text-ink-muted">
              {a.position_name} on{' '}
              <Link to={`/vessels/${a.vessel_id}`} className="hover:underline">
                {a.vessel_name}
              </Link>{' '}
              ({flagLabel(a.vessel_flag)}), {a.start_date} → {a.end_date}
            </p>
            <div className="flex flex-wrap items-center gap-2 text-sm text-ink-muted">
              Status Report:
              <ReportDownloads kind="assignment" id={a.id} label="this assignment's Status Report" />
            </div>
          </header>

          {view.position_notice && (
            <p className="flex items-start gap-2 rounded-md border border-warning/40 p-3 text-sm text-warning">
              <UserCog className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              {view.position_notice}
            </p>
          )}

          <p
            role="note"
            className="flex items-start gap-2 rounded-md border border-line-strong bg-surface-active p-3 text-sm text-ink"
          >
            <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            This view only advises: it flags gaps and suggests renewals. It approves and blocks
            nothing; whether the seafarer may serve is decided by crewing staff.
          </p>

          <dl className="grid gap-3 sm:grid-cols-4">
            <Counter label={view.before_joining_label} value={view.counters.before_joining} />
            <Counter label="Can be renewed at sea" value={view.counters.renewable_at_sea} />
            <Counter label={EXPIRY_STATUS_LABELS.expiry_not_stated} value={view.counters.expiry_not_stated} />
            <Counter label="Not reviewed" value={view.counters.not_reviewed} />
          </dl>

          <div className="space-y-4">
            <Bucket
              title={underWay ? 'Act now: sort out as soon as possible' : 'Before joining'}
              seafarerId={a.seafarer_id}
              entries={view.buckets.before_joining}
              empty="Nothing to sort out first."
            />
            <Bucket
              title="Can be renewed at sea"
              seafarerId={a.seafarer_id}
              entries={view.buckets.renewable_at_sea}
              empty="Nothing to renew at sea."
            />
            <Bucket
              title={EXPIRY_STATUS_LABELS.expiry_not_stated}
              seafarerId={a.seafarer_id}
              entries={view.buckets.expiry_not_stated}
              empty="Every expiry is stated."
            />
            <Bucket
              title="Uploaded, not yet reviewed"
              seafarerId={a.seafarer_id}
              entries={view.buckets.not_reviewed}
              empty="Nothing awaits review."
            />
            <Bucket
              title="Covers the whole assignment"
              seafarerId={a.seafarer_id}
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
