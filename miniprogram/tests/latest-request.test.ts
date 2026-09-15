import assert from 'node:assert/strict'
import test from 'node:test'
import { createLatestRequest } from '../src/services/latest-request'

test('only the latest page request may update the view', () => {
  const requests = createLatestRequest()
  const first = requests.begin()
  const second = requests.begin()
  assert.equal(first(), false)
  assert.equal(second(), true)
})

test('hiding a page or changing the account invalidates all pending work', () => {
  const requests = createLatestRequest()
  const beforeHide = requests.begin()
  requests.invalidate()
  assert.equal(beforeHide(), false)
  const afterShow = requests.begin()
  assert.equal(afterShow(), true)
  requests.invalidate()
  assert.equal(afterShow(), false)
})

test('a follow-up summary cannot commit after a filter change', async () => {
  const requests = createLatestRequest()
  const first = requests.begin()
  let displayed = 'new filter'
  const summary = Promise.resolve('old summary').then(value => { if (first()) displayed = value })
  requests.invalidate()
  await summary
  assert.equal(displayed, 'new filter')
})
