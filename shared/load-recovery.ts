/** 保留当前页面，明确提示更新；只有保存成功且用户选择后才刷新。 */
let saveDraft: (() => Promise<boolean>) | undefined
let handling = false

export function setRecoverySave(save: () => Promise<boolean>) { saveDraft = save }

export async function recoverLoad() {
  if (handling) return
  handling = true
  try {
    if (saveDraft && !await saveDraft()) {
      window.alert('页面更新加载失败，草稿尚未保存。请先恢复本地存储，再刷新页面。')
      return
    }
    let refreshed = false
    try { refreshed = sessionStorage.getItem('lc-load-reloaded') === location.href } catch { /* 存储不可用时仍提供提示 */ }
    if (refreshed) {
      window.alert('页面仍未加载成功，请检查网络，稍后手动刷新。')
      return
    }
    if (window.confirm('页面已更新或网络中断，部分功能未能加载。现在刷新页面吗？')) {
      try { sessionStorage.setItem('lc-load-reloaded', location.href) } catch { /* 不自动循环刷新 */ }
      location.reload()
    }
  } catch {
    window.alert('草稿保存失败，请恢复本地存储后再刷新。')
  } finally { handling = false }
}

export function installLoadRecovery() {
  window.addEventListener('vite:preloadError', event => { event.preventDefault(); void recoverLoad() })
}
