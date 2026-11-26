// NFR-04 click counts and NFR-05 scenarios FR-09 (upload), FR-11 (review by the
// other account) and FR-19 (readiness view), in one browser at 1280 x 800.
// Usage: node scenarios.mjs <chromium|firefox|msedge>
import path from 'node:path'
import { chromium, firefox } from '@playwright/test'
import fs from 'node:fs'
import { signIn, APP, EV4, EV5, save } from './lib.mjs'

const which = process.argv[2]
import { fileURLToPath } from 'node:url'
const FILE = path.join(path.dirname(fileURLToPath(import.meta.url)), 'nfr-test-certificate.png')

// One Missing entry per browser (a seafarer with an upcoming assignment within the horizon).
const TARGETS = {
  chromium: { seafarer: 'Rodrigo Bondarenko', filter: 'Rodrigo Bondarenko', type: 'Basic Safety Training', typeId: 5 },
  firefox: { seafarer: 'Yusuf Dvorak', filter: 'Yusuf Dvorak', type: 'Medical Certificate', typeId: 3 },
  chrome: { seafarer: 'Ivan Horvat', filter: 'Ivan Horvat', type: 'Flag Endorsement of CoC', typeId: 7 },
  msedge: { seafarer: 'Luis Hansen', filter: 'Luis Hansen', type: 'Medical Certificate', typeId: 3 },
}
// Extra upload as account B (chromium only), for the NFR-04 click count.
const B_UPLOAD = { seafarer: 'Bogdan Georgiev', filter: 'Bogdan Georgiev', type: 'Basic Safety Training', typeId: 5 }

const T = 90000
const out = path.join(EV5, 'scenarios', which)
const result = { browser: which, started: new Date().toISOString(), steps: [], consoleErrors: [], pageErrors: [] }
const log = (s) => {
  console.log(s)
  result.steps.push(s)
}

async function launch() {
  if (which === 'firefox') return firefox.launch()
  if (which === 'msedge') return chromium.launch({ channel: 'msedge' })
  if (which === 'chrome') return chromium.launch({ channel: 'chrome' })
  return chromium.launch()
}

const browser = await launch()
result.version = browser.version()

async function newPage(tag) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } })
  const page = await ctx.newPage()
  page.on('console', (m) => m.type() === 'error' && result.consoleErrors.push(`[${tag}] ${m.text()}`))
  page.on('pageerror', (e) => result.pageErrors.push(`[${tag}] ${e.message}`))
  return page
}

/** Every counted click goes through here. */
function counter(page) {
  let n = 0
  return {
    async click(locator, what) {
      await locator.click({ timeout: T })
      n++
      log(`  click ${n}: ${what}`)
    },
    get n() {
      return n
    },
  }
}

const shot = (page, name) => page.screenshot({ path: path.join(out, `${name}.png`), fullPage: false })

async function dashboard(page) {
  await page.goto(`${APP}/`)
  await page.getByRole('tab', { name: /Missing/ }).waitFor({ timeout: T })
}

function card(page, seafarer) {
  return page
    .locator('ul.space-y-3 > li')
    .filter({ has: page.getByRole('link', { name: seafarer, exact: true }) })
}

async function upload(page, target, label) {
  const c = counter(page)
  await dashboard(page)
  // typing does not count
  await page.locator('#dashboard-search').fill(target.filter)
  const entry = card(page, target.seafarer).locator('li').filter({ hasText: target.type })
  await entry.first().waitFor({ timeout: T })
  await c.click(entry.getByRole('link', { name: 'Upload', exact: true }), `Upload in the Missing queue (${target.seafarer}, ${target.type})`)
  const dialog = page.getByRole('dialog')
  let opened
  try {
    await dialog.getByRole('heading', { name: 'Upload document' }).waitFor({ timeout: 30000 })
    opened = c.n
  } catch {
    // form not opened by the link: open it on the seafarer record
    await c.click(page.getByRole('button', { name: 'Upload document' }), 'Upload document')
    await dialog.waitFor({ timeout: T })
    opened = c.n
  }
  // the type list loads after the form opens; read the choice once the options are there
  await dialog.locator('#version-type option').nth(1).waitFor({ state: 'attached', timeout: T })
  await page.waitForTimeout(300)
  const preselected = await dialog.locator('#version-type').inputValue()
  const preselectedOk = preselected === String(target.typeId)
  log(`  form open after ${opened} click(s); type preselected: ${preselected} (${preselectedOk ? 'OK' : 'NOT the missing type'})`)
  if (!preselectedOk) await dialog.locator('#version-type').selectOption(String(target.typeId))
  await dialog.locator('#version-number').fill(`NFR-${which}-${label}`)
  await dialog.locator('#version-authority').fill('NFR browser test authority')
  await dialog.locator('#version-issued').fill('2026-06-01')
  await dialog.locator('#version-expiry').fill('2028-05-31')
  await shot(page, `${label}-1-form`)
  const chooser = page.waitForEvent('filechooser', { timeout: T })
  await c.click(dialog.getByRole('button', { name: /Upload document file/ }), 'file area (opens the file chooser)')
  await (await chooser).setFiles(FILE)
  await dialog.getByText('nfr-test-certificate.png').waitFor({ timeout: T })
  await c.click(dialog.getByRole('button', { name: 'Upload', exact: true }), 'Upload (submit)')
  await dialog.waitFor({ state: 'hidden', timeout: T })
  const url = page.url()
  log(`  upload finished after ${c.n} clicks; at ${url}`)
  await shot(page, `${label}-2-after-upload`)
  return { open: opened, finish: c.n, preselected: preselectedOk, url }
}

async function selfReviewChecks(page, target) {
  // As the uploader: Waiting for review shows the reason and "Open", not "Review".
  await dashboard(page)
  await page.getByRole('tab', { name: /Waiting for review/ }).click()
  await page.locator('#dashboard-search').fill(target.filter)
  const entry = card(page, target.seafarer).locator('li').filter({ hasText: target.type })
  await entry.first().waitFor({ timeout: T })
  const queueReason = await entry.getByText(/You uploaded this version/).count()
  const queueReview = await entry.getByRole('link', { name: 'Review', exact: true }).count()
  const queueOpen = await entry.getByRole('link', { name: 'Open', exact: true }).count()
  await shot(page, 'A-waiting-for-review-own-upload')
  await entry.getByRole('link', { name: 'Open', exact: true }).click({ timeout: T })
  const v1 = page.locator('li[aria-label="Version 1"]')
  await v1.waitFor({ timeout: T })
  const docReason = await v1.getByText('You uploaded this version — another account must review it.').count()
  const docReview = await v1.getByRole('button', { name: 'Review', exact: true }).count()
  await shot(page, 'A-document-own-upload')
  const ok = queueReason > 0 && queueReview === 0 && queueOpen > 0 && docReason > 0 && docReview === 0
  log(`  self-review: queue reason=${queueReason} Review link=${queueReview} Open=${queueOpen}; document reason=${docReason} Review button=${docReview} -> ${ok ? 'OK' : 'FAIL'}`)
  return { ok, queueReason, queueReview, queueOpen, docReason, docReview, documentUrl: page.url() }
}

async function review(page, target) {
  const c = counter(page)
  await dashboard(page)
  await c.click(page.getByRole('tab', { name: /Waiting for review/ }), 'Waiting for review tab')
  await page.locator('#dashboard-search').fill(target.filter)
  const entry = card(page, target.seafarer).locator('li').filter({ hasText: target.type })
  await entry.first().waitFor({ timeout: T })
  await shot(page, 'B-1-waiting-for-review')
  await c.click(entry.getByRole('link', { name: 'Review', exact: true }), `Review in the queue (${target.seafarer})`)
  const v1 = page.locator('li[aria-label="Version 1"]')
  await v1.waitFor({ timeout: T })
  await c.click(v1.getByRole('button', { name: 'Review', exact: true }), 'Review on version 1')
  const dialog = page.getByRole('dialog')
  await dialog.locator('#review-comment').waitFor({ timeout: T })
  const opened = c.n
  await dialog.locator('#review-comment').fill('NFR-05 browser check: details match the file.')
  await shot(page, 'B-2-review-form')
  await c.click(dialog.getByRole('button', { name: 'Accept', exact: true }), 'Accept (submit)')
  await dialog.waitFor({ state: 'hidden', timeout: T })
  await v1.getByText('Reviewed', { exact: true }).waitFor({ timeout: T })
  await shot(page, 'B-3-reviewed')
  log(`  review: open after ${opened}, finished after ${c.n} clicks`)
  return { open: opened, finish: c.n }
}

async function readiness(page, target) {
  const c = counter(page)
  await dashboard(page)
  await c.click(page.getByRole('tab', { name: /Starting soon/ }), 'Starting soon tab')
  await page.locator('#dashboard-search').fill(target.filter)
  const row = page.locator('li').filter({ has: page.getByRole('link', { name: target.seafarer, exact: true }) }).filter({ has: page.getByRole('link', { name: 'Readiness' }) })
  await row.first().waitFor({ timeout: T })
  await shot(page, 'B-4-starting-soon')
  await c.click(row.first().getByRole('link', { name: 'Readiness', exact: true }), `Readiness (${target.seafarer})`)
  await page.getByRole('heading', { name: /Readiness:/ }).waitFor({ timeout: T })
  await page.getByText(/Before joining/).first().waitFor({ timeout: T })
  await shot(page, 'B-5-readiness')
  log(`  readiness: open after ${c.n} clicks; ${page.url()}`)
  return { open: c.n, finish: c.n, url: page.url() }
}

// Targets picked from the live data by scripts/verification/scenario_targets.py (the seed changed).
const LIVE = path.join(EV4, '..', 'U', 'targets.json')
if (fs.existsSync(LIVE)) { const t = JSON.parse(fs.readFileSync(LIVE, 'utf8')); Object.assign(TARGETS, t); if (t.B) Object.assign(B_UPLOAD, t.B) }
const target = TARGETS[which]
try {
  log(`${which} ${result.version}: sign in A`)
  const a = await newPage('A')
  await signIn(a, 'a')
  log('FR-09 upload as A')
  result.fr09 = await upload(a, target, 'A-upload')
  result.selfReview = await selfReviewChecks(a, target)

  log('sign in B')
  const b = await newPage('B')
  await signIn(b, 'b')
  log('FR-11 review as B')
  result.fr11 = await review(b, target)
  log('FR-19 readiness as B')
  result.fr19 = await readiness(b, target)
  if (which === 'chromium') {
    log('NFR-04 upload of a missing document as B')
    result.bUpload = await upload(b, B_UPLOAD, 'B-upload')
  }
  result.ok = true
} catch (e) {
  result.ok = false
  result.error = String(e.stack || e)
  console.error(e)
} finally {
  result.finished = new Date().toISOString()
  save(path.join(out, 'result.json'), result)
  if (which === 'chromium') save(path.join(EV4, 'clicks-chromium.json'), result)
  await browser.close()
}
