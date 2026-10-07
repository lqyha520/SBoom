import test from 'node:test'
import assert from 'node:assert/strict'
import { safeDestination, loginUrl, routeFromPage, shareCard, catalogShare, HOME } from '../src/services/return-route'

test('login preserves a shared paper or topic and rebuilds only public parameters', () => {
  for (const kind of ['paper', 'topic']) {
    const target = `/pages/${kind}/index?id=abc_123-45`
    assert.equal(safeDestination(target), target)
    assert.equal(decodeURIComponent(loginUrl(target).split('returnTo=')[1]!), target)
    assert.equal(routeFromPage({ route: `pages/${kind}/index`, options: { id: 'abc_123-45', scope: 'catalog' } }), target)
  }
  const target = '/subpages/requests/index?title=' + encodeURIComponent('分数应用题') + '&grade=' + encodeURIComponent('六年级')
  assert.equal(safeDestination(target), target)
  assert.equal(routeFromPage({ route: 'subpages/requests/index', $page: { options: { title: '分数应用题', grade: '六年级' } } }), target)
})

test('external redirects, private routes and ambiguous identifiers fail closed', () => {
  for (const value of [undefined, null, {}, '', 'https://example.com', '//example.com', '/admin/', '/api/v1/library/papers/x', '/pages/private/index', '/pages/login/index', '/pages/paper/index', '/pages/paper/index?id=a&id=b', '/pages/paper/index?id=%2Fadmin', '/pages/paper/index?id=..', '/pages/paper/index?id=%00abc', '/pages/paper/index?id=%', '/pages/paper/index?id=a#private', '/pages/paper/index?id=a&scope=private', '/subpages/privacy/index?kind=unknown', '/subpages/support/index?kind=refund', '/pages/home/index?next=https://example.com', '/pages/paper\\index?id=x']) assert.equal(safeDestination(value), HOME, String(value))
})

test('inbox destinations allow owned-record identifiers without user-supplied URLs', () => {
  for (const route of ['orders', 'requests', 'support']) assert.equal(safeDestination(`/pages/${route}/index?id=record-123`), `/subpages/${route}/index?id=record-123`)
  assert.equal(safeDestination('/subpages/closure/index'), '/subpages/closure/index')
  assert.equal(safeDestination('/subpages/orders/index?id=' + 'a'.repeat(65)), HOME)
})

test('share cards preserve public destinations and use the native current-page screenshot', () => {
  const card = shareCard('paper', 'paper-1', '  单元练习  ')
  assert.equal(card.title, '单元练习')
  assert.equal(card.path, '/pages/paper/index?id=paper-1')
  assert.deepEqual(Object.keys(card).sort(), ['path', 'title'])
  assert.equal(shareCard('paper', '../private').path, HOME)
  assert.ok(!JSON.stringify(card).includes('assets/'))
})

test('home, topic, list buttons and list menus never override the native screenshot', () => {
  const topic = shareCard('topic', 'topic-1', '单元复习')
  const cases = [
    shareCard('home'),
    topic,
    shareCard('paper', '../private'),
    catalogShare({ target: { dataset: { paperId: 'paper-1', paperTitle: '看图列式' } } }),
    catalogShare({}),
    catalogShare({}, topic),
    catalogShare({ target: { dataset: { paperId: '../private' } } }, topic),
  ]
  for (const card of cases) assert.deepEqual(Object.keys(card).sort(), ['path', 'title'])
  assert.equal(cases[3]!.path, '/pages/paper/index?id=paper-1')
  assert.equal(cases[3]!.title, '看图列式')
  assert.equal(cases[5]!.path, '/pages/topic/index?id=topic-1')
})

test('login still returns to the page when the platform keeps the target encoded', () => {
  // 微信小程序 onLoad 不做 URL 解码：returnTo 到手时仍是 %2F 开头，必须还能认出来
  const targets = ['/pages/paper/index?id=abc_123-45', '/pages/library/index?grade=' + encodeURIComponent('三年级'),
    '/subpages/requests/index?title=' + encodeURIComponent('分数应用题') + '&grade=' + encodeURIComponent('六年级')]
  for (const target of targets) assert.equal(safeDestination(encodeURIComponent(target)), target, target)
  // 页面栈里的中文参数同样未解码，重新编码前要先归一化，避免二次编码
  assert.equal(routeFromPage({ route: 'subpages/requests/index', options: { title: encodeURIComponent('分数应用题') } }),
    '/subpages/requests/index?title=' + encodeURIComponent('分数应用题'))
  // 编码形式也不是后门：解码后仍走完整校验
  assert.equal(safeDestination(encodeURIComponent('/pages/paper/index')), HOME)
  assert.equal(safeDestination(encodeURIComponent('/pages/paper/index?id=..')), HOME)
  assert.equal(safeDestination(encodeURIComponent('/pages/private/index')), HOME)
})
