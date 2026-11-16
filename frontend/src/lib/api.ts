import { resolveApiBase } from './apiBase'

const API_BASE = resolveApiBase(import.meta.env.VITE_API_BASE)

/** An error response from the API. `code` is set for refused accounts. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string | null

  constructor(status: number, message: string, code: string | null = null) {
    super(message)
    this.status = status
    this.code = code
  }
}

type Listener = () => void
const switchedOffListeners = new Set<Listener>()

/** Called whenever the API says this account has been switched off. */
export function onAccountSwitchedOff(listener: Listener): () => void {
  switchedOffListeners.add(listener)
  return () => switchedOffListeners.delete(listener)
}

const sessionRefusedListeners = new Set<Listener>()

/** Called whenever the API refuses the session because it did not pass both
 * sign-in steps (ADR-0005), e.g. one started before passwords came back. */
export function onSessionRefused(listener: Listener): () => void {
  sessionRefusedListeners.add(listener)
  return () => sessionRefusedListeners.delete(listener)
}

async function toApiError(res: Response): Promise<ApiError> {
  const text = await res.text()
  try {
    const body = JSON.parse(text) as { detail?: unknown }
    const detail = body.detail
    if (detail && typeof detail === 'object' && 'code' in detail) {
      const d = detail as { code: string; message?: string }
      return new ApiError(res.status, d.message ?? d.code, d.code)
    }
    if (typeof detail === 'string') return new ApiError(res.status, detail)
    if (Array.isArray(detail)) {
      const msgs = detail.map((d: { msg?: string }) => d.msg).filter(Boolean)
      return new ApiError(res.status, msgs.join('; ') || `HTTP ${res.status}`)
    }
  } catch {
    // not JSON
  }
  return new ApiError(res.status, text || `HTTP ${res.status}`)
}

/** A request with the session's token; a refusal becomes an ApiError. */
async function authorizedFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const { supabase } = await import('./supabase')
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token

  const headers = new Headers(options.headers)
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })

  if (!res.ok) {
    const err = await toApiError(res)
    if (err.code === 'account_deactivated') {
      switchedOffListeners.forEach((listener) => listener())
    }
    if (err.code === 'session_not_verified') {
      sessionRefusedListeners.forEach((listener) => listener())
    }
    throw err
  }
  return res
}

export async function apiFetch<T = unknown>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await authorizedFetch(path, options)

  if (res.status === 204 || res.headers.get('content-length') === '0') {
    return undefined as T
  }

  return res.json() as Promise<T>
}

/** A file from the API, saved through the browser under the name it gives.
 * Returns the response headers. */
export async function apiDownload(path: string, fallbackName: string): Promise<Headers> {
  const res = await authorizedFetch(path)
  const disposition = res.headers.get('content-disposition') ?? ''
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? fallbackName
  const url = URL.createObjectURL(await res.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  URL.revokeObjectURL(url)
  return res.headers
}
