import { test } from 'node:test'
import assert from 'node:assert/strict'

import { isOwnUpload, missingUploadPath, preselectedTypeId } from '../src/lib/missingUpload.ts'

test('a Missing entry links to the seafarer record with its Document Type', () => {
  const path = missingUploadPath(7, 12)
  assert.equal(path, '/seafarers/7?upload=12')
  assert.equal(preselectedTypeId(path.split('?')[1]), 12)
})

test('only a positive whole Document Type id is preselected', () => {
  assert.equal(preselectedTypeId(''), null)
  assert.equal(preselectedTypeId('upload='), null)
  assert.equal(preselectedTypeId('upload=abc'), null)
  assert.equal(preselectedTypeId('upload=0'), null)
  assert.equal(preselectedTypeId('upload=-3'), null)
  assert.equal(preselectedTypeId('upload=1.5'), null)
  assert.equal(preselectedTypeId('?upload=4'), 4)
})

test('the uploader is never offered the Review (FR-11)', () => {
  assert.equal(isOwnUpload('a', 'a'), true)
  assert.equal(isOwnUpload('a', 'b'), false)
  assert.equal(isOwnUpload(undefined, 'a'), false)
  assert.equal(isOwnUpload('a', undefined), false)
  assert.equal(isOwnUpload(null, null), false)
})
