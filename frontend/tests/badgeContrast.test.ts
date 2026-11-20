// NFR-04: every status badge's text is >= 4.5:1 against its badge background,
// in colour and after the CSS grayscale(1) filter. Colours are resolved from
// the classes the badges actually use (src/lib/badgeTone.ts) to the values in
// src/index.css, so a change to either is checked here.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import { BADGE_TONE } from '../src/lib/badgeTone.ts'

const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')

type RGB = [number, number, number]

function token(name: string): RGB {
  const m = css.match(new RegExp(`--color-${name}:[ \\t]*#([0-9a-fA-F]{6})[ \\t]*;`))
  assert.ok(m, `--color-${name} is defined as a 6-digit hex colour in index.css`)
  const hex = m[1]
  return [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16)) as RGB
}

/** The text and background colours of a tone's classes (`text-x`, `bg-x`). */
function colours(classes: string): { text: RGB; bg: RGB } {
  const parts = classes.split(/\s+/)
  const text = parts.find((c) => c.startsWith('text-'))
  const bg = parts.find((c) => c.startsWith('bg-'))
  assert.ok(text && bg, `"${classes}" names a text and a background colour`)
  assert.ok(!text.includes('/') && !bg.includes('/'), 'badge colours are opaque')
  return { text: token(text.slice(5)), bg: token(bg.slice(3)) }
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

for (const [tone, classes] of Object.entries(BADGE_TONE)) {
  test(`badge tone "${tone}" is at least 4.5:1 in colour and in greyscale`, () => {
    const { text, bg } = colours(classes)
    const inColour = contrast(text, bg)
    const inGrey = contrast(grayscale(text), grayscale(bg))
    assert.ok(inColour >= 4.5, `${tone}: ${inColour.toFixed(2)}:1 in colour`)
    assert.ok(inGrey >= 4.5, `${tone}: ${inGrey.toFixed(2)}:1 in greyscale`)
  })
}
