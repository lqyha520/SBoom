import test from 'node:test'
import assert from 'node:assert/strict'
import { beginReferralRegistration, bindReferralUser, cancelReferralLanding, captureReferral, configureReferralTracking, referralPayload, referralSharePath, takeReferralLanding } from '../src/services/referral'
import { createLatestRequest } from '../src/services/latest-request'
import { invitationShareCard, shareCard, shareTimeline } from '../src/services/return-route'

const storage = new Map<string, unknown>()
Object.assign(globalThis, { uni: { getStorageSync: (key: string) => storage.get(key), setStorageSync: (key: string, value: unknown) => storage.set(key, value), removeStorageSync: (key: string) => storage.delete(key) } })
const a = 'a_' + 'a'.repeat(20), b = 'a_' + 'b'.repeat(20), u = 'u_' + 'c'.repeat(20)

test('扫码入口在注册前保留首次来源，后续分享不覆盖；登录后分享自己的码', () => {
  bindReferralUser(null)
  captureReferral({ query: { scene: encodeURIComponent(a) } })
  captureReferral({ query: { ref: b } })
  assert.deepEqual(referralPayload(), { referral_code: a })
  assert.equal(referralSharePath('/pages/home/index'), '/pages/home/index?ref=' + a)
  bindReferralUser({ referral_code: u })
  assert.deepEqual(referralPayload(), {})
  captureReferral({ query: { ref: b } })
  assert.deepEqual(referralPayload(), {})
  assert.equal(shareCard('paper', 'paper-1').path, '/pages/paper/index?id=paper-1&ref=' + u)
  assert.equal(shareTimeline(shareCard('paper', 'paper-1')).query, 'id=paper-1&ref=' + u)
  bindReferralUser(null)
  assert.equal(shareCard('home').path, '/pages/home/index')
})

test('无效入口不污染推广关系，过期来源清除，切换账号不残留原邀请人', () => {
  bindReferralUser(null)
  captureReferral({ query: { scene: '%bad', ref: '../admin' } })
  assert.deepEqual(referralPayload(), {})
  storage.set('lc_referral_entry', { code: a, at: Date.now() - 8 * 86400 * 1000 })
  assert.deepEqual(referralPayload(), {})
  captureReferral({ query: { ref: b } })
  assert.deepEqual(referralPayload(), { referral_code: b })
  bindReferralUser({ referral_code: u })
  bindReferralUser({})
  assert.equal(shareCard('home').path, '/pages/home/index')
  bindReferralUser(null)
})

test('邀请好友使用首页封面和首页入口，保留本人邀请码且不沿用其他邀请人', () => {
  bindReferralUser(null)
  captureReferral({ query: { ref: a } })
  bindReferralUser({ referral_code: u })
  const card = invitationShareCard()
  assert.equal(card.path, '/pages/home/index?ref=' + u)
  assert.equal(card.imageUrl, '/static/share/home.jpg')
  assert.ok(!JSON.stringify(card).includes('/pages/account/'))
  bindReferralUser({})
  assert.equal(invitationShareCard().path, '/pages/home/index')
  assert.equal(invitationShareCard().imageUrl, card.imageUrl)
  bindReferralUser(null)
})

test('本地存储不可用时仍可完成扫码注册来源传递', () => {
  bindReferralUser(null)
  const previous = uni
  Object.assign(globalThis, { uni: { getStorageSync() { throw Error('unavailable') }, setStorageSync() { throw Error('unavailable') }, removeStorageSync() { throw Error('unavailable') } } })
  captureReferral({ query: { ref: a } })
  assert.deepEqual(referralPayload(), { referral_code: a })
  bindReferralUser({ referral_code: u })
  assert.equal(shareCard('home').path, '/pages/home/index?ref=' + u)
  bindReferralUser(null)
  Object.assign(globalThis, { uni: previous })
})

test('冷启动发现旧登录凭证过期时保留本次扫码入口，主动退出则清理', () => {
  bindReferralUser(null)
  captureReferral({ query: { ref: a } })
  bindReferralUser(null, true)
  assert.deepEqual(referralPayload(), { referral_code: a })
  bindReferralUser(null)
  assert.deepEqual(referralPayload(), {})
})

test('重复打开使用同一访问编号，首次归属与当前扫码落地独立，旧响应不覆盖新页面', async () => {
  bindReferralUser(null)
  const calls: { code: string; key: string; resolve: (value: any) => void }[] = []
  configureReferralTracking({ enter: (code, key) => new Promise(resolve => calls.push({ code, key, resolve })), start: async () => {} })
  captureReferral({ query: { ref: a } })
  captureReferral({ query: { ref: a } })
  assert.equal(calls.length, 1)
  captureReferral({ query: { ref: b } })
  calls[1]!.resolve({ visit_id: '2'.repeat(32), destination: '/pages/topic/index?id=new-topic', tracked: true })
  assert.equal(await takeReferralLanding(), '/pages/topic/index?id=new-topic')
  calls[0]!.resolve({ visit_id: '1'.repeat(32), destination: '/pages/paper/index?id=old-paper', tracked: true })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(await takeReferralLanding(), '')
  assert.deepEqual(referralPayload(), { referral_code: a, referral_visit_id: '1'.repeat(32) })
  bindReferralUser({ referral_code: u })
  captureReferral({ query: { ref: a } })
  assert.equal(calls[2]!.key, calls[0]!.key)
  calls[2]!.resolve({ visit_id: '1'.repeat(32), destination: '/pages/home/index', tracked: true })
  await takeReferralLanding()
  configureReferralTracking(null); bindReferralUser(null)
})

test('恢复已有登录保留扫码落地，直接分享资料不在回首页时误跳转', async () => {
  bindReferralUser(null)
  configureReferralTracking({ enter: async () => ({ visit_id: '3'.repeat(32), destination: '/pages/paper/index?id=campaign-paper', tracked: true }), start: async () => {} })
  captureReferral({ query: { ref: a } })
  bindReferralUser({ referral_code: u }, false, true)
  assert.equal(await takeReferralLanding(), '/pages/paper/index?id=campaign-paper')
  assert.deepEqual(referralPayload(), {})
  bindReferralUser(null)
  captureReferral({ path: 'pages/paper/index', query: { ref: b, id: 'shared-paper' } })
  assert.equal(await takeReferralLanding(), '')
  configureReferralTracking(null); bindReferralUser(null)
})

test('失败的追踪可以重试，开始注册包含有效访问编号，非法落地不跳转', async () => {
  bindReferralUser(null)
  const c = 'a_' + 'd'.repeat(20), started: string[] = [], keys: string[] = []
  configureReferralTracking({ enter: async (_code, key) => {
    keys.push(key)
    if (keys.length === 1) throw Error('offline')
    return { visit_id: '4'.repeat(32), destination: 'https://untrusted.example/', tracked: true }
  }, start: async id => { started.push(id) } })
  captureReferral({ query: { ref: c } }); await takeReferralLanding()
  await beginReferralRegistration()
  assert.equal(keys[0], keys[1])
  assert.deepEqual(started, ['4'.repeat(32)])
  assert.deepEqual(referralPayload(), { referral_code: c, referral_visit_id: '4'.repeat(32) })
  assert.equal(await takeReferralLanding(), '')
  configureReferralTracking(null); bindReferralUser(null)
})

test('推广落地等待超时后不再跳转，统计响应仍保留注册来源', async () => {
  bindReferralUser(null)
  let finish!: (value: any) => void
  configureReferralTracking({ enter: () => new Promise(resolve => { finish = resolve }), start: async () => {} })
  try {
    captureReferral({ path: 'pages/home/index', query: { ref: a } })
    assert.equal(await takeReferralLanding({ timeoutMs: 10 }), '')
    finish({ visit_id: '5'.repeat(32), destination: '/pages/paper/index?id=late', tracked: true })
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(await takeReferralLanding(), '')
    assert.equal(referralPayload().referral_visit_id, '5'.repeat(32))
  } finally { configureReferralTracking(null); bindReferralUser(null) }
})
test('用户开始浏览或离开首页立即取消跳转，不取消推广归属', async () => {
  for (const cancelWithScope of [false, true]) {
    bindReferralUser(null)
    let finish!: (value: any) => void
    configureReferralTracking({ enter: () => new Promise(resolve => { finish = resolve }), start: async () => {} })
    try {
      captureReferral({ query: { ref: b } })
      const scope = createLatestRequest(), pending = takeReferralLanding({ scope: scope.begin() })
      if (cancelWithScope) scope.invalidate()
      else { cancelReferralLanding(); scope.invalidate() }
      assert.equal(await pending, '')
      finish({ visit_id: '6'.repeat(32), destination: '/pages/topic/index?id=late', tracked: true })
      await new Promise(resolve => setImmediate(resolve))
      assert.equal(await takeReferralLanding(), ''); assert.equal(referralPayload().referral_code, b)
    } finally { configureReferralTracking(null); bindReferralUser(null) }
  }
})
test('上一轮等待不能消费新扫码的落地内容', async () => {
  bindReferralUser(null)
  const finishes: ((value: any) => void)[] = []
  configureReferralTracking({ enter: () => new Promise(resolve => finishes.push(resolve)), start: async () => {} })
  try {
    captureReferral({ query: { ref: a } }); const previous = takeReferralLanding()
    captureReferral({ query: { ref: b } }); const current = takeReferralLanding()
    finishes[0]!({ visit_id: '7'.repeat(32), destination: '/pages/paper/index?id=old', tracked: true })
    assert.equal(await previous, '')
    finishes[1]!({ visit_id: '8'.repeat(32), destination: '/pages/paper/index?id=new', tracked: true })
    assert.equal(await current, '/pages/paper/index?id=new')
  } finally { configureReferralTracking(null); bindReferralUser(null) }
})
