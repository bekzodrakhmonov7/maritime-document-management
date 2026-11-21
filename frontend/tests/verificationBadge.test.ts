// F-12: a Document that is not Verified says "Not verified" (grey, no warning
// colour) wherever the Verified shield can appear; a Verified one keeps the shield.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { VerificationBadge } from '../src/components/verificationBadge.ts'

const render = (verified: boolean) => renderToStaticMarkup(createElement(VerificationBadge, { verified }))
const text = (html: string) => html.replace(/<[^>]+>/g, '')

test('a Document that is not Verified says "Not verified" in grey', () => {
  const html = render(false)
  assert.equal(text(html), 'Not verified')
  assert.match(html, /text-ink-muted/)
  assert.doesNotMatch(html, /warning|danger/)
})

test('a Verified Document keeps the Verified shield', () => {
  const html = render(true)
  assert.equal(text(html), 'Verified')
  assert.match(html, /title="The issuing authority confirmed the current version"/)
})
