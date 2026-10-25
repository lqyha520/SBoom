import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as vue from 'vue'
import { parse } from 'vue/compiler-sfc'

async function fixture(options: { contact?: boolean; ios?: boolean; device?: 'ios' | 'android'; native?: boolean; enabled?: boolean; hasWechat?: boolean; lifetime?: boolean; confirm?: boolean; supportFails?: boolean; plansFail?: boolean; createError?: { message: string; code: string }; plans?: { id: string; revision: number; name: string; days: number; price_fen: number; price_fen_ios?: number; ios_available?: boolean; purchase_limit?: number; purchased?: number; pending?: number; pending_order?: string | null; pending_expires_at?: number | null }[] } = {}) {
  const session = vue.reactive({ user: { id: 'reader', username: 'wx1234567890', has_wechat: options.hasWechat ?? true, is_vip: !!options.lifetime, vip_expires_at: null as number | null } })
  const plans = options.plans ?? [{ id: 'month', revision: 1, name: '月度会员', days: 30, price_fen: 1990 }, { id: 'quarter', revision: 2, name: '季度会员', days: 90, price_fen: 4990 }]
  const orders: { id: string; key: string }[] = [], confirmations: string[] = [], native: string[] = []
  const jobs: Promise<unknown>[] = []
  let redemptions = 0, refreshes = 0, valid = true
  const busy = vue.ref(false), loading = vue.ref(false), error = vue.ref('')
  const modules: Record<string, unknown> = {
    vue,
    '@dcloudio/uni-app': { onLoad: (fn: (options: Record<string, string>) => void) => fn(options.contact ? { contact: '1' } : {}) },
    '../../services/session': { session, async refreshMembership() {} },
    '../../services/consumer-page': { useConsumerPage: () => ({ busy, loading, error, refresh: () => { refreshes++ }, act(operation: (valid: () => boolean) => Promise<void>) {
      if (busy.value || loading.value) return Promise.resolve()
      busy.value = true; error.value = ''
      const job = operation(() => valid).catch(cause => { error.value = cause.message }).finally(() => { busy.value = false })
      jobs.push(job)
      return job
    } }) },
    '../../services/growth': {
      async fetchPlans() { if (options.plansFail) throw new Error('plans unavailable'); return { items: plans, checkout_enabled: options.enabled ?? true, ios_enabled: false } },
      async createOrder(plan: typeof plans[number], key: string) {
        if (options.createError) throw Object.assign(new Error(options.createError.message), { code: options.createError.code })
        orders.push({ id: plan.id, key }); return { id: 'created-order' }
      },
      async redeemMembershipCard() { redemptions++; return { user: { ...session.user, is_vip: true, vip_expires_at: 1800000000 }, days: 30 } },
      requestKey: () => 'unique-request', yuan: (price: number) => '¥' + (price / 100).toFixed(2), openOrder: (id: string) => native.push('order:' + id),
    },
    '../../services/experience': {
      async fetchSupport() { if (options.supportFails) throw new Error('support unavailable'); return { wechat: 'support_demo', phone: '4000000000' } },
      openSupport: (kind: string) => native.push('feedback:' + kind),
    },
    '../../services/checkout': { iosRestricted: () => !!options.ios, checkoutSupport: () => !options.ios && (options.native ?? true), onIOS: () => options.device === 'ios' || !!options.ios },
    '../../services/navigation': { async confirmAction(_title: string, message: string) { confirmations.push(message); return options.confirm ?? true } },
  }
  const exports: Record<string, any> = {}
  const source = parse(readFileSync(new URL('../src/subpages/membership/index.vue', import.meta.url), 'utf8')).descriptor.scriptSetup!.content
  vm.runInNewContext(ts.transpileModule(source + '\nexports.controls = { load, plans, listed, contact, contactError, selectedId, contactOpen, selectPlan, primary, purchase, cardCode, redeem, redeemedDays, callContact, leaveMessage, planLimitLabel, awaitingOrder, limitReached }', {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText, { exports, require: (id: string) => modules[id] || {}, uni: { switchTab: (value: { url: string }) => native.push(value.url), makePhoneCall: (value: { phoneNumber: string }) => native.push('call:' + value.phoneNumber), showToast() {} } })
  const controls = exports.controls
  if (!options.plansFail) await controls.load(() => valid)
  return { controls, options, session, plans, orders, confirmations, native, busy, error, redemptions: () => redemptions, refreshes: () => refreshes, invalidate: () => { valid = false }, finish: () => Promise.all(jobs) }
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

test('contact deep link opens the contact sheet without creating an order', async () => {
  const app = await fixture({ contact: true })
  assert.equal(app.controls.contactOpen.value, true)
  assert.equal(app.orders.length, 0)
})

test('restricted iOS cannot create orders, open purchase contact, or redeem cards', async () => {
  const app = await fixture({ ios: true })
  app.controls.cardCode.value = 'LC-VALID-CARD'
  app.controls.primary(); app.controls.purchase(app.plans[0]); app.controls.redeem()
  await app.finish()
  assert.equal(app.orders.length, 0)
  assert.equal(app.redemptions(), 0)
  assert.equal(app.controls.contactOpen.value, false)
})

test('iPhone lists only iOS-sellable plans and confirms the iPhone price', async () => {
  const app = await fixture({ device: 'ios', plans: [
    { id: 'month', revision: 1, name: '月度会员', days: 30, price_fen: 1990 },
    { id: 'year', revision: 3, name: '年度会员', days: 365, price_fen: 19900, price_fen_ios: 22800, ios_available: true },
  ] })
  assert.deepEqual(app.controls.listed.value.map((plan: { id: string }) => plan.id), ['year'])
  assert.equal(app.controls.selectedId.value, 'year')
  app.controls.primary(); await app.finish()
  assert.match(app.confirmations[0]!, /365 天，¥228\.00/)
  assert.deepEqual(app.orders, [{ id: 'year', key: 'unique-request' }])
})

test('iPhone hides plans with no iOS price and never offers the Android price', async () => {
  const app = await fixture({ device: 'ios', plans: [{ id: 'month', revision: 1, name: '月度会员', days: 30, price_fen: 1990 }] })
  assert.deepEqual(app.controls.listed.value, [])
  assert.equal(app.controls.selectedId.value, '')
  app.controls.primary(); await app.finish()
  assert.equal(app.orders.length, 0)
  assert.equal(app.controls.contactOpen.value, true)
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

test('an open order is reopened instead of creating a duplicate for the same plan', async () => {
  const app = await fixture({ plans: [
    { id: 'month', revision: 1, name: '月度会员', days: 30, price_fen: 1990, pending: 1, pending_order: 'open-order' },
    { id: 'quarter', revision: 2, name: '季度会员', days: 90, price_fen: 4990, pending: 0, pending_order: null },
  ] })
  assert.equal(app.controls.selectedId.value, 'quarter')
  app.controls.selectPlan(app.plans[0])
  assert.deepEqual(app.native, ['order:open-order'])
  app.controls.purchase(app.plans[0]); await app.finish()
  assert.equal(app.orders.length, 0)
})

test('limited plans block repeat purchases and route to the open order until it is settled', async () => {
  const app = await fixture({ plans: [
    { id: 'trial', revision: 1, name: '体验卡', days: 1, price_fen: 1, purchase_limit: 1, purchased: 1, pending: 0, pending_order: null },
    { id: 'month', revision: 1, name: '月度会员', days: 30, price_fen: 1990, purchase_limit: 1, purchased: 0, pending: 1, pending_order: 'open-order' },
  ] })
  assert.equal(app.controls.selectedId.value, '')
  app.controls.selectPlan(app.plans[0]); app.controls.purchase(app.plans[0])
  app.controls.selectPlan(app.plans[1]); app.controls.purchase(app.plans[1])
  await app.finish()
  assert.deepEqual(app.native, ['order:open-order'])
  assert.equal(app.orders.length, 0)
  app.controls.primary()
  assert.deepEqual(app.native, ['order:open-order', 'order:open-order'])
})

test('plan labels distinguish limited, pending and expired orders', async () => {
  const app = await fixture()
  const label = app.controls.planLimitLabel
  const plan = (extra: Record<string, unknown>) => ({ id: 'p', name: '体验卡', description: '', days: 1, price_fen: 1, revision: 1, ...extra })
  assert.equal(label(plan({ purchase_limit: 1, purchased: 1 })), '已达限购')
  assert.equal(label(plan({ purchase_limit: 2, purchased: 1 })), '已购 1/2')
  assert.equal(label(plan({ purchase_limit: 2 })), '限购 2 次')
  assert.equal(label(plan({ pending: 1, pending_expires_at: 9999999999 })), '有待付款订单')
  assert.equal(label(plan({ pending: 1, pending_expires_at: 1 })), '订单已超时')
  assert.equal(label(plan({})), '')
})

test('a limit conflict refreshes the plan list so the open order becomes visible', async () => {
  const app = await fixture({ createError: { message: '该套餐每个账号限购 1 次，请先完成或取消已有的未完成订单', code: 'purchase_limit' } })
  app.controls.primary(); await app.finish(); await Promise.resolve()
  assert.equal(app.orders.length, 0)
  assert.equal(app.refreshes(), 1)
  assert.match(app.error.value, /限购 1 次/)
  const other = await fixture({ createError: { message: '套餐价格或权益已更新', code: '' } })
  other.controls.primary(); await other.finish(); await Promise.resolve()
  assert.equal(other.refreshes(), 0)
})
