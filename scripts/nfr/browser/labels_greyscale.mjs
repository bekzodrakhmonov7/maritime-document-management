// NFR-04: status labels per dimension and greyscale screenshots (Chromium, account B).
// Usage: node labels_greyscale.mjs [verificationDocId]
import path from 'node:path'
import { chromium } from '@playwright/test'
import { signIn, APP, EV4, save } from './lib.mjs'

const T = 90000
const NOT_CONFIRMED_DOC = process.argv[2] // a document made by the NFR-05 runs
const out = path.join(EV4, 'greyscale')
const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } })
const page = await ctx.newPage()
const errors = []
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
await signIn(page, 'b')

const result = { browser: `chromium ${browser.version()}`, when: new Date().toISOString(), pages: {}, labels: {} }

async function settle() {
  await page.waitForLoadState('networkidle', { timeout: T }).catch(() => {})
  await page.getByText('Loading…').first().waitFor({ state: 'hidden', timeout: T }).catch(() => {})
  await page.waitForTimeout(800)
}

// A "Not confirmed" verification, so that label can be seen (none in the volume data).
if (NOT_CONFIRMED_DOC) {
  await page.goto(`${APP}/documents/${NOT_CONFIRMED_DOC}`)
  const v1 = page.locator('li[aria-label="Version 1"]')
  await v1.waitFor({ timeout: T })
  if ((await v1.getByText('Not confirmed', { exact: true }).count()) === 0) {
    await v1.getByRole('button', { name: 'Record verification' }).click()
    const d = page.getByRole('dialog')
    await d.locator('#verification-date').fill('2026-11-20')
    await d.locator('#verification-result').selectOption('not_confirmed')
    await d.locator('#verification-source').fill('NFR test registry')
    await d.locator('#verification-reference').fill('NFR-04-NC')
    await d.getByRole('button', { name: 'Record', exact: true }).click()
    await d.waitFor({ state: 'hidden', timeout: T })
  }
}

// Greyscale on every page load from here on.
await ctx.addInitScript(() => {
  const apply = () => (document.documentElement.style.filter = 'grayscale(1)')
  if (document.documentElement) apply()
  document.addEventListener('DOMContentLoaded', apply)
})

async function collect(name) {
  const found = await page.evaluate(() => {
    const txt = (sel) => [...document.querySelectorAll(sel)].map((e) => e.textContent.trim()).filter(Boolean)
    const fromAria = (prefix) =>
      [...document.querySelectorAll(`[aria-label^="${prefix}"]`)].map((e) => e.getAttribute('aria-label').slice(prefix.length))
    return {
      expiry: fromAria('Expiry status: '),
      coverage: fromAria('Coverage: '),
      // Not reviewed tag, Reviewed / Rejected tag on a version, Verified shield
      tags: txt('span.inline-flex.items-center.gap-1'),
      reviewDecisions: txt('li[aria-label^="Version"] h4 + ul li > span.font-medium, li[aria-label^="Version"] ul li span.font-medium'),
      filter: getComputedStyle(document.documentElement).filter,
    }
  })
  result.pages[name] = found
  await page.screenshot({ path: path.join(out, `${name}.png`), fullPage: !name.startsWith('dashboard') })
}

await page.goto(`${APP}/`)
await page.getByRole('tab', { name: /Missing/ }).waitFor({ timeout: T })
await settle()
await page.locator('ul.space-y-3 > li').first().waitFor({ timeout: T })
for (const tab of ['Missing', 'Expired', 'Expiring soon', 'Expiry not stated', 'Waiting for review', 'Starting soon', 'In order']) {
  await page.getByRole('tab', { name: new RegExp('^' + tab) }).click()
  await page.waitForTimeout(700)
  await collect(`dashboard-${tab.toLowerCase().replace(/ /g, '-')}`)
}
const pages = {
  'seafarer-7': '/seafarers/7',
  'document-16-rejected-version': '/documents/16',
  'document-9-verified': '/documents/9',
  'readiness-assignment-5': '/assignments/5/readiness',
  'readiness-assignment-119-missing': '/assignments/119/readiness',
}
if (NOT_CONFIRMED_DOC) pages[`document-${NOT_CONFIRMED_DOC}-not-confirmed`] = `/documents/${NOT_CONFIRMED_DOC}`
for (const [name, url] of Object.entries(pages)) {
  await page.goto(APP + url)
  await settle()
  await collect(name)
}

const uniq = (k) => [...new Set(Object.values(result.pages).flatMap((p) => p[k]))].sort()
result.labels = {
  expiryStatus: uniq('expiry'),
  coverageClass: uniq('coverage'),
  reviewAndVerificationTags: uniq('tags'),
  reviewDecisionsAndVerificationResults: uniq('reviewDecisions'),
}
result.consoleErrors = errors
save(path.join(EV4, 'labels.json'), result)
console.log(JSON.stringify(result.labels, null, 2), 'filters:', [...new Set(Object.values(result.pages).map((p) => p.filter))], 'errors:', errors)
await browser.close()
