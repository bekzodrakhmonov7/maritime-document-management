// NFR-05: the main pages in one browser at 1280 x 800 and 1920 x 1080.
// Per page: horizontal scroll of the document, overflowing overflow-x containers,
// console errors, overlapping visible buttons/links (bounding boxes), a screenshot.
// Usage: node matrix.mjs <chromium|chrome|msedge|firefox>
import path from 'node:path'
import { chromium, firefox } from '@playwright/test'
import { signIn, APP, EV5, save } from './lib.mjs'

const which = process.argv[2]
const T = 90000
const VIEWPORTS = [
  { width: 1280, height: 800 },
  { width: 1920, height: 1080 },
]
const PAGES = {
  dashboard: '/',
  seafarers: '/seafarers',
  'seafarer-7-long-name': '/seafarers/7',
  'seafarer-447-longest-name': '/seafarers/447',
  'document-10': '/documents/10',
  'readiness-5': '/assignments/5/readiness',
  alerts: '/alerts',
  vessels: '/vessels',
  'vessel-1': '/vessels/1',
  'admin-accounts': '/admin/accounts',
  'admin-document-types': '/admin/document-types',
  'admin-positions': '/admin/positions',
  'admin-requirements': '/admin/requirements',
  'admin-settings': '/admin/settings',
  'admin-audit': '/admin/audit',
}

const browser =
  which === 'firefox'
    ? await firefox.launch()
    : await chromium.launch(which === 'chromium' ? {} : { channel: which })
const ctx = await browser.newContext({ viewport: VIEWPORTS[0] })
const page = await ctx.newPage()
let errors = []
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))

const result = { browser: which, version: browser.version(), started: new Date().toISOString(), runs: [] }
await signIn(page, 'a')

/** Runs in the page: layout checks for what is currently in view. */
function inspect() {
  const de = document.documentElement
  const hscroll = de.scrollWidth - de.clientWidth
  const overflowing = []
  for (const el of document.querySelectorAll('body *')) {
    const s = getComputedStyle(el)
    if (['auto', 'scroll'].includes(s.overflowX) && el.scrollWidth > el.clientWidth + 1) {
      overflowing.push(`${el.tagName.toLowerCase()}.${String(el.className).split(' ').slice(0, 4).join('.')} ${el.scrollWidth}>${el.clientWidth}`)
    }
  }
  const vis = (el) => {
    const s = getComputedStyle(el)
    if (s.visibility === 'hidden' || s.display === 'none' || Number(s.opacity) === 0) return null
    if (el.checkVisibility && !el.checkVisibility()) return null
    // the box as seen: clipped by every scrolling/clipping ancestor (the app's
    // content scrolls under its fixed header, which is not an overlap)
    const b = el.getBoundingClientRect()
    const r = { left: b.left, top: b.top, right: b.right, bottom: b.bottom }
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const ps = getComputedStyle(p)
      if (ps.overflowX !== 'visible' || ps.overflowY !== 'visible') {
        const c = p.getBoundingClientRect()
        r.left = Math.max(r.left, c.left)
        r.top = Math.max(r.top, c.top)
        r.right = Math.min(r.right, c.right)
        r.bottom = Math.min(r.bottom, c.bottom)
      }
    }
    r.width = r.right - r.left
    r.height = r.bottom - r.top
    if (r.width < 2 || r.height < 2) return null
    if (r.bottom <= 0 || r.right <= 0 || r.top >= innerHeight || r.left >= innerWidth) return null
    return r
  }
  const ctrls = [...document.querySelectorAll('a, button, [role=button], [role=tab]')]
    .map((el) => ({ el, r: vis(el) }))
    .filter((x) => x.r)
  const name = (el) => `${el.tagName.toLowerCase()}"${(el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 40)}"`
  const overlaps = []
  for (let i = 0; i < ctrls.length; i++) {
    for (let j = i + 1; j < ctrls.length; j++) {
      const a = ctrls[i], b = ctrls[j]
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue
      const w = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left)
      const h = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top)
      if (w > 1 && h > 1) overlaps.push(`${name(a.el)} x ${name(b.el)} (${w.toFixed(0)}x${h.toFixed(0)}px)`)
    }
  }
  return { hscroll, overflowing, overlaps, controls: ctrls.length }
}

/** The app scrolls inside its own container: scroll it to check rows further down. */
async function scrollSteps() {
  return page.evaluate(() => {
    const cands = [...document.querySelectorAll('body *')].filter((el) => {
      const s = getComputedStyle(el)
      return ['auto', 'scroll'].includes(s.overflowY) && el.scrollHeight > el.clientHeight + 1 && el.clientHeight > 300
    })
    const box = cands.sort((a, b) => b.clientHeight - a.clientHeight)[0]
    if (!box) return 0
    box.setAttribute('data-nfr-scroller', '1')
    return Math.min(5, Math.ceil((box.scrollHeight - box.clientHeight) / box.clientHeight))
  })
}

for (const vp of VIEWPORTS) {
  await page.setViewportSize(vp)
  for (const [key, url] of Object.entries(PAGES)) {
    errors = []
    const t0 = Date.now()
    await page.goto(APP + url)
    await page.waitForLoadState('networkidle', { timeout: T }).catch(() => {})
    await page.getByText('Loading…').first().waitFor({ state: 'hidden', timeout: T }).catch(() => {})
    if (key === 'dashboard') await page.locator('ul.space-y-3 > li').first().waitFor({ timeout: T }).catch(() => {})
    await page.waitForTimeout(1000)
    const shotPath = path.join(EV5, 'matrix', which, String(vp.width), `${key}.png`)
    await page.screenshot({ path: shotPath })
    const checks = [await page.evaluate(inspect)]
    const steps = await scrollSteps()
    for (let s = 1; s <= steps; s++) {
      await page.evaluate(() => {
        const b = document.querySelector('[data-nfr-scroller]')
        b.scrollTop += b.clientHeight
      })
      await page.waitForTimeout(200)
      checks.push(await page.evaluate(inspect))
    }
    const run = {
      viewport: `${vp.width}x${vp.height}`,
      page: key,
      url,
      hscroll: Math.max(...checks.map((c) => c.hscroll)),
      overflowing: [...new Set(checks.flatMap((c) => c.overflowing))],
      overlaps: [...new Set(checks.flatMap((c) => c.overlaps))],
      screensChecked: checks.length,
      controlsChecked: checks.reduce((n, c) => n + c.controls, 0),
      consoleErrors: [...errors],
      ms: Date.now() - t0,
    }
    run.pass = run.hscroll === 0 && run.overflowing.length === 0 && run.overlaps.length === 0 && run.consoleErrors.length === 0
    result.runs.push(run)
    console.log(
      `${which} ${run.viewport} ${key}: ${run.pass ? 'PASS' : 'FAIL'} hscroll=${run.hscroll} overflow=${run.overflowing.length} overlaps=${run.overlaps.length} errors=${run.consoleErrors.length}`,
    )
  }
}
result.finished = new Date().toISOString()
save(path.join(EV5, 'matrix', which, 'result.json'), result)
await browser.close()
