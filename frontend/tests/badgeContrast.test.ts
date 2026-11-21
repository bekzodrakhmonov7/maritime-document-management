// NFR-04: every status's word is >= 4.5:1 and its dot >= 3:1 against the grounds
// it sits on, in colour and after the CSS grayscale(1) filter. Colours are resolved from
// the classes the badges actually use (src/lib/badgeTone.ts) to the values in
// src/index.css, so a change to either is checked here.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import { BADGE_TONE, DOT_COLOUR } from '../src/lib/badgeTone.ts'

const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')

type RGB = [number, number, number]

function token(name: string): RGB {
  const m = css.match(new RegExp(`--color-${name}:[ \\t]*#([0-9a-fA-F]{6})[ \\t]*;`))
  assert.ok(m, `--color-${name} is defined as a 6-digit hex colour in index.css`)
  const hex = m[1]
  return [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16)) as RGB
}

/** The word colour of a tone: its last `text-<colour>` class (later wins). */
function wordColour(classes: string): RGB {
  const texts = classes.split(/\s+/).filter((c) => /^text-(ink|warning|danger)/.test(c))
  assert.ok(texts.length > 0, `"${classes}" names a text colour`)
  return token(texts[texts.length - 1].slice(5))
}

const channel = (v: number) => {
  const s = v / 255
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
}
const luminance = ([r, g, b]: RGB) => 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

/** WCAG 2 contrast ratio. */
export function contrast(a: RGB, b: RGB): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

/** CSS grayscale(1) as browsers apply it: the luminance matrix on sRGB values. */
export function grayscale([r, g, b]: RGB): RGB {
  const v = Math.round(0.2126 * r + 0.7152 * g + 0.0722 * b)
  return [v, v, v]
}

test('the contrast formula matches known WCAG values', () => {
  assert.equal(contrast([0, 0, 0], [255, 255, 255]).toFixed(1), '21.0')
  assert.equal(contrast([118, 118, 118], [255, 255, 255]).toFixed(2), '4.54')
})

// Statuses sit on the page (canvas) and on the frame (surface, table headers).
const GROUNDS = ['canvas', 'surface', 'surface-active'] as const

for (const [tone, classes] of Object.entries(BADGE_TONE)) {
  test(`status tone "${tone}": word >= 4.5:1 and dot >= 3:1 on every ground, in colour and greyscale`, () => {
    const word = wordColour(classes)
    const dot = token(DOT_COLOUR[tone as keyof typeof DOT_COLOUR])
    for (const g of GROUNDS) {
      const ground = token(g)
      for (const [name, fg, min] of [['word', word, 4.5], ['dot', dot, 3]] as const) {
        const inColour = contrast(fg, ground)
        const inGrey = contrast(grayscale(fg), grayscale(ground))
        assert.ok(inColour >= min, `${tone} ${name} on ${g}: ${inColour.toFixed(2)}:1 in colour`)
        assert.ok(inGrey >= min, `${tone} ${name} on ${g}: ${inGrey.toFixed(2)}:1 in greyscale`)
      }
    }
  })
}

test('body text, danger and warning text read at 4.5:1 on every ground', () => {
  for (const fg of ['ink', 'ink-muted', 'ink-faint', 'danger', 'warning']) {
    for (const g of GROUNDS) {
      const r = contrast(token(fg), token(g))
      assert.ok(r >= 4.5, `${fg} on ${g}: ${r.toFixed(2)}:1`)
    }
  }
  const r = contrast(token('on-accent'), token('accent'))
  assert.ok(r >= 4.5, `on-accent on accent: ${r.toFixed(2)}:1`)
})
