import { useState, type ChangeEvent } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, FileText } from 'lucide-react'
import { useAddVersion } from '../hooks/useDocuments'
import { useDocumentTypes } from '../hooks/useReferenceData'
import { useSettings } from '../hooks/useSettings'
import type { DocumentDetail, DocumentSummary, DocumentType, Seafarer, VersionDetails } from '../types'
import { DocumentDropzone } from './DocumentDropzone'
import { ExpiryStatusBadge } from './ExpiryStatusBadge'
import { EndorsementCapNote } from './EndorsementCapNote'
import { effectiveExpiryOf, hasCapNote } from '../lib/effectiveExpiry'
import { NotReviewedTag } from './ReviewTags'
import { VerificationBadge } from './verificationBadge.ts'
import { Field, FIELD_CLASS, FormDialog } from './FormDialog'
import { FILE_SIZE_CEILING_MB } from '../lib/fileSize'
import { Table } from './Table'

/** Which Version dialog is open: a first upload (pick the type), a new file
 * for an existing document (renewal), or corrected details only. */
export type VersionDialogState =
  | { kind: 'new'; seafarer: Seafarer; taken: number[]; /** Opened from a Missing entry: preselected, still editable. */ documentTypeId?: number }
  | { kind: 'renew'; document: DocumentSummary }
  | { kind: 'details'; document: DocumentDetail }

const EMPTY: VersionDetails = {
  document_number: '',
  issuing_authority: '',
  issue_date: '',
  expiry_date: '',
}

function initialDetails(state: VersionDialogState): VersionDetails {
  if (state.kind !== 'details') return EMPTY
  const current = state.document.versions.find((v) => v.is_current)
  if (!current) return EMPTY
  return {
    document_number: current.document_number,
    issuing_authority: current.issuing_authority,
    issue_date: current.issue_date,
    expiry_date: current.expiry_date ?? '',
    expiry_not_stated: current.expiry_date === null,
  }
}

const TITLES: Record<VersionDialogState['kind'], string> = {
  new: 'Upload document',
  renew: 'Upload new version',
  details: 'Correct details',
}

/** The upload form. On a refusal it shows the API's sentence and keeps
 * everything already entered, file included, so the officer can fix and retry. */
export function VersionDialog({ state, onClose }: { state: VersionDialogState; onClose: () => void }) {
  const { data: types } = useDocumentTypes()
  const { data: settings } = useSettings()
  const action = useAddVersion()
  const [details, setDetails] = useState<VersionDetails>(() => initialDetails(state))
  const [typeId, setTypeId] = useState<number | null>(
    state.kind === 'new' ? (state.documentTypeId ?? null) : state.document.document_type_id,
  )
  const [file, setFile] = useState<File | null>(null)
  // Warnings from the save (SR-12): the Version is saved; shown before closing.
  const [warnings, setWarnings] = useState<string[]>([])

  const type: Pick<DocumentType, 'name' | 'expires' | 'max_validity_months'> | undefined =
    state.kind === 'new'
      ? types?.find((t) => t.id === typeId)
      : {
          name: state.document.document_type_name,
          expires: state.document.expires,
          max_validity_months: state.document.max_validity_months,
        }
  const pickable =
    state.kind === 'new' ? (types ?? []).filter((t) => !t.retired && !state.taken.includes(t.id)) : []
  const needsFile = state.kind !== 'details'
  const set = (field: keyof VersionDetails) => (e: ChangeEvent<HTMLInputElement>) =>
    setDetails((d) => ({ ...d, [field]: e.target.value }))

  const notStated = !!type?.expires && !!details.expiry_not_stated
  const body: VersionDetails = {
    ...details,
    expiry_date: type?.expires && !notStated ? details.expiry_date || null : null,
    expiry_not_stated: notStated,
  }
  const canSubmit =
    !!type &&
    !!details.document_number.trim() &&
    !!details.issuing_authority.trim() &&
    !!details.issue_date &&
    (!type.expires || notStated || !!details.expiry_date) &&
    (!needsFile || !!file)

  const saved = (document: DocumentDetail) => {
    if (document.warnings?.length) setWarnings(document.warnings)
    else onClose()
  }

  const submit = () => {
    if (!type || typeId === null) return
    if (state.kind === 'details') {
      action.mutate({ kind: 'details', documentId: state.document.id, details: body }, { onSuccess: saved })
    } else if (file) {
      const seafarerId = state.kind === 'new' ? state.seafarer.id : state.document.seafarer_id
      action.mutate(
        { kind: 'upload', seafarerId, documentTypeId: typeId, details: body, file },
        { onSuccess: saved },
      )
    }
  }

  if (warnings.length > 0) {
    return (
      <FormDialog
        title="Saved with a warning"
        subtitle={type?.name}
        submitLabel="OK"
        onSubmit={onClose}
        onClose={onClose}
        pending={false}
        canSubmit
        error={null}
      >
        {warnings.map((w) => (
          <p key={w} role="status" className="flex gap-2 text-sm text-warning">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            {w}
          </p>
        ))}
      </FormDialog>
    )
  }

  const hint = settings
    ? `PDF, JPEG or PNG, up to ${settings.max_file_size_mb} MB; PDFs up to ${settings.max_pdf_pages} pages.`
    : 'PDF, JPEG or PNG.'

  return (
    <FormDialog
      title={TITLES[state.kind]}
      subtitle={state.kind === 'new' ? undefined : type?.name}
      submitLabel={needsFile ? 'Upload' : 'Save as new version'}
      onSubmit={submit}
      onClose={onClose}
      pending={action.isPending}
      canSubmit={canSubmit}
      error={action.error}
    >
      {state.kind === 'new' && (
        <Field id="version-type" label="Document type">
          <select
            id="version-type"
            className={FIELD_CLASS}
            value={typeId ?? ''}
            onChange={(e) => setTypeId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">Choose…</option>
            {pickable.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </Field>
      )}
      {state.kind === 'details' && (
        <p className="text-sm text-ink-muted">
          The new version keeps the current file and waits for review.
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="version-number" label="Document number">
          <input id="version-number" className={FIELD_CLASS} value={details.document_number} onChange={set('document_number')} />
        </Field>
        <Field id="version-authority" label="Issuing authority">
          <input
            id="version-authority"
            className={FIELD_CLASS}
            value={details.issuing_authority}
            onChange={set('issuing_authority')}
          />
        </Field>
        <Field id="version-issued" label="Issue date">
          <input id="version-issued" type="date" className={FIELD_CLASS} value={details.issue_date} onChange={set('issue_date')} />
        </Field>
        {type?.expires !== false && (
          <Field id="version-expiry" label="Expiry date">
            <input
              id="version-expiry"
              type="date"
              className={FIELD_CLASS}
              value={details.expiry_date ?? ''}
              onChange={set('expiry_date')}
              disabled={notStated}
            />
          </Field>
        )}
      </div>
      {type?.expires && (
        <label className="flex items-center gap-2 text-sm text-ink-muted">
          <input
            type="checkbox"
            checked={notStated}
            onChange={(e) => setDetails((d) => ({ ...d, expiry_not_stated: e.target.checked }))}
            className="h-4 w-4 rounded border-line-strong bg-canvas"
          />
          Expiry not stated on the document
        </label>
      )}
      {type?.expires === false && <p className="text-xs text-ink-faint">This document type doesn't expire.</p>}
      {type?.max_validity_months && (
        <p className="text-xs text-ink-faint">
          Valid for at most {type.max_validity_months} months from the issue date; a longer validity is saved with a warning.
        </p>
      )}
      {needsFile && (
        <DocumentDropzone
          file={file}
          onFileAccepted={setFile}
          onClear={() => setFile(null)}
          maxSizeMb={settings?.max_file_size_mb ?? FILE_SIZE_CEILING_MB}
          hint={hint}
        />
      )}
    </FormDialog>
  )
}

/** A seafarer's documents with their Current Version, Expiry Status,
 * Not-reviewed tag and Verification badge. */
export function DocumentsTable({
  documents,
  onRenew,
}: {
  documents: DocumentSummary[] | undefined
  onRenew?: (document: DocumentSummary) => void
}) {
  return (
    <Table
      head={[
        'Document',
        'Number',
        'Expires',
        'Status',
        'Versions',
        ...(onRenew ? [{ label: 'Actions', className: 'text-right' }] : []),
      ]}
      empty={documents?.length === 0 ? 'No documents yet.' : null}
    >
      {documents?.map((d) => (
        <tr key={d.id}>
          <td className="px-4 py-3">
            <Link to={`/documents/${d.id}`} className="inline-flex items-center gap-2 text-ink hover:underline">
              <FileText className="h-4 w-4 text-ink-faint" aria-hidden="true" />
              {d.document_type_name}
            </Link>
            {d.document_type_retired && <span className="ml-2 text-xs text-ink-faint">(retired type)</span>}
          </td>
          <td className="px-4 py-3 text-ink-muted">{d.current_version?.document_number ?? '—'}</td>
          <td className="px-4 py-3 text-ink-muted">
            <ExpiryCell document={d} />
          </td>
          <td className="px-4 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <ExpiryStatusBadge status={d.expiry_status} />
              {d.current_version?.review_state === 'not_reviewed' && <NotReviewedTag />}
              <VerificationBadge verified={d.verified} />
            </div>
          </td>
          <td className="px-4 py-3 text-ink-muted">{d.version_count}</td>
          {onRenew && (
            <td className="px-4 py-3 text-right">
              {!d.document_type_retired && (
                <button
                  type="button"
                  onClick={() => onRenew(d)}
                  className="h-8 shrink-0 whitespace-nowrap rounded-md border border-line-strong bg-canvas px-3 text-sm font-medium text-ink hover:bg-surface-active"
                >
                  New version
                </button>
              )}
            </td>
          )}
        </tr>
      ))}
    </Table>
  )
}

/** The documents table's expiry: the own date, or the Endorsement cap note. */
function ExpiryCell({ document }: { document: DocumentSummary }) {
  const fields = effectiveExpiryOf(document, document.current_version?.expiry_date ?? null)
  if (document.current_version && hasCapNote(fields)) return <EndorsementCapNote {...fields} />
  return <>{document.current_version?.expiry_date ?? '—'}</>
}
