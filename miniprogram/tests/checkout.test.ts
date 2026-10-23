import * as vue from 'vue'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

function fixture(platform = 'MP-WEIXIN', status = 'paid', nativeFailure = '', hideDuringPayment = false, switchAccount = false, options: { virtual?: boolean; payErrors?: any[]; virtualErrors?: any[]; refreshFails?: boolean } = {}) {
  const code = readFileSync(new URL('../src/services/checkout.ts', import.meta.url), 'utf8')
  let include = true
  const filtered = code.split('\n').filter(line => {
    const marker = /\/\/ #ifdef (.*)/.exec(line)
    if (marker) { include = marker[1]!.trim() === platform; return false }
    if (line.includes('// #endif')) { include = true; return false }
    return include
  }).join('\n')
  const events: string[] = []
  const delays: number[] = []
  let valid = true, epoch = 0
  const exports: Record<string, any> = {}
  const ordinaryPayment = { timeStamp: '123', nonceStr: 'nonce', package: 'prepay_id=fixture', signType: 'RSA', paySign: 'fixture-signature' }
  const virtualPayment = { mode: 'short_series_goods', signData: '{"offerId":"123","buyQuantity":1,"env":0,"currencyType":"CNY","productId":"fixture-product","goodsPrice":1990,"outTradeNo":"order-one","attach":"plan-one"}', paySig: 'fixture-pay-signature', signature: 'fixture-user-signature' }
  const payment = options.virtual ? virtualPayment : ordinaryPayment
  const growth = {
    async payOrder() { events.push('prepay'); const failure = options.payErrors?.shift(); if (failure) throw failure; return { order: { status: 'pending' }, payment } },
    async syncOrder() { events.push('server-confirm'); return { id: 'order-one', status } },
    async refreshWechatSession(value: string) { events.push('refresh-session:' + value); if (options.refreshFails) throw new Error('refresh failed') },
  }
  const requestVirtualPayment = (request: any) => {
    assert.equal(request.mode, virtualPayment.mode)
    assert.equal(request.signData, virtualPayment.signData)
    assert.equal(request.paySig, virtualPayment.paySig)
    assert.equal(request.signature, virtualPayment.signature)
    events.push('virtual-payment')
    if (hideDuringPayment) valid = false
    if (switchAccount) epoch++
    const failure = options.virtualErrors?.shift()
    if (failure) request.fail(failure); else request.success()
  }
  vm.runInNewContext(ts.transpileModule(filtered, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, {
    exports,
    setTimeout: (callback: () => void, delay: number) => { delays.push(delay); queueMicrotask(callback) },
    require: (id: string) => id === 'vue' ? vue : id === './api' ? { authGeneration: () => epoch } : id === './growth' ? growth : { async refreshMembership() { events.push('membership') } },
    uni: {
      getSystemInfoSync: () => ({ platform: 'ios' }),
      login(options: any) { events.push('wx-login'); options.success({ code: 'fixture-code' }) },
      requestPayment(options: any) { assert.equal(options.paySign, ordinaryPayment.paySign); events.push('native-payment'); if (hideDuringPayment) valid = false; if (switchAccount) epoch++; if (nativeFailure) options.fail({ errMsg: nativeFailure }); else options.success() },
      requestVirtualPayment,
    },
    wx: { requestVirtualPayment },
  })
  return { api: exports as any, events, delays, growth, valid: () => valid, invalidate: () => { valid = false }, switchAccount: () => { epoch++ } }
}

test('native payment is followed by server confirmation and entitlement refresh', async () => {
  const app = fixture()
  const order = await app.api.checkout('order-one', app.valid)
  assert.equal(order.status, 'paid')
  assert.deepEqual(app.events, ['prepay', 'native-payment', 'server-confirm', 'membership'])
})

test('native success cannot manufacture paid state when server still says pending', async () => {
  const app = fixture('MP-WEIXIN', 'pending')
  assert.equal((await app.api.checkout('order-one', app.valid)).status, 'pending')
  assert.deepEqual(app.delays, [1000, 2000])
  assert.equal(app.api.checkoutState.get('order-one').phase, 'waiting')
})

test('an exhausted confirmation cycle resumes later without another payment', async () => {
  const app = fixture('MP-WEIXIN', 'pending')
  await app.api.checkout('order-one', app.valid)
  app.growth.syncOrder = async () => { app.events.push('server-confirm'); return { id: 'order-one', status: 'paid' } }
  await app.api.resumeCheckouts()
  assert.equal(app.events.filter(x => x === 'prepay').length, 1)
  assert.equal(app.events.filter(x => x === 'server-confirm').length, 4)
  assert.equal(app.api.checkoutState.has('order-one'), false)
})

test('manual terminal results clear pending state and failed reads can retry', async () => {
  const app = fixture('MP-WEIXIN', 'pending')
  await app.api.checkout('order-one', app.valid)
  app.growth.syncOrder = async () => { throw new Error('offline') }
  await assert.rejects(app.api.confirmCheckout('order-one'), /offline/)
  assert.equal(app.api.checkoutState.get('order-one').phase, 'waiting')
  app.api.settleCheckout({ id: 'order-one', status: 'closed' })
  assert.equal(app.api.checkoutState.has('order-one'), false)
})

test('concurrent recovery shares a request and a changed account never refreshes old payment', async () => {
  const app = fixture('MP-WEIXIN', 'pending')
  await app.api.checkout('order-one', app.valid)
  let finish!: (value: { id: string; status: string }) => void
  app.growth.syncOrder = () => new Promise(resolve => { finish = resolve })
  const first = app.api.confirmCheckout('order-one')
  assert.equal(first, app.api.confirmCheckout('order-one'))
  app.switchAccount()
  finish({ id: 'order-one', status: 'paid' })
  assert.equal(await first, null)
  assert.equal(app.api.checkoutState.has('order-one'), false)
})

test('account/page changes prevent opening the old account payment sheet', async () => {
  const app = fixture()
  const original = app.growth.payOrder
  app.growth.payOrder = async () => { const result = await original(); app.invalidate(); return result }
  assert.equal(await app.api.checkout('order-one', app.valid), null)
  assert.deepEqual(app.events, ['prepay'])
})

test('native cancellation and unsupported platforms do not grant membership', async () => {
  const cancelled = fixture('MP-WEIXIN', 'paid', 'requestPayment:fail cancel')
  await assert.rejects(cancelled.api.checkout('order-one', cancelled.valid), /已取消支付/)
  assert.deepEqual(cancelled.events, ['prepay', 'native-payment'])
  assert.equal(cancelled.api.checkoutSupport(false), false)
  assert.equal(cancelled.api.checkoutSupport(true), true)
  const web = fixture('H5')
  await assert.rejects(web.api.checkout('order-one', web.valid), /微信小程序/)
  assert.equal(web.api.checkoutSupport(true), false)
  assert.deepEqual(web.events, [])
})


test('原生收银台 hide/show 不跳过服务端确认，也不依赖已取消的页面读取 scope', async () => {
  const app = fixture('MP-WEIXIN', 'paid', '', true)
  assert.equal((await app.api.checkout('order-one', app.valid)).status, 'paid')
  assert.equal(app.valid(), false)
  assert.deepEqual(app.events, ['prepay', 'native-payment', 'server-confirm', 'membership'])
})

test('支付期间换账号不再以新账号确认旧订单或刷新其会员权益', async () => {
  const app = fixture('MP-WEIXIN', 'paid', '', true, true)
  assert.equal(await app.api.checkout('order-one', app.valid), null)
  assert.deepEqual(app.events, ['prepay', 'native-payment'])
})

test('虚拟支付使用服务端签名唤起收银台，并以服务端查单结果为准', async () => {
  const app = fixture('MP-WEIXIN', 'paid', '', false, false, { virtual: true })
  const order = await app.api.checkout('order-one', app.valid)
  assert.equal(order.status, 'paid')
  assert.deepEqual(app.events, ['prepay', 'virtual-payment', 'server-confirm', 'membership'])
})

test('虚拟支付 session_key 过期时重新登录换签并自动重试', async () => {
  const app = fixture('MP-WEIXIN', 'paid', '', false, false, { virtual: true, virtualErrors: [{ errCode: -15007, errMsg: 'session_key expired' }] })
  const order = await app.api.checkout('order-one', app.valid)
  assert.equal(order.status, 'paid')
  assert.deepEqual(app.events, ['prepay', 'virtual-payment', 'wx-login', 'refresh-session:fixture-code', 'prepay', 'virtual-payment', 'server-confirm', 'membership'])
})

test('获取支付参数发现登录态过期时先刷新再重新下单', async () => {
  const app = fixture('MP-WEIXIN', 'paid', '', false, false, { virtual: true, payErrors: [{ code: 'wechat_session_expired' }] })
  const order = await app.api.checkout('order-one', app.valid)
  assert.equal(order.status, 'paid')
  assert.deepEqual(app.events, ['prepay', 'wx-login', 'refresh-session:fixture-code', 'prepay', 'virtual-payment', 'server-confirm', 'membership'])
})

test('虚拟支付重复单号交给服务端查单，不伪造付款成功', async () => {
  const app = fixture('MP-WEIXIN', 'pending', '', false, false, { virtual: true, virtualErrors: [{ errCode: -15002, errMsg: 'outTradeNo duplicate' }] })
  assert.equal((await app.api.checkout('order-one', app.valid)).status, 'pending')
  assert.deepEqual(app.events, ['prepay', 'virtual-payment', 'server-confirm', 'server-confirm', 'server-confirm', 'membership'])
  assert.equal(app.api.checkoutState.get('order-one').phase, 'waiting')
})

test('取消虚拟支付不触发服务端确认，可在订单页再次付款', async () => {
  const app = fixture('MP-WEIXIN', 'paid', '', false, false, { virtual: true, virtualErrors: [{ errCode: -2, errMsg: 'requestVirtualPayment:fail cancel' }] })
  await assert.rejects(app.api.checkout('order-one', app.valid), /已取消支付/)
  assert.deepEqual(app.events, ['prepay', 'virtual-payment'])
  assert.equal(app.api.checkoutState.has('order-one'), false)
})
