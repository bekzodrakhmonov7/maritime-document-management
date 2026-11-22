import { useState } from 'react'
import { useRecordVerification, useReviewVersion } from '../hooks/useDocuments'
import { useSettings } from '../hooks/useSettings'
import type { ReviewDecision, VerificationDetails, VerificationResult, Version } from '../types'
import { DocumentDropzone } from './DocumentDropzone'
import { Field, FIELD_CLASS, FormDialog, LABEL_CLASS } from './FormDialog'
import { FILE_SIZE_CEILING_MB } from '../lib/fileSize'

/** Accept or reject one Version, with a required comment. A later Review
 * overturns an earlier one; rejecting the Current Version hands "current"
 * back to the previous non-rejected Version. */
export function ReviewDialog({ version, onClose }: { version: Version; onClose: () => void }) {
  const review = useReviewVersion()
  const [decision, setDecision] = useState<ReviewDecision>(
    version.review_state === 'accepted' ? 'reject' : 'accept',
  )
  const [comment, setComment] = useState('')

  return (
    <FormDialog
      title={`Review version ${version.number}`}
      subtitle={`Uploaded by ${version.uploaded_by_name}`}
      submitLabel={decision === 'accept' ? 'Accept' : 'Reject'}
      onSubmit={() =>
        review.mutate({ versionId: version.id, decision, comment: comment.trim() }, { onSuccess: onClose })
      }
      onClose={onClose}
      pending={review.isPending}
      canSubmit={!!comment.trim()}
      error={review.error}
    >
      <fieldset className="flex gap-4">
        <legend className={LABEL_CLASS}>Decision</legend>
        {(['accept', 'reject'] as const).map((d) => (
          <label key={d} className="flex items-center gap-2 text-sm text-ink">
            <input type="radio" name="decision" checked={decision === d} onChange={() => setDecision(d)} />
            {d === 'accept' ? 'Accept' : 'Reject'}
          </label>
        ))}
      </fieldset>
      {decision === 'reject' && version.is_current && (
        <p className="text-sm text-ink-muted">
          The previous version that isn't rejected becomes current again; with none, the document counts as missing.
        </p>
      )}
      <Field id="review-comment" label="Comment">
        <textarea
          id="review-comment"
          rows={3}
          className={FIELD_CLASS}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
      </Field>
    </FormDialog>
  )
}

function today(): string {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
}

/** Record a check with the issuing authority, with an optional proof file
 * (same formats and limits as a document file). */
export function VerificationDialog({ version, onClose }: { version: Version; onClose: () => void }) {
  const record = useRecordVerification()
  const { data: settings } = useSettings()
  const [details, setDetails] = useState<VerificationDetails>({
    checked_on: today(),
    source: '',
    result: 'confirmed',
    reference: '',
  })
  const [proof, setProof] = useState<File | null>(null)
  const set = (field: keyof VerificationDetails) => (value: string) =>
    setDetails((d) => ({ ...d, [field]: value }))

  const canSubmit = !!details.checked_on && !!details.source.trim() && !!details.reference.trim()
  const hint = settings
    ? `Optional proof: PDF, JPEG or PNG, up to ${settings.max_file_size_mb} MB.`
    : 'Optional proof: PDF, JPEG or PNG.'

  return (
    <FormDialog
      title={`Record verification of version ${version.number}`}
      subtitle={`${version.document_number}, issued by ${version.issuing_authority}`}
      submitLabel="Record"
      onSubmit={() =>
        record.mutate(
          {
            versionId: version.id,
            details: { ...details, source: details.source.trim(), reference: details.reference.trim() },
            proof,
          },
          { onSuccess: onClose },
        )
      }
      onClose={onClose}
      pending={record.isPending}
      canSubmit={canSubmit}
      error={record.error}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="verification-date" label="Date">
          <input
            id="verification-date"
            type="date"
            max={today()}
            className={FIELD_CLASS}
            value={details.checked_on}
            onChange={(e) => set('checked_on')(e.target.value)}
          />
        </Field>
        <Field id="verification-result" label="Result">
          <select
            id="verification-result"
            className={FIELD_CLASS}
            value={details.result}
            onChange={(e) => set('result')(e.target.value as VerificationResult)}
          >
            <option value="confirmed">Confirmed</option>
            <option value="not_confirmed">Not confirmed</option>
          </select>
        </Field>
        <Field id="verification-source" label="Source">
          <input
            id="verification-source"
            className={FIELD_CLASS}
            placeholder="e.g. e-mail to the registry"
            value={details.source}
            onChange={(e) => set('source')(e.target.value)}
          />
        </Field>
        <Field id="verification-reference" label="Reference">
          <input
            id="verification-reference"
            className={FIELD_CLASS}
            value={details.reference}
            onChange={(e) => set('reference')(e.target.value)}
          />
        </Field>
      </div>
      <DocumentDropzone
        file={proof}
        onFileAccepted={setProof}
        onClear={() => setProof(null)}
        maxSizeMb={settings?.max_file_size_mb ?? FILE_SIZE_CEILING_MB}
        hint={hint}
      />
    </FormDialog>
  )
}
