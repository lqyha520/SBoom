import { payOrder, syncOrder, type Order } from './growth'
import { refreshMembership } from './session'

export function checkoutSupport(iosEnabled: boolean) {
  let supported = false
  // #ifdef MP-WEIXIN
  supported = uni.getSystemInfoSync().platform !== 'ios' || iosEnabled
  // #endif
  return supported
}
export async function checkout(id: string, valid: () => boolean): Promise<Order | null> {
  // #ifdef MP-WEIXIN
  const result = await payOrder(id)
  if (!valid()) return null
  if (result.payment) {
    const payment = result.payment
    await new Promise<void>((resolve, reject) => uni.requestPayment({ provider: 'wxpay', ...payment, success: () => resolve(), fail: cause => reject(new Error(cause.errMsg?.includes('cancel') ? '已取消支付，可在订单中继续付款' : '支付未确认，请查询订单状态后再试')) }))
  }
  if (!valid()) return null
  // Only the backend's verified provider status determines whether payment completed.
  const confirmed = await syncOrder(id)
  if (!valid()) return null
  await refreshMembership()
  return valid() ? confirmed : null
  // #endif
  // #ifdef H5
  throw new Error('请在微信小程序内支付')
  // #endif
}
