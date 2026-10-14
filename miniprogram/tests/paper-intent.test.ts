import assert from 'node:assert/strict'
import test from 'node:test'
import { rememberPaperIntent, bindPaperIntent, takePaperIntent, clearPaperIntent } from '../src/services/paper-intent'

test('a login intent is bound to one account and consumed only by its paper once', () => {
  rememberPaperIntent({ paperId: 'one', action: 'download', edition: 'answers' })
  bindPaperIntent('reader')
  assert.equal(takePaperIntent('two', 'reader'), null)
  assert.deepEqual(takePaperIntent('one', 'reader'), { paperId: 'one', action: 'download', edition: 'answers' })
  assert.equal(takePaperIntent('one', 'reader'), null)
  rememberPaperIntent({ paperId: 'one', action: 'favorite', edition: 'original' })
  bindPaperIntent('reader')
  bindPaperIntent('another')
  assert.equal(takePaperIntent('one', 'another'), null)
  assert.equal(takePaperIntent('one', 'reader'), null)
})

test('expired and cancelled login intents cannot replay later', context => {
  context.mock.timers.enable({ apis: ['Date'], now: 1000 })
  rememberPaperIntent({ paperId: 'one', action: 'download', edition: 'answers' })
  bindPaperIntent('reader')
  context.mock.timers.tick(10 * 60_000)
  assert.equal(takePaperIntent('one', 'reader'), null)
  rememberPaperIntent({ paperId: 'one', action: 'favorite', edition: 'original' })
  clearPaperIntent()
  bindPaperIntent('reader')
  assert.equal(takePaperIntent('one', 'reader'), null)
})
