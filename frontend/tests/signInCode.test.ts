import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  RESEND_WAIT_SECONDS,
  codeErrorMessage,
  groupSecret,
  qrCodeSource,
  isCompleteCode,
  normaliseCode,
  passwordProblem,
  secondsUntilResend,
} from '../src/lib/signInCode.ts'

test('a typed or pasted code keeps only its first 6 digits', () => {
  assert.equal(normaliseCode('123 456'), '123456')
  assert.equal(normaliseCode('12-34-56-78'), '123456')
  assert.equal(normaliseCode('abc'), '')
})

test('only 6 digits make a complete code', () => {
  assert.equal(isCompleteCode('123456'), true)
  assert.equal(isCompleteCode('12345'), false)
  assert.equal(isCompleteCode('12345a'), false)
  assert.equal(isCompleteCode('1234567'), false)
})

test('a new code can be asked for 60 seconds after the last send', () => {
  assert.equal(RESEND_WAIT_SECONDS, 60)
  const sentAt = 1_000_000
  assert.equal(secondsUntilResend(sentAt, sentAt), 60)
  assert.equal(secondsUntilResend(sentAt, sentAt + 100), 60)
  assert.equal(secondsUntilResend(sentAt, sentAt + 1_000), 59)
  assert.equal(secondsUntilResend(sentAt, sentAt + 59_001), 1)
  assert.equal(secondsUntilResend(sentAt, sentAt + 60_000), 0)
  assert.equal(secondsUntilResend(sentAt, sentAt + 120_000), 0)
})

test('nothing sent yet means no wait', () => {
  assert.equal(secondsUntilResend(null, 5), 0)
})

test('a wrong or expired code says so', () => {
  for (const code of ['otp_expired', 'invalid_credentials', 'otp_invalid']) {
    assert.match(codeErrorMessage({ status: 403, code, message: 'x' }), /wrong or has expired/)
  }
})

test('too many attempts asks the person to wait', () => {
  assert.match(
    codeErrorMessage({ status: 429, code: 'over_request_rate_limit', message: 'x' }),
    /Too many attempts/,
  )
})

test('any other refusal shows the API message', () => {
  assert.equal(
    codeErrorMessage({ status: 503, code: 'auth_unavailable', message: 'Sign-in is unavailable.' }),
    'Sign-in is unavailable.',
  )
  assert.equal(codeErrorMessage(new Error('Failed to fetch')), 'Failed to fetch')
})

test('a new password is 12 to 72 characters, typed the same twice', () => {
  assert.match(passwordProblem('short1', 'short1') ?? '', /at least 12/)
  assert.match(passwordProblem('eleven-char', 'eleven-char') ?? '', /at least 12/)
  assert.equal(passwordProblem('twelve-chars', 'twelve-chars'), null)
  assert.match(passwordProblem('x'.repeat(73), 'x'.repeat(73)) ?? '', /at most 72/)
  assert.match(passwordProblem('long-enough-1', 'long-enough-2') ?? '', /not the same/)
  assert.equal(passwordProblem('long-enough-1', 'long-enough-1'), null)
})

test('a wrong authenticator code says so, without offering an e-mail', () => {
  const message = codeErrorMessage({ status: 403, code: 'totp_invalid', message: 'x' })
  assert.match(message, /authenticator/)
  assert.doesNotMatch(message, /send a new code/)
})

test('the QR code SVG becomes an image source', () => {
  const src = qrCodeSource('<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>')
  assert.ok(src.startsWith('data:image/svg+xml;charset=utf-8,'))
  assert.equal(decodeURIComponent(src.split(',')[1]), '<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>')
})

test('the key is shown in groups of four', () => {
  assert.equal(groupSecret('A535CNTD555SWDNGVB3NUO3BEQYJ6QXB'), 'A535 CNTD 555S WDNG VB3N UO3B EQYJ 6QXB')
  assert.equal(groupSecret('ABCDE'), 'ABCD E')
  assert.equal(groupSecret(''), '')
})
