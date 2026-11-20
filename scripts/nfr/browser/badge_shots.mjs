// NFR-04: one cropped screenshot per status label, in colour and in greyscale,
// for the contrast comparison in badge_contrast.py.
import path from 'node:path'
import { chromium } from '@playwright/test'
import { signIn, APP, EV4 } from './lib.mjs'
const T = 90000
const out = path.join(EV4, 'badges')
const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2 })
const page = await ctx.newPage()
await signIn(page, 'a')
const pages = ['/assignments/5/readiness', '/assignments/119/readiness', '/seafarers/7', '/documents/16', '/documents/2851', '/']
const seen = new Set()
for (const url of pages) {
  await page.goto(APP + url)
  await page.waitForLoadState('networkidle', { timeout: T }).catch(() => {})
  if (url === '/') {
    await page.locator('ul.space-y-3 > li').first().waitFor({ timeout: T })
    await page.getByRole('tab', { name: /^Expired/ }).click()
    await page.waitForTimeout(800)
  } else await page.waitForTimeout(1500)
  const els = await page.locator('[aria-label^="Expiry status: "], [aria-label^="Coverage: "], span.inline-flex.items-center.gap-1').all()
  for (const el of els) {
    const aria = await el.getAttribute('aria-label')
    const key = (aria ?? 'Tag: ' + (await el.innerText()).trim()).replace(/[^A-Za-z0-9]+/g, '_')
    if (seen.has(key) || !(await el.isVisible())) continue
    seen.add(key)
    await el.scrollIntoViewIfNeeded()
    await page.evaluate(() => (document.documentElement.style.filter = ''))
    await el.screenshot({ path: path.join(out, `${key}__colour.png`) })
    await page.evaluate(() => (document.documentElement.style.filter = 'grayscale(1)'))
    await el.screenshot({ path: path.join(out, `${key}__grey.png`) })
  }
}
console.log([...seen].join('\n'))
await browser.close()
