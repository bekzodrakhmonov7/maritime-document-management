import { test } from 'node:test'
import assert from 'node:assert/strict'

import { isNotFound, retryUnlessClientError } from '../src/lib/retry.ts'

test('a 4xx answer is never retried', () => {
  for (const status of [400, 403, 404, 422]) {
    assert.equal(retryUnlessClientError(0, { status }), false)
  }
})

test('other failures are retried up to three times', () => {
  assert.equal(retryUnlessClientError(0, { status: 503 }), true)
  assert.equal(retryUnlessClientError(2, new Error('network')), true)
  assert.equal(retryUnlessClientError(3, { status: 500 }), false)
})

test('only a 404 is not found', () => {
  assert.equal(isNotFound({ status: 404 }), true)
  assert.equal(isNotFound({ status: 403 }), false)
  assert.equal(isNotFound(null), false)
})
