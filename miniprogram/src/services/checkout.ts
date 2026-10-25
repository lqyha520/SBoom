import { payOrder, refreshWechatSession, syncOrder, type CheckoutPayment, type Order, type PaymentParameters, type VirtualPaymentParameters } from './growth'
import { onIOS } from './platform'

export { onIOS }
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
  return onIOS() && !iosEnabled
  // #endif
  // #ifdef H5
  return false
  // #endif
}
export function checkoutSupport(iosEnabled: boolean) {
  let supported = false
  // #ifdef MP-WEIXIN
  supported = !onIOS() || iosEnabled
  // #endif
  return supported
}

// #ifdef MP-WEIXIN
class VirtualPayError extends Error {
  constructor(message: string, readonly code = 0) { super(message); this.name = 'VirtualPayError' }
}

function isVirtual(payment: CheckoutPayment | null): payment is VirtualPaymentParameters {
  return !!payment && (payment as VirtualPaymentParameters).mode === 'short_series_goods'
}

function wxLogin(): Promise<string> {
  return new Promise((resolve, reject) => uni.login({
    provider: 'weixin',
    success: result => result.code ? resolve(result.code) : reject(new Error('无法获取微信登录凭证，请重新进入小程序')),
    fail: () => reject(new Error('无法刷新微信登录态，请重新进入小程序')),
  }))
}

async function refreshSession() {
  await refreshWechatSession(await wxLogin())
}

function virtualError(cause: any): VirtualPayError {
  const message = String(cause?.errMsg || '')
  const code = Number(cause?.errCode) || 0
  if (code === -2 || message.includes('cancel')) return new VirtualPayError('已取消支付，可在订单中继续付款', code)
  if (code === -15002) return new VirtualPayError('订单已提交，正在确认支付结果', code)
  if (code === -15005 || code === -15006) return new VirtualPayError('支付签名校验失败，请联系客服', code)
  if (code === -15007) return new VirtualPayError('微信支付登录态已过期，请重试', code)
  if (code === -15008 || code === -15009) return new VirtualPayError('虚拟支付商户或商品尚未完成配置，请联系客服', code)
  if (code === -15010) return new VirtualPayError('商品尚未发布，请联系客服', code)
  if (code === -15011) return new VirtualPayError('虚拟支付环境配置错误，请联系客服', code)
  if (code === -15013) return new VirtualPayError('商品价格已更新，请重新下单', code)
  if (code === -15014) return new VirtualPayError('商品发布尚未生效，请稍后再试', code)
  if (code === -15017 || code === -15019) return new VirtualPayError('当前暂无法使用虚拟支付，请联系客服', code)
  if (code === -4) return new VirtualPayError('支付被风控拦截，请稍后重试或联系客服', code)
  return new VirtualPayError('支付未确认，请查询订单状态后再试', code)
}

function requestVirtual(payment: VirtualPaymentParameters): Promise<void> {
  return new Promise((resolve, reject) => {
    const api = (globalThis as any).wx
    if (!api?.requestVirtualPayment) return reject(new VirtualPayError('当前微信版本不支持虚拟支付，请升级微信后重试'))
    api.requestVirtualPayment({
      mode: payment.mode, signData: payment.signData, paySig: payment.paySig, signature: payment.signature,
      success: () => resolve(), fail: (cause: any) => reject(virtualError(cause)),
    })
  })
}

async function payOnce(id: string) {
  try {
    return await payOrder(id)
  } catch (error) {
    if ((error as any)?.code !== 'wechat_session_expired') throw error
    await refreshSession()
    return payOrder(id)
  }
}
// #endif

export async function checkout(id: string, valid: () => boolean, options: ReadOptions = {}): Promise<Order | null> {
  // #ifdef MP-WEIXIN
  if (checkoutState.has(id)) return confirmCheckout(id)
  const epoch = authGeneration()
  const result = await payOnce(id)
  if (!valid() || epoch !== authGeneration()) return null
  checkoutState.set(id, { epoch, phase: 'native', attempts: 0 })
  if (result.payment) {
    const payment = result.payment
    try {
      if (isVirtual(payment)) {
        try {
          await requestVirtual(payment)
        } catch (error) {
          if (!(error instanceof VirtualPayError) || error.code !== -15007) throw error
          await refreshSession()
          const retried = await payOnce(id)
          if (!isVirtual(retried.payment)) throw new Error('支付参数已更新，请重新下单')
          await requestVirtual(retried.payment)
        }
      } else {
        await new Promise<void>((resolve, reject) => uni.requestPayment({ provider: 'wxpay', ...(payment as PaymentParameters), success: () => resolve(), fail: cause => reject(new Error(cause.errMsg?.includes('cancel') ? '已取消支付，可在订单中继续付款' : '支付未确认，请查询订单状态后再试')) }))
      }
    } catch (error) {
      // -15002 表示同号订单已提交，继续查单确认；其余失败保留订单，交给订单页重试。
      if (!(error instanceof VirtualPayError) || error.code !== -15002) {
        checkoutState.delete(id)
        throw error
      }
    }
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
