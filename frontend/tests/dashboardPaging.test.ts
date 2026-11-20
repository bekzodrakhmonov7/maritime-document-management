import { test } from 'node:test'
import assert from 'node:assert/strict'

import { filterParams, nextOffset, pageItems, pageParams } from '../src/lib/dashboardPaging.ts'

const NO_FILTERS = {
  name: '',
  positionIds: [],
  vesselIds: [],
  ashore: false,
  documentTypeIds: [],
  showInactive: false,
}

function page(offset: number, limit: number, total: number, groups: unknown[] = []) {
  return { queue: 'expired', offset, limit, total, groups, assignments: [] }
}

test('a page asks for its queue and keeps every filter', () => {
  const filters = filterParams({
    ...NO_FILTERS,
    name: ' anna ',
    vesselIds: [3, 4],
    ashore: true,
    showInactive: true,
  })
  assert.equal(
    pageParams(filters, 'expired', 0),
    'name=anna&vessel_id=3&vessel_id=4&ashore=true&show_inactive=true&queue=expired',
  )
  assert.equal(pageParams('', 'starting_soon', 100), 'queue=starting_soon&offset=100')
})

test('the next page starts after the last one, until the total is reached', () => {
  assert.equal(nextOffset(page(0, 50, 120)), 50)
  assert.equal(nextOffset(page(50, 50, 120)), 100)
  assert.equal(nextOffset(page(100, 50, 120)), undefined)
  assert.equal(nextOffset(page(0, 50, 50)), undefined)
  assert.equal(nextOffset(page(0, 50, 0)), undefined)
})

test('the pages read so far are shown in queue order', () => {
  const pages = [page(0, 2, 3, ['a', 'b']), page(2, 2, 3, ['c'])]
  assert.deepEqual(pageItems(pages, (p) => p.groups), ['a', 'b', 'c'])
})
