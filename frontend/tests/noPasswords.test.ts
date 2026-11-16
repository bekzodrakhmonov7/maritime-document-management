import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

// ADR-0004: a Sign-in Code is the only way in; no password field or
// password/OTP sign-in call may remain in the app.
const SRC = new URL('../src/', import.meta.url).pathname

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return sourceFiles(path)
    return /\.(ts|tsx)$/.test(name) ? [path] : []
  })
}

const FORBIDDEN = [
  /type=["']password["']/,
  /\bsignUp\b/,
  /\bsignInWithPassword\b/,
  /\bsignInWithOtp\b/,
  /\bpassword\b/i,
]

test('no password field or password/OTP sign-in call remains in frontend/src', () => {
  const hits = sourceFiles(SRC).flatMap((file) => {
    const text = readFileSync(file, 'utf8')
    return FORBIDDEN.filter((re) => re.test(text)).map((re) => `${file}: ${re}`)
  })
  assert.deepEqual(hits, [])
})
