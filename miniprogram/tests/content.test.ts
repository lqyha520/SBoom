import assert from 'node:assert/strict'
import test from 'node:test'
import { fileSize, formatDate } from '../src/content'

test('dates and file sizes are stable display values', () => {
  assert.equal(formatDate(new Date(2026, 8, 14).getTime() / 1000), '2026.09.14')
  assert.equal(fileSize(1024 * 1024), '1.0 MB')
  assert.equal(fileSize(0), '0 KB')
})
