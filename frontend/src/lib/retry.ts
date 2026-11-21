function statusOf(error: unknown): number | undefined {
  const status = (error as { status?: unknown } | null)?.status
  return typeof status === 'number' ? status : undefined
}

/** React Query `retry`: a 4xx answer won't change on a retry (and an
 * out-of-Scope 404 writes an Access refused record each time), so only other
 * failures are retried, up to three times like the default. */
export function retryUnlessClientError(failureCount: number, error: unknown): boolean {
  const status = statusOf(error)
  if (status !== undefined && status >= 400 && status < 500) return false
  return failureCount < 3
}

export function isNotFound(error: unknown): boolean {
  return statusOf(error) === 404
}
