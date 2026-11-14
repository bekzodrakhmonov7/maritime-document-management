import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, FileWarning, Plus, Upload } from 'lucide-react'
import { useSeafarerAssignments } from '../hooks/useAssignments'
import { useSeafarerDocuments } from '../hooks/useDocuments'
import { fullName, useSeafarer } from '../hooks/useSeafarers'
import { flagLabel } from '../lib/flags'
import { ActionButton } from '../components/ActionButton'
import {
  AssignmentDialog,
  AssignmentsTable,
  type AssignmentDialogState,
} from '../components/AssignmentDialogs'
import { DocumentsTable, VersionDialog, type VersionDialogState } from '../components/DocumentDialogs'
import { ErrorNote } from '../components/ErrorNote'
import {
  SeafarerActions,
  SeafarerDialog,
  SeafarerStatusBadge,
  type SeafarerDialogState,
} from '../components/SeafarerDialogs'
import type { SeafarerRecord } from '../types'

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-navy-400">{label}</dt>
      <dd className="mt-1 text-navy-50">{children}</dd>
    </div>
  )
}

/** The required documents with no Current Version, for the Assignment under
 * way (or the held Position when ashore). Expiry is shown in the table below. */
function MissingDocumentsStrip({ seafarer }: { seafarer: SeafarerRecord }) {
  const missing = seafarer.missing_documents
  const basis = seafarer.current_vessel_name
    ? `as on board ${seafarer.current_vessel_name}`
    : `for ${seafarer.position_name}, ashore`
  if (missing.length === 0) {
    return <p className="text-sm text-navy-400">No required documents missing ({basis}).</p>
  }
  return (
    <section
      aria-label="Missing documents"
      className="flex flex-wrap items-center gap-2 rounded-lg border border-status-expired/40 bg-status-expired-bg/10 p-3 text-sm"
    >
      <FileWarning className="h-4 w-4 shrink-0 text-status-expired" aria-hidden="true" />
      <span className="font-medium text-status-expired">
        {missing.length} missing ({basis}):
      </span>
      {missing.map((m) =>
        m.document_id ? (
          <Link
            key={m.document_type_id}
            to={`/documents/${m.document_id}`}
            className="rounded-full bg-navy-800 px-2.5 py-0.5 text-xs text-navy-100 hover:underline"
            title="Every Version was rejected"
          >
            {m.name}
          </Link>
        ) : (
          <span key={m.document_type_id} className="rounded-full bg-navy-800 px-2.5 py-0.5 text-xs text-navy-100">
            {m.name}
          </span>
        ),
      )}
    </section>
  )
}

/** One seafarer's record: personal details, held Position, Current Vessel,
 * missing documents, Assignments and documents. */
export function SeafarerPage() {
  const { id } = useParams()
  const { data: seafarer, isLoading, error } = useSeafarer(Number(id))
  const assignments = useSeafarerAssignments(Number(id))
  const documents = useSeafarerDocuments(Number(id))
  const [versionDialog, setVersionDialog] = useState<VersionDialogState | null>(null)
  const [dialog, setDialog] = useState<SeafarerDialogState | null>(null)
  const [assignmentDialog, setAssignmentDialog] = useState<AssignmentDialogState | null>(null)

  return (
    <div className="max-w-3xl space-y-6">
      <Link
        to="/seafarers"
        className="inline-flex items-center gap-1 text-sm text-navy-300 hover:text-navy-100"
      >
        <ArrowLeft className="h-4 w-4" />
        All seafarers
      </Link>

      {isLoading && <p className="text-sm text-navy-400">Loading…</p>}
      {error && <ErrorNote message={error.message} />}

      {seafarer && (
        <>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <h2 className="text-2xl font-semibold text-navy-50">{fullName(seafarer)}</h2>
              <SeafarerStatusBadge seafarer={seafarer} />
            </div>
            <SeafarerActions seafarer={seafarer} onOpen={setDialog} />
          </div>

          {seafarer.inactive_since && (
            <p className="rounded-lg border border-navy-700 bg-navy-900 p-3 text-sm text-navy-300">
              Inactive since {new Date(seafarer.inactive_since).toLocaleDateString()}:{' '}
              {seafarer.inactive_reason}
            </p>
          )}

          <dl className="grid gap-4 rounded-xl border border-navy-800 bg-navy-900 p-6 sm:grid-cols-2">
            <Detail label="Position">
              {seafarer.position_name}
              {seafarer.position_retired && (
                <span className="ml-2 text-xs text-navy-400">(retired Position)</span>
              )}
            </Detail>
            <Detail label="Nationality">
              {seafarer.nationality ? flagLabel(seafarer.nationality) : '—'}
            </Detail>
            <Detail label="Date of birth">{seafarer.date_of_birth ?? '—'}</Detail>
            <Detail label="Current vessel">
              {seafarer.current_vessel_id ? (
                <Link to={`/vessels/${seafarer.current_vessel_id}`} className="hover:underline">
                  {seafarer.current_vessel_name}
                </Link>
              ) : (
                'Ashore'
              )}
            </Detail>
          </dl>

          {!seafarer.inactive_since && <MissingDocumentsStrip seafarer={seafarer} />}

          <section className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-lg font-semibold text-navy-50">Assignments</h3>
              {!seafarer.inactive_since && (
                <ActionButton
                  tone="primary"
                  onClick={() => setAssignmentDialog({ kind: 'create', seafarer })}
                >
                  <Plus className="h-4 w-4" />
                  Plan Assignment
                </ActionButton>
              )}
            </div>
            {assignments.error && <ErrorNote message={assignments.error.message} />}
            <AssignmentsTable
              assignments={assignments.data}
              show="vessel"
              empty="No Assignments yet."
              onEdit={(assignment) => setAssignmentDialog({ kind: 'edit', seafarer, assignment })}
              onCancel={(assignment) => setAssignmentDialog({ kind: 'cancel', assignment })}
            />
          </section>

          <section className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-lg font-semibold text-navy-50">Documents</h3>
              {!seafarer.inactive_since && (
                <ActionButton
                  tone="primary"
                  onClick={() =>
                    setVersionDialog({
                      kind: 'new',
                      seafarer,
                      taken: (documents.data ?? []).map((d) => d.document_type_id),
                    })
                  }
                >
                  <Upload className="h-4 w-4" />
                  Upload document
                </ActionButton>
              )}
            </div>
            {documents.error && <ErrorNote message={documents.error.message} />}
            <DocumentsTable
              documents={documents.data}
              onRenew={
                seafarer.inactive_since
                  ? undefined
                  : (document) => setVersionDialog({ kind: 'renew', document })
              }
            />
          </section>
        </>
      )}

      {dialog && <SeafarerDialog state={dialog} onClose={() => setDialog(null)} />}
      {versionDialog && (
        <VersionDialog state={versionDialog} onClose={() => setVersionDialog(null)} />
      )}
      {assignmentDialog && (
        <AssignmentDialog state={assignmentDialog} onClose={() => setAssignmentDialog(null)} />
      )}
    </div>
  )
}
