import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

// ADR-0005: signing in is a password, then an e-mailed code, and both steps go
// through the API's sign-in proxy. A session from Supabase Auth directly
// (password alone or code alone) is refused by the API, so the app must never
// ask Supabase Auth for one, nor change a password behind the proxy's back.
const SRC = fileURLToPath(new URL('../src/', import.meta.url))

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return sourceFiles(path)
    return /\.(ts|tsx)$/.test(name) ? [path] : []
  })
}

const FORBIDDEN = [
  /\bsignUp\b/,
  /\bsignInWithPassword\b/,
  /\bsignInWithOtp\b/,
  /\bverifyOtp\b/,
  /\bupdateUser\b/,
  /\bresetPasswordForEmail\b/,
]

test('no direct Supabase Auth sign-in or password call remains in frontend/src', () => {
  const hits = sourceFiles(SRC).flatMap((file) => {
    const text = readFileSync(file, 'utf8')
    return FORBIDDEN.filter((re) => re.test(text)).map((re) => `${file}: ${re}`)
  })
  assert.deepEqual(hits, [])
})
