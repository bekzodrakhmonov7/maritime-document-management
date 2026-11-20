// Shared helpers for the NFR-04/05 browser checks (local stack only).
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
export const APP = 'http://localhost:5173'
export const MAILPIT = 'http://127.0.0.1:54324'
// NFR_RUN=after-fix writes a second run beside the first one.
const RUN = process.env.NFR_RUN
export const EV4 = path.join(ROOT, 'docs/nfr-evidence/nfr-04', RUN ? `${RUN}-run` : '')
export const EV5 = path.join(ROOT, 'docs/nfr-evidence/nfr-05', RUN ?? '')
const ACCOUNTS = path.join(ROOT, 'docs/nfr-evidence/nfr-05/test-accounts.txt')

/** Test passwords are kept in the git-ignored evidence folder. */
export function account(letter) {
  const txt = fs.readFileSync(ACCOUNTS, 'utf8')
  const email = `nfr-browser-${letter}@example.com`
  const line = txt.split(/\r?\n/).find((l) => l.startsWith(email + ' '))
  return { email, password: line.split(' ')[1] }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function codeFor(email, since) {
  for (let i = 0; i < 30; i++) {
    const list = await (await fetch(`${MAILPIT}/api/v1/messages?limit=30`)).json()
    const m = list.messages.find(
      (m) => m.To.some((t) => t.Address === email) && new Date(m.Created).getTime() >= since - 2000,
    )
    if (m) {
      const full = await (await fetch(`${MAILPIT}/api/v1/message/${m.ID}`)).json()
      const code = full.Text.match(/\b\d{6}\b/)
      if (code) return code[0]
    }
    await sleep(500)
  }
  throw new Error(`no code for ${email}`)
}

/** Password then e-mailed code, through the real sign-in page. */
export async function signIn(page, letter) {
  const { email, password } = account(letter)
  for (let attempt = 0; attempt < 3; attempt++) {
    await page.goto(`${APP}/login`)
    await page.locator('#email').fill(email)
    await page.locator('#password').fill(password)
    const since = Date.now()
    await page.locator('button[type=submit]').click()
    const codeBox = page.locator('#code')
    const err = page.getByRole('alert')
    await Promise.race([codeBox.waitFor({ timeout: 20000 }), err.waitFor({ timeout: 20000 })]).catch(() => {})
    if (!(await codeBox.isVisible())) {
      // e.g. the e-mail send limit (one code per 60 s per address)
      await sleep(62000)
      continue
    }
    let code
    try {
      code = await codeFor(email, since)
    } catch {
      // the address got a code less than 60 s ago: no new e-mail was sent
      await sleep(62000)
      continue
    }
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
