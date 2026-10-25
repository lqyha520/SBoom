/** 下单设备只用于让服务端选对价格和留痕，不能当作安全凭证。 */
export function devicePlatform(): string {
  let platform = ''
  // #ifdef MP-WEIXIN
  try { platform = String((uni.getSystemInfoSync() as { platform?: unknown }).platform || '') } catch { platform = '' }
  // #endif
  return /^[a-z]{1,16}$/.test(platform) ? platform : ''
}

export function onIOS() {
  return devicePlatform() === 'ios'
}
