export const DOC_TYPE_NAMES: Record<number, string> = {
  1: 'COC',
  2: 'STCW',
  3: 'Medical',
  4: 'Passport',
  5: 'Endorsement',
  6: 'GMDSS',
}

export function getDocTypeName(docTypeId: number): string {
  return DOC_TYPE_NAMES[docTypeId] ?? `Type ${docTypeId}`
}

export const DOC_TYPE_OPTIONS = Object.entries(DOC_TYPE_NAMES).map(
  ([id, name]) => ({
    doc_type_id: Number(id),
    type_name: name,
  }),
)
