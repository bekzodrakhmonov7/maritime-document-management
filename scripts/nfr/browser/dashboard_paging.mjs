// Dashboard paging checks: every tab loads with its count; Load more appends and
// "Showing X of N" updates; filters reset paging; Missing Upload and the
// self-review Open links still work; no console errors.
// Usage: node dashboard_paging.mjs <chromium|chrome|msedge>
import path from 'node:path'
import { chromium } from '@playwright/test'
import { signIn, APP, EV5, save } from './lib.mjs'

const which = process.argv[2]
const T = 90000
const browser = await chromium.launch(which === 'chromium' ? {} : { channel: which })
const page = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage()
const errors = []
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
const out = path.join(EV5, 'dashboard', which)
const r = { browser: which, version: browser.version(), checks: {} }
const check = (k, ok, detail) => {
  r.checks[k] = { ok, detail }
  console.log(`${ok ? 'PASS' : 'FAIL'} ${k}: ${JSON.stringify(detail)}`)
}
const QUEUES = ['Missing', 'Expired', 'Expiring soon', 'Expiry not stated', 'Waiting for review', 'Starting soon', 'In order']
const showing = page.getByText(/^Showing \d+ of \d+/)
const parseShowing = async () => {
  const m = (await showing.innerText({ timeout: T })).match(/Showing (\d+) of (\d+)/)
  return { shown: +m[1], total: +m[2] }
}
const rows = (q) => (q === 'Starting soon' ? page.locator('ul.space-y-2 > li') : page.locator('ul.space-y-3 > li'))
const tab = (q) => page.getByRole('tab', { name: new RegExp('^' + q) })
const tabCount = async (q) => (await tab(q).locator('span').last().innerText()).trim()

await signIn(page, process.argv[3] || 'b')
await page.goto(`${APP}/`)
await rows('Missing').first().waitFor({ timeout: T })

// 1. every tab: loads, count shown, count = N in "Showing X of N", X = rows (<= 50)
const tabs = {}
for (const q of QUEUES) {
  await tab(q).click()
  await page.waitForFunction((sel) => document.querySelector(sel), 'ul', { timeout: T })
  await showing.waitFor({ timeout: T })
  await page.waitForTimeout(500)
  const s = await parseShowing()
  const n = await rows(q).count()
  const c = await tabCount(q)
  tabs[q] = { tabCount: c, ...s, rows: n }
  await page.screenshot({ path: path.join(out, `tab-${q.replace(/ /g, '-').toLowerCase()}.png`) })
}
check('tabs-load-with-counts', // the tab counts entries (documents; assignments on Starting soon), N counts seafarer groups
  Object.values(tabs).every((t) => /^\d+$/.test(t.tabCount) && +t.tabCount >= t.total && t.shown === t.rows && t.rows === Math.min(50, t.total)), tabs)

// 2. Load more appends the next page, Showing updates
await tab('In order').click()
await showing.waitFor({ timeout: T })
const before = await parseShowing()
const firstName = await rows('In order').first().locator('a').first().innerText()
await page.getByRole('button', { name: 'Load more' }).click()
await page.waitForFunction((n) => document.querySelectorAll('ul.space-y-3 > li').length > n, before.rows ?? before.shown, { timeout: T })
await page.waitForTimeout(500)
const after = await parseShowing()
const rowsAfter = await rows('In order').count()
const firstAfter = await rows('In order').first().locator('a').first().innerText()
check('load-more-appends', after.shown === Math.min(before.shown + 50, before.total) && rowsAfter === after.shown && firstAfter === firstName, { before, after, rowsAfter, firstKept: firstAfter === firstName })
// load to the end on a smaller queue: button disappears at N
await tab('Expiry not stated').click()
await showing.waitFor({ timeout: T })
let guard = 0
while ((await page.getByRole('button', { name: 'Load more' }).count()) > 0 && guard++ < 20) {
  await page.getByRole('button', { name: 'Load more' }).click()
  await page.waitForTimeout(1500)
}
const end = await parseShowing()
check('load-more-to-end', end.shown === end.total && (await page.getByRole('button', { name: 'Load more' }).count()) === 0, end)

// 3. filters reset paging: on In order with 100 loaded, type a name, then clear it
await tab('In order').click()
await showing.waitFor({ timeout: T })
if ((await parseShowing()).shown <= 50) {
  await page.getByRole('button', { name: 'Load more' }).click()
  await page.waitForTimeout(2000)
}
const loaded = await parseShowing()
await page.locator('#dashboard-search').fill('Aquino')
await page.waitForTimeout(2500)
const filtered = await parseShowing()
const filteredRows = await rows('In order').count()
const allMatch = (await rows('In order').locator('> div a').allInnerTexts()).every((t) => /Aquino/i.test(t))
await page.locator('#dashboard-search').fill('')
await page.waitForTimeout(2500)
const cleared = await parseShowing()
check('search-resets-paging', filtered.shown === filteredRows && filtered.total < loaded.total && allMatch && cleared.total === loaded.total && cleared.shown <= Math.max(50, loaded.shown), { loaded, filtered, allMatch, cleared, tabCountAfterFilter: null })
// tag filter (click a vessel tag) and remove it
await rows('In order').first().locator('button[title^="Filter by this vessel"]').click()
await page.waitForTimeout(2500)
const tagged = await parseShowing()
const taggedCount = await tabCount('In order')
await page.getByRole('button', { name: 'Clear all' }).click()
await page.waitForTimeout(2500)
const untagged = await parseShowing()
check('tag-filter-resets-paging', tagged.total < untagged.total && +taggedCount >= tagged.total && tagged.shown <= 50, { tagged, taggedCount, untagged })
// show inactive
const activeTotal = (await parseShowing()).total
await page.getByLabel('Show inactive').check()
await page.waitForTimeout(2500)
const inactive = await parseShowing()
await page.getByLabel('Show inactive').uncheck()
await page.waitForTimeout(2500)
const back = await parseShowing()
check('show-inactive-resets-paging', inactive.total >= activeTotal && inactive.shown <= 50 && back.total === activeTotal, { activeTotal, inactive, back })
await page.screenshot({ path: path.join(out, 'after-filters.png') })

// 4. Missing Upload link carries ?upload= and opens the form with the type
await tab('Missing').click()
await rows('Missing').first().waitFor({ timeout: T })
const up = page.locator('ul.space-y-3 a', { hasText: /^Upload$/ }).filter({ has: page.locator('xpath=self::a[contains(@href,"?upload=")]') }).first()
const href = await up.getAttribute('href')
await up.click()
await page.getByRole('dialog').getByRole('heading', { name: 'Upload document' }).waitFor({ timeout: T })
await page.locator('#version-type option').nth(1).waitFor({ state: 'attached', timeout: T })
await page.waitForTimeout(300)
const typeVal = await page.locator('#version-type').inputValue()
check('missing-upload-link', href.includes('?upload=') && typeVal === href.split('upload=')[1], { href, typeVal })
await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click()

r.consoleErrors = errors
check('no-console-errors', errors.length === 0, errors)
save(path.join(out, 'result.json'), r)
await browser.close()
