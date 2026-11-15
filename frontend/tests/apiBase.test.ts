import { test } from 'node:test'
import assert from 'node:assert/strict'

import { resolveApiBase } from '../src/lib/apiBase.ts'

test('an unset API base means the local API on port 8000', () => {
  assert.equal(resolveApiBase(undefined), 'http://localhost:8000')
})

test('an explicitly empty API base means the page’s own origin', () => {
  assert.equal(resolveApiBase(''), '')
})

test('a set API base is used as given', () => {
  assert.equal(resolveApiBase('https://api.example.test'), 'https://api.example.test')
})
