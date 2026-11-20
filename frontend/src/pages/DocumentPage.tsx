import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, Download, Paperclip, Pencil, ShieldQuestion, Upload, XCircle } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useDocument, useOpenProofFile, useOpenVersionFile } from '../hooks/useDocuments'
import { ActionButton } from '../components/ActionButton'
import { ErrorNote } from '../components/ErrorNote'
import { ExpiryStatusBadge } from '../components/ExpiryStatusBadge'
import { EndorsementCapNote } from '../components/EndorsementCapNote'
import { effectiveExpiryOf } from '../lib/effectiveExpiry'
import { BADGE_TONE } from '../lib/badgeTone'
import { cn } from '../lib/cn'
import { SELF_REVIEW_REASON, isOwnUpload } from '../lib/missingUpload'
import { VersionDialog, type VersionDialogState } from '../components/DocumentDialogs'
import { ReviewDialog, VerificationDialog } from '../components/ReviewDialogs'
import { NotReviewedTag, VerifiedShield } from '../components/ReviewTags'
import { EXPIRY_STATUS_LABELS, type Version } from '../types'

type CheckDialog = { kind: 'review' | 'verify'; version: Version }

/** One document: its Expiry Status, Verified shield and full history of
 * Versions, newest first, each with its Reviews and Verifications. Every file
 * is fetched through a signed, recorded link. */
export function DocumentPage() {
  const { id } = useParams()
  const { user } = useAuth()
  const { data: document, isLoading, error } = useDocument(Number(id))
  const openFile = useOpenVersionFile()
  const openProof = useOpenProofFile()
  const [dialog, setDialog] = useState<VersionDialogState | null>(null)
  const [check, setCheck] = useState<CheckDialog | null>(null)
  const canAdd = !!document && !document.seafarer_inactive && !document.document_type_retired

  return (
    <div className="max-w-4xl space-y-6">
      {document && (
        <Link
          to={`/seafarers/${document.seafarer_id}`}
          className="inline-flex items-center gap-1 text-sm text-navy-300 hover:text-navy-100"
        >
          <ArrowLeft className="h-4 w-4" />
          {document.seafarer_first_name} {document.seafarer_last_name}
        </Link>
      )}

      {isLoading && <p className="text-sm text-navy-400">Loading…</p>}
      {error && <ErrorNote message={error.message} />}

      {document && (
        <>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <h2 className="text-2xl font-semibold text-navy-50">{document.document_type_name}</h2>
              <ExpiryStatusBadge status={document.expiry_status} />
              {document.current_version?.review_state === 'not_reviewed' && <NotReviewedTag />}
              {document.verified && <VerifiedShield />}
              {document.current_version && (
                <EndorsementCapNote
                  {...effectiveExpiryOf(document, document.current_version.expiry_date)}
                />
              )}
            </div>
            {canAdd && (
              <div className="flex gap-2">
                {document.current_version && (
                  <ActionButton onClick={() => setDialog({ kind: 'details', document })}>
                    <Pencil className="h-3.5 w-3.5" />
                    Correct details
                  </ActionButton>
                )}
                <ActionButton tone="primary" onClick={() => setDialog({ kind: 'renew', document })}>
                  <Upload className="h-4 w-4" />
                  Upload new version
                </ActionButton>
              </div>
            )}
          </div>

          {openFile.error && <ErrorNote message={openFile.error.message} />}
          {openProof.error && <ErrorNote message={openProof.error.message} />}

          <section className="space-y-3">
            <h3 className="text-lg font-semibold text-navy-50">History</h3>
            <ol className="space-y-3">
              {document.versions.map((v) => (
                <li
                  key={v.id}
                  className="rounded-xl border border-navy-800 bg-navy-900 p-4"
                  aria-label={`Version ${v.number}`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-1">
                      <p className="flex flex-wrap items-center gap-2 font-medium text-navy-50">
                        Version {v.number}
                        {v.is_current && (
                          <span className="rounded-full bg-navy-700 px-2 py-0.5 text-xs text-navy-100">Current</span>
                        )}
                        <ReviewStateTag version={v} />
                      </p>
                      <p className="text-xs text-navy-400">
                        Uploaded by {v.uploaded_by_name} on {new Date(v.uploaded_at).toLocaleString()}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <ActionButton onClick={() => openFile.mutate(v.id)} disabled={openFile.isPending}>
                        <Download className="h-3.5 w-3.5" />
                        {v.original_filename}
                      </ActionButton>
                      {isOwnUpload(v.uploaded_by, user?.id) ? (
                        <span className="self-center text-xs text-navy-400">{SELF_REVIEW_REASON}</span>
                      ) : (
                        <ActionButton onClick={() => setCheck({ kind: 'review', version: v })}>
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          Review
                        </ActionButton>
                      )}
                      <ActionButton onClick={() => setCheck({ kind: 'verify', version: v })}>
                        <ShieldQuestion className="h-3.5 w-3.5" />
                        Record verification
                      </ActionButton>
                    </div>
                  </div>
                  <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-4">
                    <div>
                      <dt className="text-xs text-navy-400">Number</dt>
                      <dd className="text-navy-100">{v.document_number}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-navy-400">Issued by</dt>
                      <dd className="text-navy-100">{v.issuing_authority}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-navy-400">Issued</dt>
                      <dd className="text-navy-100">{v.issue_date}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-navy-400">Expires</dt>
                      <dd className="text-navy-100">
                        {v.expiry_date ??
                          EXPIRY_STATUS_LABELS[document.expires ? 'expiry_not_stated' : 'no_expiry_date']}
                      </dd>
                    </div>
                  </dl>
                  {v.above_max_validity && (
                    <p className="mt-2 text-xs text-status-expiring">
                      Validity longer than this type allows (at most {document.max_validity_months} months).
                    </p>
                  )}
                  {v.file_from_version_number && (
                    <p className="mt-2 text-xs text-navy-400">
                      Details corrected; same file as version {v.file_from_version_number}.
                    </p>
                  )}
                  {(v.reviews.length > 0 || v.verifications.length > 0) && (
                    <div className="mt-3 grid gap-3 border-t border-navy-800 pt-3 sm:grid-cols-2">
                      <div>
                        <h4 className="text-xs font-semibold uppercase tracking-wider text-navy-400">Reviews</h4>
                        {v.reviews.length === 0 && <p className="mt-1 text-sm text-navy-400">None yet.</p>}
                        <ul className="mt-1 space-y-2">
                          {v.reviews.map((r, i) => (
                            <li key={r.id} className={i > 0 ? 'text-sm text-navy-400' : 'text-sm text-navy-200'}>
                              <span className="font-medium">{r.decision === 'accept' ? 'Accepted' : 'Rejected'}</span>{' '}
                              by {r.reviewed_by_name} on {new Date(r.reviewed_at).toLocaleString()}
                              {i > 0 && ' (overturned)'}
                              <p className="text-navy-300">“{r.comment}”</p>
                            </li>
                          ))}
                        </ul>
                      </div>
                      <div>
                        <h4 className="text-xs font-semibold uppercase tracking-wider text-navy-400">Verifications</h4>
                        {v.verifications.length === 0 && <p className="mt-1 text-sm text-navy-400">None yet.</p>}
                        <ul className="mt-1 space-y-2">
                          {v.verifications.map((c) => (
                            <li key={c.id} className="text-sm text-navy-200">
                              <span className="font-medium">
                                {c.result === 'confirmed' ? 'Confirmed' : 'Not confirmed'}
                              </span>{' '}
                              on {c.checked_on} via {c.source}, ref. {c.reference}
                              <p className="text-xs text-navy-400">Recorded by {c.recorded_by_name}</p>
                              {c.proof_original_filename && (
                                <button
                                  type="button"
                                  onClick={() => openProof.mutate(c.id)}
                                  disabled={openProof.isPending}
                                  className="mt-1 inline-flex items-center gap-1 text-xs text-navy-200 underline hover:text-navy-50"
                                >
                                  <Paperclip className="h-3 w-3" aria-hidden="true" />
                                  {c.proof_original_filename}
                                </button>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  )}
                </li>
              ))}
            </ol>
          </section>
        </>
      )}

      {dialog && <VersionDialog state={dialog} onClose={() => setDialog(null)} />}
      {check?.kind === 'review' && <ReviewDialog version={check.version} onClose={() => setCheck(null)} />}
      {check?.kind === 'verify' && <VerificationDialog version={check.version} onClose={() => setCheck(null)} />}
    </div>
  )
}

/** Not reviewed, accepted or rejected: the Version's latest Review. */
function ReviewStateTag({ version }: { version: Version }) {
  if (version.review_state === 'not_reviewed') return <NotReviewedTag />
  if (version.review_state === 'accepted') {
    return (
      <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium', BADGE_TONE.ok)}>
        <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
        Reviewed
      </span>
    )
  }
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium', BADGE_TONE.bad)}>
      <XCircle className="h-3 w-3" aria-hidden="true" />
      Rejected
    </span>
  )
}
