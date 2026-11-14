import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Download, Pencil, Upload } from 'lucide-react'
import { useDocument, useOpenVersionFile } from '../hooks/useDocuments'
import { ActionButton } from '../components/ActionButton'
import { ErrorNote } from '../components/ErrorNote'
import { ExpiryStatusBadge } from '../components/ExpiryStatusBadge'
import { VersionDialog, type VersionDialogState } from '../components/DocumentDialogs'

/** One document: its Expiry Status and full history of Versions, newest first.
 * Every file is fetched through a signed, recorded link. Reviews and Verifications
 * join the history in S8. */
export function DocumentPage() {
  const { id } = useParams()
  const { data: document, isLoading, error } = useDocument(Number(id))
  const openFile = useOpenVersionFile()
  const [dialog, setDialog] = useState<VersionDialogState | null>(null)
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
                      <p className="font-medium text-navy-50">
                        Version {v.number}
                        {v.is_current && (
                          <span className="ml-2 rounded-full bg-navy-700 px-2 py-0.5 text-xs text-navy-100">
                            Current
                          </span>
                        )}
                      </p>
                      <p className="text-xs text-navy-400">
                        Uploaded by {v.uploaded_by_name} on {new Date(v.uploaded_at).toLocaleString()}
                      </p>
                    </div>
                    <ActionButton onClick={() => openFile.mutate(v.id)} disabled={openFile.isPending}>
                      <Download className="h-3.5 w-3.5" />
                      {v.original_filename}
                    </ActionButton>
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
                      <dd className="text-navy-100">{v.expiry_date ?? 'No expiry date'}</dd>
                    </div>
                  </dl>
                  {v.file_from_version_number && (
                    <p className="mt-2 text-xs text-navy-400">
                      Details corrected; same file as version {v.file_from_version_number}.
                    </p>
                  )}
                </li>
              ))}
            </ol>
          </section>
        </>
      )}

      {dialog && <VersionDialog state={dialog} onClose={() => setDialog(null)} />}
    </div>
  )
}
