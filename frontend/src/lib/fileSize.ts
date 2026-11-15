/**
 * The largest file, in MB, the Settings can allow (ADR 0003: Vercel refuses
 * request bodies over 4.5 MB). The API holds the same ceiling.
 */
export const FILE_SIZE_CEILING_MB = 4
