/** What an Endorsement's Effective Expiry needs to be explained (FR-14). */
export interface EffectiveExpiryFields {
  /** The Current Version's own expiry date. */
  ownExpiry: string | null
  effectiveExpiry: string | null
  /** The certificate's Document Type when its date caps the Endorsement. */
  cappedBy: string | null
  certificateMissing: boolean
}

/** The API's fields (a document summary, a readiness or a queue entry) as the
 * cap note reads them. */
export function effectiveExpiryOf(
  item: { effective_expiry: string | null; capped_by: string | null; certificate_missing: boolean },
  ownExpiry: string | null,
): EffectiveExpiryFields {
  return {
    ownExpiry,
    effectiveExpiry: item.effective_expiry,
    cappedBy: item.capped_by,
    certificateMissing: item.certificate_missing,
  }
}

/** Whether the Effective Expiry isn't simply the own date: capped by the
 * certificate, or no certificate behind it. */
export function hasCapNote({ cappedBy, effectiveExpiry, certificateMissing }: EffectiveExpiryFields): boolean {
  return certificateMissing || (cappedBy !== null && effectiveExpiry !== null)
}
