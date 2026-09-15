import assert from 'node:assert/strict'
import test from 'node:test'
import { answerText, fileSize, formatDate, richNodes, sectionNames } from '../src/content'
import type { Question } from '../src/types'

test('rich text preserves reading semantics without resource/style/event attributes', () => {
  const nodes = richNodes('<div onclick="bad()"><b>12</b> &lt; 20<sub>2</sub><img src="https://bad.invalid/a" onerror="bad()"><script>alert(1)</script><span style="position:fixed">文字</span></div>')
  const output = JSON.stringify(nodes)
  assert.match(output, /"name":"b"/)
  assert.match(output, /"name":"sub"/)
  assert.match(output, /< 20/)
  assert.doesNotMatch(output, /onclick|onerror|https|alert|position|script|img/)
})
test('plain fallback is always a text node', () => {
  assert.deepEqual(richNodes(undefined, '<img onerror=alert(1)>'), [{ type: 'text', text: '<img onerror=alert(1)>' }])
})
test('malformed HTML and excessive nesting stay bounded', () => {
  assert.ok(richNodes('<p><b>hello<p>world').length)
  assert.ok(JSON.stringify(richNodes('<div>'.repeat(300) + 'x' + '</div>'.repeat(300))).length < 2000)
})
test('answers retain zero indexes, arithmetic zero and match pair numbering', () => {
  assert.equal(answerText({ options: ['20', '30'], answer: 0 }), 'A. 20')
  assert.equal(answerText({ answer: 0 }), '0')
  assert.equal(answerText({ answer: [[0, 1], [1, 0]] }), '1 → 2，2 → 1')
  assert.equal(answerText({}), '暂无答案')
})
test('dates and file sizes are stable display values', () => {
  assert.equal(formatDate(new Date(2026, 8, 14).getTime() / 1000), '2026.09.14')
  assert.equal(fileSize(1024 * 1024), '1.0 MB')
  assert.equal(fileSize(0), '0 KB')
  assert.equal(sectionNames.reading, '阅读理解')
})

test('an older or malformed answer array does not crash the reading page', () => {
  const question = JSON.parse('{"answer":[1,2,null]}') as Question
  assert.equal(answerText(question), '1，2，')
})
