import { useState, type ChangeEvent } from 'react'
import { Link } from 'react-router-dom'
import { FileText } from 'lucide-react'
import { useAddVersion } from '../hooks/useDocuments'
import { useDocumentTypes } from '../hooks/useReferenceData'
import { useSettings } from '../hooks/useSettings'
import type { DocumentDetail, DocumentSummary, DocumentType, Seafarer, VersionDetails } from '../types'
import { DocumentDropzone } from './DocumentDropzone'
import { ExpiryStatusBadge } from './ExpiryStatusBadge'
import { EndorsementCapNote } from './EndorsementCapNote'
import { effectiveExpiryOf, hasCapNote } from '../lib/effectiveExpiry'
import { NotReviewedTag, VerifiedShield } from './ReviewTags'
import { FIELD_CLASS, FormDialog, LABEL_CLASS } from './FormDialog'
import { FILE_SIZE_CEILING_MB } from '../lib/fileSize'

/** Which Version dialog is open: a first upload (pick the type), a new file
 * for an existing document (renewal), or corrected details only. */
export type VersionDialogState =
  | { kind: 'new'; seafarer: Seafarer; taken: number[] }
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
    state.kind === 'new' ? null : state.document.document_type_id,
  )
  const [file, setFile] = useState<File | null>(null)

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

  const body: VersionDetails = { ...details, expiry_date: type?.expires ? details.expiry_date || null : null }
  const canSubmit =
    !!type &&
    !!details.document_number.trim() &&
    !!details.issuing_authority.trim() &&
    !!details.issue_date &&
    (!type.expires || !!details.expiry_date) &&
    (!needsFile || !!file)

  const submit = () => {
    if (!type || typeId === null) return
    if (state.kind === 'details') {
      action.mutate({ kind: 'details', documentId: state.document.id, details: body }, { onSuccess: onClose })
    } else if (file) {
      const seafarerId = state.kind === 'new' ? state.seafarer.id : state.document.seafarer_id
      action.mutate(
        { kind: 'upload', seafarerId, documentTypeId: typeId, details: body, file },
        { onSuccess: onClose },
      )
    }
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
        <div>
          <label htmlFor="version-type" className={LABEL_CLASS}>
            Document type
          </label>
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
        </div>
      )}
      {state.kind === 'details' && (
        <p className="text-sm text-navy-300">
          The new version keeps the current file and waits for review.
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="version-number" className={LABEL_CLASS}>
            Document number
          </label>
          <input id="version-number" className={FIELD_CLASS} value={details.document_number} onChange={set('document_number')} />
        </div>
        <div>
          <label htmlFor="version-authority" className={LABEL_CLASS}>
            Issuing authority
          </label>
          <input
            id="version-authority"
            className={FIELD_CLASS}
            value={details.issuing_authority}
            onChange={set('issuing_authority')}
          />
        </div>
        <div>
          <label htmlFor="version-issued" className={LABEL_CLASS}>
            Issue date
          </label>
          <input id="version-issued" type="date" className={FIELD_CLASS} value={details.issue_date} onChange={set('issue_date')} />
        </div>
        {type?.expires !== false && (
          <div>
            <label htmlFor="version-expiry" className={LABEL_CLASS}>
              Expiry date
            </label>
            <input
              id="version-expiry"
              type="date"
              className={FIELD_CLASS}
              value={details.expiry_date ?? ''}
              onChange={set('expiry_date')}
            />
          </div>
        )}
      </div>
      {type?.expires === false && <p className="text-xs text-navy-400">This document type doesn't expire.</p>}
      {type?.max_validity_months && (
        <p className="text-xs text-navy-400">
          Valid for at most {type.max_validity_months} months from the issue date.
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
 * Not-reviewed tag and Verified shield. */
export function DocumentsTable({
  documents,
  onRenew,
}: {
  documents: DocumentSummary[] | undefined
  onRenew?: (document: DocumentSummary) => void
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-navy-800 bg-navy-900">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-navy-800 text-xs uppercase tracking-wider text-navy-400">
          <tr>
            <th scope="col" className="px-4 py-3">Document</th>
            <th scope="col" className="px-4 py-3">Number</th>
            <th scope="col" className="px-4 py-3">Expires</th>
            <th scope="col" className="px-4 py-3">Status</th>
            <th scope="col" className="px-4 py-3">Versions</th>
            {onRenew && <th scope="col" className="px-4 py-3 text-right">Actions</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-navy-800">
          {documents?.length === 0 && (
            <tr>
              <td colSpan={onRenew ? 6 : 5} className="px-4 py-6 text-center text-navy-400">
                No documents yet.
              </td>
            </tr>
          )}
          {documents?.map((d) => (
            <tr key={d.id}>
              <td className="px-4 py-3">
                <Link to={`/documents/${d.id}`} className="inline-flex items-center gap-2 text-navy-50 hover:underline">
                  <FileText className="h-4 w-4 text-navy-400" aria-hidden="true" />
                  {d.document_type_name}
                </Link>
                {d.document_type_retired && <span className="ml-2 text-xs text-navy-400">(retired type)</span>}
              </td>
              <td className="px-4 py-3 text-navy-200">{d.current_version?.document_number ?? '—'}</td>
              <td className="px-4 py-3 text-navy-200">
                <ExpiryCell document={d} />
              </td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <ExpiryStatusBadge status={d.expiry_status} />
                  {d.current_version?.review_state === 'not_reviewed' && <NotReviewedTag />}
                  {d.verified && <VerifiedShield />}
                </div>
              </td>
              <td className="px-4 py-3 text-navy-300">{d.version_count}</td>
              {onRenew && (
                <td className="px-4 py-3 text-right">
                  {!d.document_type_retired && (
                    <button
                      type="button"
                      onClick={() => onRenew(d)}
                      className="rounded-lg bg-navy-700 px-3 py-1.5 text-xs font-medium text-navy-50 hover:bg-navy-600"
                    >
                      New version
                    </button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** The documents table's expiry: the own date, or the Endorsement cap note. */
function ExpiryCell({ document }: { document: DocumentSummary }) {
  const fields = effectiveExpiryOf(document, document.current_version?.expiry_date ?? null)
  if (document.current_version && hasCapNote(fields)) return <EndorsementCapNote {...fields} />
  return <>{document.current_version?.expiry_date ?? '—'}</>
}
