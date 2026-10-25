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
  if (typeof wx === 'undefined' || !wx.openPrivacyContract) {
    uni.showToast({ title: '暂时无法打开隐私指引，请稍后重试', icon: 'none' })
    return
  }
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
/** 微信在用户拒绝后约 10 秒内不会再次弹窗，失败时给出可操作的去处。 */
function showPrivacyGuide() {
  uni.showModal({
    title: '需要微信隐私授权',
    content: '复制会使用微信剪贴板。请在弹出的授权窗口点「同意并继续」；如果刚点了「暂不同意」，请等待约 10 秒再试。',
    confirmText: '去隐私设置',
    cancelText: '知道了',
    success: result => { if (result.confirm) uni.navigateTo({ url: '/subpages/privacy/index?kind=privacy' }) },
  })
}
/**
 * 隐私接口被拦截有两种原因：用户还没同意授权（可再次弹窗），或后台指引没声明该类信息（errno 112）。
 * 后者 needAuthorization 为 false，微信不会再弹授权，只能把原始错误留给开发者工具排查。
 * cause 来自各端事件，形状不一，只用于打日志。
 */
export function showPrivacyError(cause?: unknown) {
  // #ifdef MP-WEIXIN
  if (typeof wx !== 'undefined' && wx.getPrivacySetting) {
    wx.getPrivacySetting({
      success: result => {
        if (result.needAuthorization) { showPrivacyGuide(); return }
        console.warn('[privacy] action blocked without pending authorization', cause)
        uni.showToast({ title: '微信暂不允许复制，请稍后重试', icon: 'none' })
      },
      fail: () => { console.warn('[privacy] getPrivacySetting failed', cause); showPrivacyGuide() },
    })
    return
  }
  // #endif
  uni.showToast({ title: '请先同意隐私授权，再使用此功能', icon: 'none' })
}
export function copyWithPrivacy(options: UniApp.SetClipboardDataOptions) {
  void requirePrivacy().then(() => uni.setClipboardData({ ...options, fail: cause => {
    if (privacyError(cause)) showPrivacyError(cause)
    options.fail?.(cause)
  } })).catch((cause: { errMsg?: string }) => {
    showPrivacyError(cause)
    const failure = { errMsg: 'setClipboardData:fail privacy authorization denied' }
    options.fail?.(failure)
    options.complete?.(failure)
  })
}
