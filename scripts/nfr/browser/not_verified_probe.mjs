// reverify: where does the text "Not verified" render (F-12)? Usage: node not_verified_probe.mjs
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from '@playwright/test'
import { signIn, APP, EV4, save } from './lib.mjs'
const PAGES = JSON.parse(fs.readFileSync(path.join(EV4, '..', 'U', 'u1_pages.json'), 'utf8'))
const browser = await chromium.launch()
const page = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage()
await signIn(page, 'a')
const out = { browser: browser.version(), when: new Date().toISOString(), pages: {} }
for (const [name, url] of Object.entries(PAGES)) {
  if (typeof url !== 'string' || !url.startsWith('/')) continue
  await page.goto(APP + url)
  await page.waitForLoadState('networkidle', { timeout: 60000 }).catch(() => {})
  await page.waitForTimeout(800)
  out.pages[name] = await page.evaluate(() => [...document.querySelectorAll('span')].filter((e) => /^(Not verified|Verified)$/.test(e.textContent.trim()))
    .map((e) => { const b = getComputedStyle(e, '::before'); return { text: e.textContent.trim(), color: getComputedStyle(e).color, before_bg: b.backgroundColor, before_shadow: b.boxShadow, before_content: b.content } }))
}
save(path.join(EV4, 'not_verified_probe.json'), out)
for (const [k, v] of Object.entries(out.pages)) console.log(k, JSON.stringify(v.slice(0, 2)), v.length)
await browser.close()
