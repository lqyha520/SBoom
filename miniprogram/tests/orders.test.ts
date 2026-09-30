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
    '@dcloudio/uni-app': { onLoad() {}, onReachBottom() {} },
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
