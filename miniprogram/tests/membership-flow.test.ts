import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as vue from 'vue'
import { parse } from 'vue/compiler-sfc'

async function fixture(options: { native?: boolean; enabled?: boolean; hasWechat?: boolean; lifetime?: boolean; confirm?: boolean; supportFails?: boolean; plansFail?: boolean } = {}) {
  const session = vue.reactive({ user: { id: 'reader', username: 'wx1234567890', has_wechat: options.hasWechat ?? true, is_vip: !!options.lifetime, vip_expires_at: null as number | null } })
  const plans = [{ id: 'month', revision: 1, name: '月度会员', days: 30, price_fen: 1990 }, { id: 'quarter', revision: 2, name: '季度会员', days: 90, price_fen: 4990 }]
  const orders: { id: string; key: string }[] = [], confirmations: string[] = [], native: string[] = []
  const jobs: Promise<unknown>[] = []
  let redemptions = 0, valid = true
  const busy = vue.ref(false), loading = vue.ref(false), error = vue.ref('')
  const modules: Record<string, unknown> = {
    vue,
    '../../services/session': { session, async refreshMembership() {} },
    '../../services/consumer-page': { useConsumerPage: () => ({ busy, loading, error, act(operation: (valid: () => boolean) => Promise<void>) {
      if (busy.value || loading.value) return
      busy.value = true; error.value = ''
      jobs.push(operation(() => valid).catch(cause => { error.value = cause.message }).finally(() => { busy.value = false }))
    } }) },
    '../../services/growth': {
      async fetchPlans() { if (options.plansFail) throw new Error('plans unavailable'); return { items: plans, checkout_enabled: options.enabled ?? true, ios_enabled: false } },
      async createOrder(plan: typeof plans[number], key: string) { orders.push({ id: plan.id, key }); return { id: 'created-order' } },
      async redeemMembershipCard() { redemptions++; return { user: { ...session.user, is_vip: true, vip_expires_at: 1800000000 }, days: 30 } },
      requestKey: () => 'unique-request', yuan: (price: number) => '¥' + (price / 100).toFixed(2), openOrder: (id: string) => native.push('order:' + id),
    },
    '../../services/experience': {
      async fetchSupport() { if (options.supportFails) throw new Error('support unavailable'); return { wechat: 'support_demo', phone: '4000000000' } },
      openSupport: (kind: string) => native.push('feedback:' + kind),
    },
    '../../services/checkout': { checkoutSupport: () => options.native ?? true },
    '../../services/navigation': { async confirmAction(_title: string, message: string) { confirmations.push(message); return options.confirm ?? true } },
  }
  const exports: Record<string, any> = {}
  const source = parse(readFileSync(new URL('../src/pages/membership/index.vue', import.meta.url), 'utf8')).descriptor.scriptSetup!.content
  vm.runInNewContext(ts.transpileModule(source + '\nexports.controls = { load, plans, contact, contactError, selectedId, contactOpen, selectPlan, primary, purchase, cardCode, redeem, redeemedDays, callContact, leaveMessage }', {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText, { exports, require: (id: string) => modules[id] || {}, uni: { switchTab: (value: { url: string }) => native.push(value.url), makePhoneCall: (value: { phoneNumber: string }) => native.push('call:' + value.phoneNumber), showToast() {} } })
  const controls = exports.controls
  if (!options.plansFail) await controls.load(() => valid)
  return { controls, options, session, plans, orders, confirmations, native, busy, error, redemptions: () => redemptions, invalidate: () => { valid = false }, finish: () => Promise.all(jobs) }
}

test('plan selection is separate from order creation and repeated confirmation is gated', async () => {
  const app = await fixture()
  app.controls.selectPlan(app.plans[1])
  assert.equal(app.controls.selectedId.value, 'quarter')
  assert.equal(app.orders.length, 0)
  app.controls.primary(); app.controls.primary()
  await app.finish()
  assert.deepEqual(app.orders, [{ id: 'quarter', key: 'unique-request' }])
  assert.equal(app.confirmations.length, 1)
  assert.match(app.confirmations[0]!, /90 天，¥49.90/)
  assert.deepEqual(app.native, ['order:created-order'])
})

test('unsupported checkout, cancellation and leaving the page cannot create an order', async () => {
  for (const options of [{ native: false }, { enabled: false }, { hasWechat: false }]) {
    const app = await fixture(options)
    app.controls.primary(); app.controls.purchase(app.plans[0]); await app.finish()
    assert.equal(app.controls.contactOpen.value, true)
    assert.equal(app.orders.length, 0)
  }
  const cancelled = await fixture({ confirm: false })
  cancelled.controls.primary(); await cancelled.finish()
  assert.equal(cancelled.orders.length, 0)
  const stale = await fixture()
  stale.controls.primary(); stale.invalidate(); await stale.finish()
  assert.equal(stale.orders.length, 0)
})

test('lifetime membership prevents repeat purchases and redemption; short cards get a readable error', async () => {
  const lifetime = await fixture({ lifetime: true })
  lifetime.controls.cardCode.value = 'LC-TEST-CARD'
  lifetime.controls.redeem(); lifetime.controls.primary(); await lifetime.finish()
  assert.equal(lifetime.orders.length, 0)
  assert.equal(lifetime.redemptions(), 0)
  assert.deepEqual(lifetime.native, ['/pages/library/index'])
  const regular = await fixture()
  regular.controls.cardCode.value = 'short'
  regular.controls.redeem(); await regular.finish()
  assert.match(regular.error.value, /卡密至少需要 8 位/)
  assert.equal(regular.redemptions(), 0)
  regular.controls.cardCode.value = 'LC-VALID-CARD'
  regular.controls.redeem(); await regular.finish()
  assert.equal(regular.redemptions(), 1)
  assert.equal(regular.session.user.is_vip, true)
  assert.equal(regular.controls.redeemedDays.value, 30)
  assert.equal(regular.controls.cardCode.value, '')
})

test('contact and plan failures are independent and support actions have a working destination', async () => {
  const app = await fixture({ supportFails: true })
  assert.equal(app.controls.plans.value.length, 2)
  assert.equal(app.controls.contactError.value, true)
  app.options.supportFails = false
  await app.controls.load(() => true)
  assert.equal(app.controls.contactError.value, false)
  app.controls.callContact(); app.controls.leaveMessage()
  assert.deepEqual(app.native, ['call:4000000000', 'feedback:membership'])
  const unavailablePlans = await fixture({ plansFail: true })
  await assert.rejects(unavailablePlans.controls.load(() => true), /plans unavailable/)
  assert.equal(unavailablePlans.controls.contact.value.wechat, 'support_demo')
})
