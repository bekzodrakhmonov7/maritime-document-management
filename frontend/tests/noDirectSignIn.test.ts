import { test } from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

// ADR 0005, ADR 0007, SR-01: signing in is a password, then an authenticator
// (TOTP) code, and every call to Supabase Auth goes through the API: the
// sign-in proxy, renewing the session (/api/auth/refresh) and signing out.
// The web client never calls Supabase Auth itself, so it has no Supabase
// client, URL or public key at all.
const FRONTEND = fileURLToPath(new URL('../', import.meta.url))
const SRC = join(FRONTEND, 'src')

function files(dir: string, pattern: RegExp): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return files(path, pattern)
    return pattern.test(name) ? [path] : []
  })
}

function hits(paths: string[], forbidden: RegExp[]): string[] {
  return paths.flatMap((file) => {
    const text = readFileSync(file, 'utf8')
    return forbidden.filter((re) => re.test(text)).map((re) => `${file}: ${re}`)
  })
}

const FORBIDDEN = [
  /\bsignUp\b/,
  /\bsignInWithPassword\b/,
  /\bsignInWithOtp\b/,
  /\bverifyOtp\b/,
  /\bupdateUser\b/,
  /\bresetPasswordForEmail\b/,
  /\bmfa\./,
  /@supabase\//,
  /VITE_SUPABASE/,
]

test('no Supabase client or direct Supabase Auth call remains in frontend/src', () => {
  assert.deepEqual(hits(files(SRC, /\.(ts|tsx)$/), FORBIDDEN), [])
})

test('package.json has no Supabase dependency', () => {
  const pkg = JSON.parse(readFileSync(join(FRONTEND, 'package.json'), 'utf8')) as Record<
    string,
    Record<string, string> | undefined
  >
  const names = [...Object.keys(pkg.dependencies ?? {}), ...Object.keys(pkg.devDependencies ?? {})]
  assert.deepEqual(
    names.filter((name) => name.includes('supabase')),
    [],
  )
})

test('the built app has no Supabase Auth address in it', () => {
  // A build of its own, so the check never reads a stale dist/.
  const out = mkdtempSync(join(tmpdir(), 'mdm-dist-'))
  try {
    execFileSync(
      process.execPath,
      [
        join(FRONTEND, 'node_modules/vite/bin/vite.js'),
        'build',
        '--outDir',
        out,
        '--emptyOutDir',
        '--logLevel',
        'error',
      ],
      { cwd: FRONTEND, stdio: 'inherit' },
    )
    const built = files(out, /\.(js|html|css)$/)
    assert.ok(built.length > 0, 'the build wrote no files')
    assert.deepEqual(hits(built, [/supabase\.co/, /\/auth\/v1/]), [])
  } finally {
    rmSync(out, { recursive: true, force: true })
  }
})
