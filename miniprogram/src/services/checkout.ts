import { payOrder, syncOrder, type Order } from './growth'
import { refreshMembership } from './session'
import type { ReadOptions } from './api'
import { authGeneration } from './api'
import { reactive } from 'vue'

export const checkoutState = reactive(new Map<string, { epoch: number; phase: 'native' | 'confirming' | 'waiting'; attempts: number }>())
const confirming = new Map<string, Promise<Order | null>>()
export function settleCheckout(order: Order) {
  if (!['created', 'pending'].includes(order.status)) checkoutState.delete(order.id)
}
export function confirmCheckout(id: string): Promise<Order | null> {
  const existing = confirming.get(id)
  if (existing) return existing
  const state = checkoutState.get(id)
  if (!state || state.phase === 'native' || state.epoch !== authGeneration()) { if (state?.epoch !== authGeneration()) checkoutState.delete(id); return Promise.resolve(null) }
  const promise = (async () => {
    let confirmed: Order | null = null
    state.attempts = 0
    state.phase = 'confirming'
    while (state.attempts < 3 && state.epoch === authGeneration() && checkoutState.get(id) === state) {
      if (state.attempts) await new Promise(resolve => setTimeout(resolve, state.attempts * 1000))
      if (state.epoch !== authGeneration() || checkoutState.get(id) !== state) return null
      state.attempts++
      confirmed = await syncOrder(id)
      if (state.epoch !== authGeneration()) return null
      if (!['created', 'pending'].includes(confirmed.status)) break
    }
    if (state.epoch !== authGeneration()) return null
    if (confirmed) settleCheckout(confirmed)
    await refreshMembership({ force: true })
    return confirmed
  })().finally(() => {
    if (checkoutState.get(id) === state) {
      if (state.epoch !== authGeneration()) checkoutState.delete(id)
      else state.phase = 'waiting'
    }
    confirming.delete(id)
  })
  confirming.set(id, promise)
  return promise
}
export async function resumeCheckouts() {
  await Promise.allSettled([...checkoutState.keys()].map(confirmCheckout))
}

export function iosRestricted(iosEnabled: boolean) {
  // #ifdef MP-WEIXIN
  return uni.getSystemInfoSync().platform === 'ios' && !iosEnabled
  // #endif
  // #ifdef H5
  return false
  // #endif
}
export function checkoutSupport(iosEnabled: boolean) {
  let supported = false
  // #ifdef MP-WEIXIN
  supported = uni.getSystemInfoSync().platform !== 'ios' || iosEnabled
  // #endif
  return supported
}
export async function checkout(id: string, valid: () => boolean, options: ReadOptions = {}): Promise<Order | null> {
  // #ifdef MP-WEIXIN
  if (checkoutState.has(id)) return confirmCheckout(id)
  const epoch = authGeneration()
  const result = await payOrder(id)
  if (!valid() || epoch !== authGeneration()) return null
  checkoutState.set(id, { epoch, phase: 'native', attempts: 0 })
  if (result.payment) {
    const payment = result.payment
    try {
      await new Promise<void>((resolve, reject) => uni.requestPayment({ provider: 'wxpay', ...payment, success: () => resolve(), fail: cause => reject(new Error(cause.errMsg?.includes('cancel') ? '已取消支付，可在订单中继续付款' : '支付未确认，请查询订单状态后再试')) }))
    } catch (error) { checkoutState.delete(id); throw error }
  }
  if (epoch !== authGeneration()) { checkoutState.delete(id); return null }
  // 原生收银台触发 onHide 后，仍在原账号内完成服务端确认。
  checkoutState.set(id, { epoch, phase: 'confirming', attempts: 0 })
  const confirmed = await confirmCheckout(id)
  uni.$emit?.('lc-checkout-confirmed')
  return confirmed
  // #endif
  // #ifdef H5
  throw new Error('请在微信小程序内支付')
  // #endif
}
