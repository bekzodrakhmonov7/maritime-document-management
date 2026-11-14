import { useState } from 'react'
import { Plus } from 'lucide-react'
import { useDocumentTypeAction, useDocumentTypes } from '../hooks/useReferenceData'
import type { DocumentType, DocumentTypeWrite } from '../types'
import { ActionButton } from '../components/ActionButton'
import { ErrorNote } from '../components/ErrorNote'
import { FIELD_CLASS, FormDialog, LABEL_CLASS } from '../components/FormDialog'
import { RetirableActions, RetireDialog, type RetireKind } from '../components/RetireDialog'
import { StateBadge } from '../components/StateBadge'

type Dialog =
  | { kind: 'create' }
  | { kind: 'edit'; docType: DocumentType }
  | { kind: RetireKind; docType: DocumentType }

/** Document Types and their rules (FR-07, administrators only). */
export function DocumentTypesPage() {
  const { data: types, isLoading, error } = useDocumentTypes()
  const [dialog, setDialog] = useState<Dialog | null>(null)
  const nameOf = new Map(types?.map((t) => [t.id, t.name]))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold text-navy-50">Document Types</h2>
          <p className="mt-1 text-sm text-navy-400">
            The kinds of document the company tracks and their rules. A type that depends on a
            certificate is an Endorsement. A type in use is retired, not deleted.
          </p>
        </div>
        <ActionButton tone="primary" onClick={() => setDialog({ kind: 'create' })}>
          <Plus className="h-4 w-4" />
          Add Document Type
        </ActionButton>
      </div>

      {error && <ErrorNote message={error.message} />}

      <div className="overflow-x-auto rounded-xl border border-navy-800 bg-navy-900">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-navy-800 text-xs uppercase tracking-wider text-navy-400">
            <tr>
              <th scope="col" className="px-4 py-3">Name</th>
              <th scope="col" className="px-4 py-3">Expires</th>
              <th scope="col" className="px-4 py-3">Max validity</th>
              <th scope="col" className="px-4 py-3">Renewable at sea</th>
              <th scope="col" className="px-4 py-3">Endorsement of</th>
              <th scope="col" className="px-4 py-3">Status</th>
              <th scope="col" className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-navy-800">
            {isLoading && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-navy-400">
                  Loading…
                </td>
              </tr>
            )}
            {types?.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-navy-400">
                  No Document Types yet.
                </td>
              </tr>
            )}
            {types?.map((t) => (
              <tr key={t.id}>
                <td className="px-4 py-3 text-navy-50">{t.name}</td>
                <td className="px-4 py-3 text-navy-200">{t.expires ? 'Yes' : 'No'}</td>
                <td className="px-4 py-3 text-navy-200">
                  {t.max_validity_months ? `${t.max_validity_months} months` : '—'}
                </td>
                <td className="px-4 py-3 text-navy-200">{t.renewable_at_sea ? 'Yes' : 'No'}</td>
                <td className="px-4 py-3 text-navy-200">
                  {t.depends_on_id ? nameOf.get(t.depends_on_id) : '—'}
                </td>
                <td className="px-4 py-3">
                  <StateBadge on={!t.retired} label={t.retired ? 'Retired' : 'In use'} />
                </td>
                <td className="px-4 py-3">
                  <RetirableActions
                    retired={t.retired}
                    onEdit={() => setDialog({ kind: 'edit', docType: t })}
                    onRetire={(kind) => setDialog({ kind, docType: t })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(dialog?.kind === 'create' || dialog?.kind === 'edit') && (
        <DocumentTypeForm
          docType={dialog.kind === 'edit' ? dialog.docType : null}
          all={types ?? []}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog && dialog.kind !== 'create' && dialog.kind !== 'edit' && (
        <RetireDialog
          collection="document-types"
          noun="Document Type"
          row={dialog.docType}
          kind={dialog.kind}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  )
}

function DocumentTypeForm({
  docType,
  all,
  onClose,
}: {
  docType: DocumentType | null
  all: DocumentType[]
  onClose: () => void
}) {
  const [name, setName] = useState(docType?.name ?? '')
  const [expires, setExpires] = useState(docType?.expires ?? true)
  const [maxMonths, setMaxMonths] = useState(docType?.max_validity_months?.toString() ?? '')
  const [renewableAtSea, setRenewableAtSea] = useState(docType?.renewable_at_sea ?? false)
  const [dependsOn, setDependsOn] = useState(docType?.depends_on_id?.toString() ?? '')
  const action = useDocumentTypeAction()

  // A type with Endorsements of its own is a certificate: it keeps expiring
  // and can't become an Endorsement itself (one level only).
  const endorsements = docType ? all.filter((t) => t.depends_on_id === docType.id) : []
  const isCertificate = endorsements.length > 0
  // Possible certificates: expiring, not Endorsements, not this type. Retired
  // ones are offered only if already chosen.
  const certificates = all.filter(
    (t) =>
      t.id !== docType?.id &&
      t.expires &&
      t.depends_on_id === null &&
      (!t.retired || t.id === docType?.depends_on_id),
  )

  const months = maxMonths.trim() === '' ? null : Number(maxMonths)
  const body: DocumentTypeWrite = {
    name: name.trim(),
    expires,
    max_validity_months: expires ? months : null,
    renewable_at_sea: renewableAtSea,
    depends_on_id: dependsOn ? Number(dependsOn) : null,
  }
  const canSubmit =
    !!body.name && (body.max_validity_months === null || Number.isInteger(body.max_validity_months))

  return (
    <FormDialog
      title={docType ? 'Edit Document Type' : 'Add Document Type'}
      subtitle={docType?.name}
      submitLabel={docType ? 'Save' : 'Add Document Type'}
      onSubmit={() =>
        action.mutate(docType ? { kind: 'edit', id: docType.id, body } : { kind: 'create', body }, {
          onSuccess: onClose,
        })
      }
      onClose={onClose}
      pending={action.isPending}
      canSubmit={canSubmit}
      error={action.error}
    >
      <div>
        <label htmlFor="doctype-name" className={LABEL_CLASS}>
          Name
        </label>
        <input
          id="doctype-name"
          required
          maxLength={200}
          value={name}
          onChange={(e) => setName(e.target.value)}
          className={FIELD_CLASS}
          placeholder="e.g. Passport"
        />
      </div>

      <label className="flex items-start gap-2 text-sm text-navy-100">
        <input
          type="checkbox"
          checked={expires}
          disabled={isCertificate && expires}
          onChange={(e) => setExpires(e.target.checked)}
          className="mt-0.5"
        />
        <span>
          Expires
          <span className="block text-xs text-navy-400">
            {isCertificate
              ? 'It has Endorsements, so it must keep expiring.'
              : 'On: every document needs an expiry date. Off: it must have none.'}
          </span>
        </span>
      </label>

      {expires && (
        <div>
          <label htmlFor="doctype-max" className={LABEL_CLASS}>
            Maximum validity in months (optional)
          </label>
          <input
            id="doctype-max"
            type="number"
            min={1}
            max={1200}
            step={1}
            value={maxMonths}
            onChange={(e) => setMaxMonths(e.target.value)}
            className={FIELD_CLASS}
            placeholder="No maximum"
          />
          <p className="mt-1 text-xs text-navy-400">
            An upload whose expiry date is later than its issue date plus this is refused.
          </p>
        </div>
      )}

      <label className="flex items-start gap-2 text-sm text-navy-100">
        <input
          type="checkbox"
          checked={renewableAtSea}
          onChange={(e) => setRenewableAtSea(e.target.checked)}
          className="mt-0.5"
        />
        <span>
          Renewable at sea
          <span className="block text-xs text-navy-400">
            Advice only: it can be renewed on board rather than before joining.
          </span>
        </span>
      </label>

      <div>
        <label htmlFor="doctype-depends" className={LABEL_CLASS}>
          Depends on (makes it an Endorsement)
        </label>
        <select
          id="doctype-depends"
          value={dependsOn}
          disabled={isCertificate}
          onChange={(e) => setDependsOn(e.target.value)}
          className={FIELD_CLASS}
        >
          <option value="">Nothing: not an Endorsement</option>
          {certificates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
              {t.retired ? ' (retired)' : ''}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-navy-400">
          {isCertificate
            ? `Endorsements depend on this type (${endorsements.map((t) => t.name).join(', ')}), so it can't be one itself.`
            : 'Only an expiring type that is not itself an Endorsement can be picked.'}
        </p>
      </div>
    </FormDialog>
  )
}
