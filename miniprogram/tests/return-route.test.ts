import test from 'node:test'
import assert from 'node:assert/strict'
import { safeDestination, loginUrl, routeFromPage, shareCard, HOME } from '../src/services/return-route'

test('login preserves a shared paper or topic and rebuilds only public parameters', () => {
  for (const kind of ['paper', 'topic']) {
    const target = `/pages/${kind}/index?id=abc_123-45`
    assert.equal(safeDestination(target), target)
    assert.equal(decodeURIComponent(loginUrl(target).split('returnTo=')[1]!), target)
    assert.equal(routeFromPage({ route: `pages/${kind}/index`, options: { id: 'abc_123-45', scope: 'catalog' } }), target)
  }
  const target = '/pages/requests/index?title=' + encodeURIComponent('分数应用题') + '&grade=' + encodeURIComponent('六年级')
  assert.equal(safeDestination(target), target)
  assert.equal(routeFromPage({ route: 'pages/requests/index', $page: { options: { title: '分数应用题', grade: '六年级' } } }), target)
})

test('external redirects, private routes and ambiguous identifiers fail closed', () => {
  for (const value of [undefined, null, {}, '', 'https://example.com', '//example.com', '/admin/', '/api/v1/library/papers/x', '/pages/private/index', '/pages/login/index', '/pages/paper/index', '/pages/paper/index?id=a&id=b', '/pages/paper/index?id=%2Fadmin', '/pages/paper/index?id=..', '/pages/paper/index?id=%00abc', '/pages/paper/index?id=%', '/pages/paper/index?id=a#private', '/pages/paper/index?id=a&scope=private', '/pages/privacy/index?kind=unknown', '/pages/support/index?kind=refund', '/pages/home/index?next=https://example.com', '/pages/paper\\index?id=x']) assert.equal(safeDestination(value), HOME, String(value))
})

test('inbox destinations allow owned-record identifiers without user-supplied URLs', () => {
  for (const route of ['orders', 'requests', 'support']) assert.equal(safeDestination(`/pages/${route}/index?id=record-123`), `/pages/${route}/index?id=record-123`)
  assert.equal(safeDestination('/pages/closure/index'), '/pages/closure/index')
  assert.equal(safeDestination('/pages/orders/index?id=' + 'a'.repeat(65)), HOME)
})

test('share cards contain static public artwork and a public destination', () => {
  const card = shareCard('paper', 'paper-1', '  单元练习  ')
  assert.equal(card.title, '单元练习')
  assert.equal(card.path, '/pages/paper/index?id=paper-1')
  assert.equal(card.imageUrl, '/static/banners/study.jpg')
  assert.equal(shareCard('paper', '../private').path, HOME)
  assert.ok(!JSON.stringify(card).includes('assets/'))
})
