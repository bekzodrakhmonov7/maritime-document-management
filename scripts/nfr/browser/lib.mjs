// Shared helpers for the NFR-04/05 browser checks (local stack only).
// Sign-in is password + TOTP (since be4f354): each browser test account is
// enrolled once by scripts/verification/browser_accounts.py, which keeps its
// e-mail, password and TOTP secret in the git-ignored evidence folder; the code
// is computed here with RFC 6238 (HMAC-SHA1, 30 s, 6 digits).
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
export const APP = process.env.APP_URL ?? 'http://localhost:5173'
// Evidence lives in the main checkout's git-ignored docs/ (EVIDENCE_DIR overrides).
const EVIDENCE = process.env.EVIDENCE_DIR ?? path.join(ROOT, '..', 'maritime-document-management', 'docs', 'ch4-evidence')
const RUN = process.env.NFR_RUN
export const EV4 = path.join(EVIDENCE, 'U1', RUN ?? '')
export const EV5 = path.join(EVIDENCE, 'U2', RUN ?? '')
const ACCOUNTS = path.join(EVIDENCE, 'U', 'browser-accounts.json')

/** { email, password, secret } of browser test account `letter` (a, b, ...). */
export function account(letter) {
  const all = JSON.parse(fs.readFileSync(ACCOUNTS, 'utf8'))
  const a = all[letter]
  if (!a) throw new Error(`no browser account ${letter}`)
  return a
}

function base32(s) {
  const alpha = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  let bits = ''
  for (const ch of s.replace(/=+$/, '').toUpperCase()) bits += alpha.indexOf(ch).toString(2).padStart(5, '0')
  const out = []
  for (let i = 0; i + 8 <= bits.length; i += 8) out.push(parseInt(bits.slice(i, i + 8), 2))
  return Buffer.from(out)
}

/** RFC 6238 TOTP code for `secret` at `when` (ms). */
export function totp(secret, when = Date.now()) {
  const counter = Math.floor(when / 1000 / 30)
  const msg = Buffer.alloc(8)
  msg.writeBigUInt64BE(BigInt(counter))
  const h = crypto.createHmac('sha1', base32(secret)).update(msg).digest()
  const o = h[h.length - 1] & 0xf
  const n = ((h.readUInt32BE(o) & 0x7fffffff) % 1_000_000).toString()
  return n.padStart(6, '0')
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const lastCode = new Map()

/** Password, then the authenticator code, through the real sign-in page. */
export async function signIn(page, letter) {
  const { email, password, secret } = account(letter)
  for (let attempt = 0; attempt < 3; attempt++) {
    await page.goto(`${APP}/login`)
    await page.locator('#email').fill(email)
    await page.locator('#password').fill(password)
    await page.locator('button[type=submit]').click()
    const codeBox = page.locator('#code')
    await codeBox.waitFor({ timeout: 20000 }).catch(() => {})
    if (!(await codeBox.isVisible())) continue
    // Supabase Auth refuses a code twice: wait for a fresh window if needed.
    let code = totp(secret)
    while (code === lastCode.get(email) || 30 - ((Date.now() / 1000) % 30) < 3) {
      await sleep(1000)
      code = totp(secret)
    }
    lastCode.set(email, code)
    await codeBox.fill(code)
    await page.locator('button[type=submit]').click()
    await page.waitForURL(`${APP}/`, { timeout: 30000 })
    return
  }
  throw new Error(`sign-in failed for ${email}`)
}

export function save(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, typeof data === 'string' ? data : JSON.stringify(data, null, 2))
}
