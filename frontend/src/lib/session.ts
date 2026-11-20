/**
 * The signed-in session, kept in the browser (SR-01).
 *
 * The web client never calls Supabase Auth: the API's sign-in proxy hands
 * over the session, `/api/auth/refresh` renews it and `/api/auth/logout`
 * ends it. The two tokens are kept in `localStorage` under one app key (the
 * same storage the Supabase client used); who is signed in and until when
 * is read from the access token. The API checks its signature; here it is
 * only read.
 */

export const SESSION_KEY = 'mdm.session'
/** Renew the session this many seconds before its access token expires. */
export const REFRESH_MARGIN_SECONDS = 60

export interface SessionTokens {
  access_token: string
  refresh_token: string
}

export interface User {
  id: string
  email: string | null
}

export interface Session extends SessionTokens {
  /** When the access token expires, in seconds since the epoch. */
  expires_at: number
  user: User
}

type Listener = (session: Session | null) => void
const listeners = new Set<Listener>()

function claimsOf(token: string): Record<string, unknown> | null {
  const part = token.split('.')[1]
  if (!part) return null
  try {
    const base64 = part.replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
    const bytes = Uint8Array.from(atob(padded), (c) => c.charCodeAt(0))
    const claims: unknown = JSON.parse(new TextDecoder().decode(bytes))
    return claims && typeof claims === 'object' ? (claims as Record<string, unknown>) : null
  } catch {
    return null
  }
}

/** The session the tokens stand for, or null when they are not one. */
export function sessionFromTokens(tokens: Partial<SessionTokens> | null): Session | null {
  const { access_token, refresh_token } = tokens ?? {}
  if (typeof access_token !== 'string' || typeof refresh_token !== 'string' || !refresh_token) {
    return null
  }
  const claims = claimsOf(access_token)
  if (!claims || typeof claims.sub !== 'string' || typeof claims.exp !== 'number') return null
  return {
    access_token,
    refresh_token,
    expires_at: claims.exp,
    user: { id: claims.sub, email: typeof claims.email === 'string' ? claims.email : null },
  }
}

export function readSession(): Session | null {
  try {
    const text = localStorage.getItem(SESSION_KEY)
    return text ? sessionFromTokens(JSON.parse(text) as Partial<SessionTokens>) : null
  } catch {
    return null
  }
}

/** Keep the session (null: forget it) and tell the listeners. */
export function writeSession(session: Session | null): void {
  try {
    if (session) {
      const { access_token, refresh_token } = session
      localStorage.setItem(SESSION_KEY, JSON.stringify({ access_token, refresh_token }))
    } else {
      localStorage.removeItem(SESSION_KEY)
    }
  } catch {
    // Storage blocked: the session lasts only as long as the page.
  }
  listeners.forEach((listener) => listener(session))
}

/** Called whenever the session changes, in this tab or another one. */
export function onSessionChange(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key === SESSION_KEY || event.key === null) {
      const session = readSession()
      listeners.forEach((listener) => listener(session))
    }
  })
}

/** Seconds until the session should be renewed (0: now). */
export function secondsUntilRefresh(session: Session, nowSeconds = Date.now() / 1000): number {
  return Math.max(0, session.expires_at - REFRESH_MARGIN_SECONDS - nowSeconds)
}

/** Remove a session the Supabase client kept in earlier versions. */
export function forgetLegacySessions(): void {
  try {
    const keys = Array.from({ length: localStorage.length }, (_, i) => localStorage.key(i))
    keys
      .filter((key): key is string => !!key && /^sb-.+-auth-token$/.test(key))
      .forEach((key) => localStorage.removeItem(key))
  } catch {
    // nothing to clean up
  }
}
