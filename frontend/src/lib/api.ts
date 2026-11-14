const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

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

export async function apiFetch<T = unknown>(path: string, options: RequestInit = {}): Promise<T> {
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
    throw err
  }

  if (res.status === 204 || res.headers.get('content-length') === '0') {
    return undefined as T
  }

  return res.json() as Promise<T>
}
