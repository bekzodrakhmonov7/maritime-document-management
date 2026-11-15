/**
 * The origin the API is called on, from `VITE_API_BASE`.
 *
 * Unset means local development: the API runs on its own port. Explicitly
 * empty means the page's own origin, as on Vercel, where the API is served
 * under `/api` next to the app (ADR 0003).
 */
export function resolveApiBase(value: string | undefined): string {
  return value ?? 'http://localhost:8000'
}
