// U1 / NFR-04 after the redesign: every status label as rendered (text, dot colour,
// text colour, background), WCAG 2.2 contrast of the word (SC 1.4.3, >= 4.5:1) and of
// the dot (SC 1.4.11, >= 3:1) against the actual background, in colour and after a
// greyscale conversion (CSS grayscale(1) matrix); greyscale screenshots of each page;
// axe-core WCAG 2.2 A/AA scan of each page. Pages: <evidence>/U/u1_pages.json.
// Usage: node labels_contrast.mjs
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from '@playwright/test'
import { AxeBuilder } from '@axe-core/playwright'
import { signIn, APP, EV4, save } from './lib.mjs'

const PAGES = JSON.parse(fs.readFileSync(path.join(EV4, '..', 'U', 'u1_pages.json'), 'utf8'))
const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } })
const page = await ctx.newPage()
await signIn(page, 'a')
const result = { browser: `chromium ${browser.version()}`, when: new Date().toISOString(), labels: [], axe: {}, shots: [] }

async function settle() {
  await page.waitForLoadState('networkidle', { timeout: 60000 }).catch(() => {})
  await page.getByText('Loading…').first().waitFor({ state: 'hidden', timeout: 60000 }).catch(() => {})
  await page.waitForTimeout(700)
}

function collect() {
  // Runs in the page.
  const parse = (c) => { const m = c.match(/[\d.]+/g); return m ? m.slice(0, 4).map(Number) : null }
  const bgOf = (el) => {
    for (let e = el; e; e = e.parentElement) {
      const c = parse(getComputedStyle(e).backgroundColor)
      if (c && (c.length < 4 || c[3] > 0)) return c.slice(0, 3)
    }
    return [255, 255, 255]
  }
  const out = []
  for (const el of document.querySelectorAll('span')) {
    const before = getComputedStyle(el, '::before')
    if (before.content === 'none' || before.content === '' || before.borderRadius === '0px') continue
    let dot = parse(before.backgroundColor)
    // reverify fix: a hollow ring dot (neutral/muted tone) has a transparent fill; take the ring colour
    if ((!dot || (dot.length === 4 && dot[3] === 0)) && before.boxShadow && before.boxShadow !== 'none') dot = (before.boxShadow.match(/rgba?\([^)]*\)/g) || []).map(parse).find((c) => c.length < 4 || c[3] > 0) || null
    if (!dot || (dot.length === 4 && dot[3] === 0)) continue
    const r = el.getBoundingClientRect()
    if (!r.width) continue
    const ctxEl = el.closest('td,li,div')
    out.push({ text: el.textContent.trim(), aria: el.getAttribute('aria-label'), text_rgb: parse(getComputedStyle(el).color).slice(0, 3),
               dot_rgb: dot.slice(0, 3), bg_rgb: bgOf(el), font_px: parseFloat(getComputedStyle(el).fontSize),
               weight: getComputedStyle(el).fontWeight, context: (ctxEl?.textContent || '').trim().slice(0, 60) })
  }
  return out
}

for (const [name, url] of Object.entries(PAGES)) {
  const tabs = name === 'dashboard' ? ['Missing', 'Expired', 'Expiring soon', 'Expiry not stated', 'Waiting for review', 'Starting soon', 'In order'] : [null]
  await page.goto(APP + url)
  await settle()
  for (const tab of tabs) {
    if (tab) { await page.getByRole('tab', { name: new RegExp('^' + tab) }).click(); await settle() }
    const key = tab ? `${name}-${tab.toLowerCase().replace(/ /g, '-')}` : name
    for (const l of await page.evaluate(collect)) result.labels.push({ page: key, ...l })
    await page.evaluate(() => (document.documentElement.style.filter = 'grayscale(1)'))
    const f = path.join(EV4, 'greyscale', `${key}.png`)
    fs.mkdirSync(path.dirname(f), { recursive: true })
    await page.screenshot({ path: f, fullPage: true })
    await page.evaluate(() => (document.documentElement.style.filter = ''))
    result.shots.push(f)
    if (!tab || tab === 'Missing') {
      const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()
      result.axe[key] = axe.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length, sample: v.nodes[0]?.target }))
    }
  }
}
save(path.join(EV4, 'labels_raw.json'), result)
console.log('labels', result.labels.length, 'pages', Object.keys(PAGES).length, 'axe pages', Object.keys(result.axe).length)
await browser.close()
