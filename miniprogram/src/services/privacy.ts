import { reactive } from 'vue'

export const LEGAL_VERSION = '2026-09-28'
const CONSENT_KEY = 'lc-legal-consent-version'
export const privacyState = reactive({ open: false, name: '用户隐私保护指引' })
let resolvers: ((value: { event: 'agree' | 'disagree'; buttonId?: string }) => void)[] = []

export function hasConsent() { try { return uni.getStorageSync(CONSENT_KEY) === LEGAL_VERSION } catch { return false } }
export function rememberConsent() { try { uni.setStorageSync(CONSENT_KEY, LEGAL_VERSION) } catch { /* 当前会话可继续 */ } }

export function installPrivacy() {
  // #ifdef MP-WEIXIN
  if (typeof wx !== 'undefined' && wx.onNeedPrivacyAuthorization) {
    // uni-app 的合并类型将回调误标成 GeneralCallbackResult，按微信 API 的真实签名收窄。
    const listen = wx.onNeedPrivacyAuthorization as unknown as (callback: (resolve: typeof resolvers[number]) => void) => void
    listen(resolve => {
      resolvers.push(resolve)
      privacyState.open = true
      wx.getPrivacySetting({ success: result => { privacyState.name = result.privacyContractName || '用户隐私保护指引' } })
    })
  }
  // #endif
}
export function resolvePrivacy(agree: boolean) {
  const pending = resolvers; resolvers = []; privacyState.open = false
  pending.forEach(resolve => resolve(agree ? { event: 'agree', buttonId: 'privacy-agree' } : { event: 'disagree' }))
}
export function openPrivacy() {
  // #ifdef MP-WEIXIN
  wx.openPrivacyContract({ fail: () => uni.showToast({ title: '暂时无法打开隐私指引，请稍后重试', icon: 'none' }) })
  // #endif
}
export async function requirePrivacy(): Promise<void> {
  // #ifdef MP-WEIXIN
  if (typeof wx !== 'undefined' && wx.requirePrivacyAuthorize) {
    await new Promise<void>((resolve, reject) => wx.requirePrivacyAuthorize({ success: () => resolve(),
      fail: () => reject(new Error('尚未同意微信隐私授权，请阅读并同意隐私指引后重试')) }))
  }
  // #endif
}
export function privacyError(cause: { errMsg?: string; errno?: number }) {
  return cause.errno === 112 || /privacy|authorize|隐私/i.test(cause.errMsg || '')
}
export function showPrivacyError() { uni.showToast({ title: '请先同意隐私授权，再使用此功能', icon: 'none' }) }
export function copyWithPrivacy(options: UniApp.SetClipboardDataOptions) {
  void requirePrivacy().then(() => uni.setClipboardData({ ...options, fail: cause => {
    if (privacyError(cause)) showPrivacyError()
    options.fail?.(cause)
  } })).catch(() => {
    showPrivacyError()
    const failure = { errMsg: 'setClipboardData:fail privacy authorization denied' }
    options.fail?.(failure)
    options.complete?.(failure)
  })
}
