/** Opening the upload form from a Missing entry (dashboard Missing queue,
 * readiness gap) carries the missing Document Type in the seafarer record's
 * URL, so the form opens with that type already chosen. */
export const UPLOAD_PARAM = 'upload'

export function missingUploadPath(seafarerId: number, documentTypeId: number): string {
  return `/seafarers/${seafarerId}?${UPLOAD_PARAM}=${documentTypeId}`
}

/** The Document Type id asked for in a seafarer record's query string, if any. */
export function preselectedTypeId(search: string): number | null {
  const raw = new URLSearchParams(search).get(UPLOAD_PARAM)
  if (raw === null || !/^\d+$/.test(raw)) return null
  const id = Number(raw)
  return id > 0 ? id : null
}

/** FR-11: the account that uploaded a Version never reviews it. */
export const SELF_REVIEW_REASON = 'You uploaded this version — another account must review it.'

export function isOwnUpload(uploadedBy: string | null | undefined, accountId: string | null | undefined): boolean {
  return !!uploadedBy && !!accountId && uploadedBy === accountId
}
