import type { QueryClient, QueryKey } from '@tanstack/react-query'
import { resolveApiBase } from './apiBase'
import { readSession, secondsUntilRefresh, sessionFromTokens, writeSession } from './session'

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
 * sign-in steps through the proxy (ADR 0005) or lacks the authenticator
 * code (aal2, ADR 0007), e.g. one started before TOTP came in. */
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

let refreshing: Promise<string | null> | null = null

/**
 * Renew the session through the API (SR-01: never at Supabase Auth). One
 * renewal at a time: a refresh token works only once. Returns the new
 * access token, or null. A refused renewal ends the session here; when the
 * API can't be reached the session is kept for another try.
 */
export function refreshSession(): Promise<string | null> {
  refreshing ??= (async () => {
    const current = readSession()
    if (!current) return null
    let res: Response
    try {
      res = await fetch(`${API_BASE}/api/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: current.refresh_token }),
      })
    } catch {
      return null
    }
    if (res.ok) {
      const renewed = sessionFromTokens(await res.json())
      writeSession(renewed)
      return renewed?.access_token ?? null
    }
    if (res.status === 401 || res.status === 403) {
      const err = await toApiError(res)
      if (err.code === 'account_deactivated') {
        switchedOffListeners.forEach((listener) => listener())
      }
      // Another tab may have renewed it with the same refresh token first.
      if (readSession()?.refresh_token === current.refresh_token) writeSession(null)
    }
    return null
  })().finally(() => {
    refreshing = null
  })
  return refreshing
}

/** The access token to send, renewed first when it is about to expire. */
async function accessToken(): Promise<string | null> {
  const session = readSession()
  if (!session) return null
  if (secondsUntilRefresh(session) > 0) return session.access_token
  return (await refreshSession()) ?? readSession()?.access_token ?? null
}

function send(path: string, options: RequestInit, token: string | null): Promise<Response> {
  const headers = new Headers(options.headers)
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  return fetch(`${API_BASE}${path}`, { ...options, headers })
}

/** A request with the session's token; a refusal becomes an ApiError. A 401
 * renews the session once and tries again. */
async function authorizedFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = await accessToken()
  let res = await send(path, options, token)
  if (res.status === 401 && token) {
    const renewed = await refreshSession()
    if (renewed) res = await send(path, options, renewed)
  }

  if (!res.ok) {
    const err = await toApiError(res)
    if (err.code === 'account_deactivated') {
      switchedOffListeners.forEach((listener) => listener())
    }
    if (err.code === 'session_not_verified' || err.code === 'second_factor_missing') {
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

/** A JSON request: `body` (if given) is sent as JSON. */
export function apiSend<T = unknown>(method: string, path: string, body?: unknown): Promise<T> {
  return apiFetch<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) })
}

/** Refresh every query under each of the given keys. */
export function invalidate(queryClient: QueryClient, ...keys: QueryKey[]) {
  return Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })))
}
