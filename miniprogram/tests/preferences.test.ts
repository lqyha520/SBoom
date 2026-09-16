import assert from 'node:assert/strict'
import test from 'node:test'
import { cleanPreferences, readPreferences, rememberSearch, writePreferences } from '../src/services/preferences'

test('search history is recent-first, deduplicated and bounded without mutating previous values', () => {
  const original = cleanPreferences({ grade: '三年级', subject: '数学', history: ['加法', '除法'] })
  const next = rememberSearch(original, ' 除法 ')
  assert.deepEqual(next.history, ['除法', '加法'])
  assert.deepEqual(original.history, ['加法', '除法'])
  assert.equal(cleanPreferences({ history: Array.from({ length: 100 }, (_, i) => String(i)) }).history.length, 12)
  assert.equal(rememberSearch(original, 'x'.repeat(500)).history[0]?.length, 120)
})

test('malformed stored preferences do not crash or inject non-text history', () => {
  assert.deepEqual(cleanPreferences(null), { grade: '', subject: '', history: [] })
  assert.deepEqual(cleanPreferences({ grade: [], subject: false, history: [null, {}, ' ', '有效记录'] }), { grade: '', subject: '', history: ['有效记录'] })
})

test('preferences are isolated by account and tolerate unavailable storage', () => {
  const storage = new Map<string, unknown>()
  const target = globalThis as typeof globalThis & { uni?: unknown }
  const before = target.uni
  target.uni = { getStorageSync: (key: string) => storage.get(key), setStorageSync: (key: string, value: unknown) => storage.set(key, value) }
  try {
    writePreferences('reader-one', { grade: '三年级', subject: '数学', history: ['乘法'] })
    assert.equal(readPreferences('reader-two').history.length, 0)
    assert.equal(readPreferences('reader-one').grade, '三年级')
    target.uni = { getStorageSync() { throw Error('storage unavailable') }, setStorageSync() { throw Error('storage unavailable') } }
    assert.deepEqual(readPreferences('reader-one'), cleanPreferences(null))
    assert.doesNotThrow(() => writePreferences('reader-one', cleanPreferences(null)))
  } finally { target.uni = before }
})
