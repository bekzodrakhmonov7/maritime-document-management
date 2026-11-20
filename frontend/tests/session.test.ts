import { test, beforeEach } from 'node:test'
import assert from 'node:assert/strict'

import {
  REFRESH_MARGIN_SECONDS,
  SESSION_KEY,
  forgetLegacySessions,
  onSessionChange,
  readSession,
  secondsUntilRefresh,
  sessionFromTokens,
  writeSession,
} from '../src/lib/session.ts'

class MemoryStorage {
  private items = new Map<string, string>()
  get length() {
    return this.items.size
  }
  key(i: number) {
    return [...this.items.keys()][i] ?? null
  }
  getItem(k: string) {
    return this.items.get(k) ?? null
  }
  setItem(k: string, v: string) {
    this.items.set(k, String(v))
  }
  removeItem(k: string) {
    this.items.delete(k)
  }
}

function jwt(claims: Record<string, unknown>): string {
  const part = (o: unknown) => Buffer.from(JSON.stringify(o)).toString('base64url')
  return `${part({ alg: 'HS256', typ: 'JWT' })}.${part(claims)}.signature`
}

const USER = '7f3cae85-87dd-4b45-9b64-6d623ebe43f5'
const ACCESS = jwt({ sub: USER, email: 'officer@example.com', exp: 2_000_000_000, aal: 'aal2' })

let storage: MemoryStorage
beforeEach(() => {
  storage = new MemoryStorage()
  ;(globalThis as { localStorage?: unknown }).localStorage = storage
})

test('a session from the proxy keeps both tokens and reads user and expiry from the token', () => {
  const session = sessionFromTokens({ access_token: ACCESS, refresh_token: 'r1' })
  assert.deepEqual(session, {
    access_token: ACCESS,
    refresh_token: 'r1',
    expires_at: 2_000_000_000,
    user: { id: USER, email: 'officer@example.com' },
  })
})

test('tokens that are not a session give none', () => {
  assert.equal(sessionFromTokens({ access_token: 'not-a-jwt', refresh_token: 'r1' }), null)
  assert.equal(sessionFromTokens({ access_token: jwt({ email: 'x' }), refresh_token: 'r1' }), null)
  assert.equal(sessionFromTokens({ access_token: ACCESS, refresh_token: '' }), null)
})

test('the session is kept under one app key and read back', () => {
  const session = sessionFromTokens({ access_token: ACCESS, refresh_token: 'r1' })
  writeSession(session)
  assert.deepEqual(storage.getItem(SESSION_KEY) && JSON.parse(storage.getItem(SESSION_KEY)!), {
    access_token: ACCESS,
    refresh_token: 'r1',
  })
  assert.deepEqual(readSession(), session)
  assert.equal(storage.length, 1)
})

test('signing out removes it', () => {
  writeSession(sessionFromTokens({ access_token: ACCESS, refresh_token: 'r1' }))
  writeSession(null)
  assert.equal(storage.getItem(SESSION_KEY), null)
  assert.equal(readSession(), null)
})

test('a damaged stored value counts as no session', () => {
  storage.setItem(SESSION_KEY, '{oops')
  assert.equal(readSession(), null)
  storage.setItem(SESSION_KEY, JSON.stringify({ access_token: 'x' }))
  assert.equal(readSession(), null)
})

test('without storage there is simply no session', () => {
  ;(globalThis as { localStorage?: unknown }).localStorage = {
    getItem() {
      throw new Error('blocked')
    },
    setItem() {
      throw new Error('blocked')
    },
    removeItem() {
      throw new Error('blocked')
    },
  }
  assert.equal(readSession(), null)
  writeSession(null) // does not throw
})

test('listeners hear every change, and stop when unsubscribed', () => {
  const heard: (string | null)[] = []
  const stop = onSessionChange((s) => heard.push(s?.refresh_token ?? null))
  writeSession(sessionFromTokens({ access_token: ACCESS, refresh_token: 'r1' }))
  writeSession(null)
  stop()
  writeSession(sessionFromTokens({ access_token: ACCESS, refresh_token: 'r2' }))
  assert.deepEqual(heard, ['r1', null])
})

test('the session is renewed shortly before it expires', () => {
  const session = sessionFromTokens({ access_token: ACCESS, refresh_token: 'r1' })!
  const now = 2_000_000_000 - 3600
  assert.equal(secondsUntilRefresh(session, now), 3600 - REFRESH_MARGIN_SECONDS)
  assert.equal(secondsUntilRefresh(session, 2_000_000_000 - 10), 0)
  assert.equal(secondsUntilRefresh(session, 2_000_000_100), 0)
})

test('a session left behind by the old Supabase client is removed', () => {
  storage.setItem('sb-127-auth-token', '{"access_token":"old"}')
  storage.setItem('sb-abcdefgh-auth-token', '{}')
  storage.setItem('theme', 'dark')
  forgetLegacySessions()
  assert.equal(storage.getItem('sb-127-auth-token'), null)
  assert.equal(storage.getItem('sb-abcdefgh-auth-token'), null)
  assert.equal(storage.getItem('theme'), 'dark')
})
