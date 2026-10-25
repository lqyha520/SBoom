import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as vue from 'vue'
import { parse } from 'vue/compiler-sfc'

test('订单详情校验退款原因，提交后展示后端状态，并同步处理中退款', async () => {
  const calls: string[] = [], jobs: Promise<unknown>[] = []
  const order = { id: 'order', status: 'paid', expires_at: Date.now() / 1000 + 60, refund: null }
  const source = parse(readFileSync(new URL('../src/subpages/orders/index.vue', import.meta.url), 'utf8')).descriptor.scriptSetup!.content
  const exports: any = {}
  const modules: Record<string, unknown> = {
    vue,
    '@dcloudio/uni-app': { onLoad() {}, onReachBottom() {}, onShow() {}, onHide() {}, onUnload() {} },
    '../../services/consumer-page': { useConsumerPage: () => ({ error: vue.ref(''), busy: vue.ref(false), loading: vue.ref(false), act: (work: (valid: () => boolean) => Promise<void>) => jobs.push(work(() => true)) }) },
    '../../services/session': { session: { user: { has_wechat: true } }, refreshMembership: async () => { calls.push('membership') } },
    '../../services/checkout': { checkoutState: new Map(), checkoutSupport: () => true, settleCheckout: () => {} },
    '../../services/growth': {
      fetchOrder: async () => order,
      fetchPlans: async () => ({ checkout_enabled: true, ios_enabled: true }),
      requestRefund: async (id: string, reason: string) => { calls.push(`refund:${id}:${reason}`); return { ...order, refund: { id: 'refund', status: 'requested' } } },
      syncRefund: async (id: string) => { calls.push('sync:' + id); return { ...order, status: 'refunded', refund: { id, status: 'success' } } },
    },
  }
  vm.runInNewContext(ts.transpileModule(source + '\nexports.state = { id, selected, reason, refundError, refundOpen, load, refund, sync };', {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText, { exports, require: (name: string) => modules[name] || {} })
  const page = exports.state
  page.id.value = 'order'; await page.load(() => true)
  assert.equal(page.selected.value.status, 'paid')
  page.reason.value = '短'; page.refund(); assert.match(page.refundError.value, /至少 5 个字/); assert.equal(calls.length, 0)
  page.refundOpen.value = true; page.reason.value = '重复购买申请退款'; page.refund(); await Promise.all(jobs)
  assert.equal(page.selected.value.refund.status, 'requested'); assert.equal(page.refundOpen.value, false)
  page.selected.value.refund.status = 'processing'; page.sync(); await Promise.all(jobs)
  assert.equal(page.selected.value.status, 'refunded')
  assert.deepEqual(calls, ['refund:order:重复购买申请退款', 'sync:refund', 'membership'])
})

async function settle() { for (let index = 0; index < 10; index++) await Promise.resolve() }

test('订单详情按分钟展示付款倒计时，超时后停止并随页面生命周期清理定时器', async () => {
  let clock = 1_700_000_000_000, nextTimer = 1, interval = 0
  const timers = new Map<number, () => void>(), hooks: Record<string, () => void> = {}
  const order = { id: 'order', status: 'created', expires_at: clock / 1000 + 90, refund: null }
  const source = parse(readFileSync(new URL('../src/subpages/orders/index.vue', import.meta.url), 'utf8')).descriptor.scriptSetup!.content
  const exports: any = {}
  const modules: Record<string, unknown> = {
    vue,
    '@dcloudio/uni-app': { onLoad() {}, onReachBottom() {}, onShow: (fn: () => void) => { hooks.show = fn }, onHide: (fn: () => void) => { hooks.hide = fn }, onUnload: (fn: () => void) => { hooks.unload = fn } },
    '../../services/consumer-page': { useConsumerPage: () => ({ error: vue.ref(''), busy: vue.ref(false), loading: vue.ref(false), act: (work: (valid: () => boolean) => Promise<void>) => work(() => true) }) },
    '../../services/session': { session: { user: { has_wechat: true } }, refreshMembership: async () => {} },
    '../../services/checkout': { checkoutState: new Map(), checkoutSupport: () => true, settleCheckout: () => {} },
    '../../services/growth': {
      fetchOrder: async () => order,
      fetchPlans: async () => ({ checkout_enabled: true, ios_enabled: true }),
    },
  }
  vm.runInNewContext(ts.transpileModule(source + '\nexports.state = { id, selected, payable, payRemaining, now, load };', {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText, {
    exports, require: (name: string) => modules[name] || {},
    Date: { now: () => clock },
    setInterval: (fn: () => void, ms: number) => { interval = ms; const id = nextTimer++; timers.set(id, fn); return id },
    clearInterval: (id: number) => { timers.delete(id) },
  })
  const page = exports.state
  page.id.value = 'order'; await page.load(() => true); await settle()
  assert.equal(page.payable(page.selected.value), true)
  assert.equal(page.payRemaining.value, '01:30')
  assert.equal(interval, 1000); assert.equal(timers.size, 1)
  clock += 30_000; [...timers.values()][0](); await vue.nextTick()
  assert.equal(page.payRemaining.value, '01:00')
  clock += 61_000; [...timers.values()][0](); await vue.nextTick()
  assert.equal(page.payable(page.selected.value), false)
  assert.equal(page.payRemaining.value, '00:00')
  assert.equal(timers.size, 0)

  page.selected.value = { ...order, expires_at: clock / 1000 + 60 }; await vue.nextTick()
  assert.equal(timers.size, 1)
  hooks.hide(); assert.equal(timers.size, 0)
  hooks.show(); assert.equal(timers.size, 1)
  hooks.unload(); assert.equal(timers.size, 0)
})
