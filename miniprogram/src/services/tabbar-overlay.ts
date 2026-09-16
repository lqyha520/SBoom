import { onScopeDispose, ref, watch } from 'vue'

const overlays = new Set<symbol>()
export const tabBarObscured = ref(false)

export function hideNativeTabBar() {
  uni.hideTabBar({ animation: false, fail() {} })
}

export function useTabBarOverlay(open: () => boolean) {
  const key = Symbol('tabbar-overlay')
  function restore() {
    overlays.delete(key)
    tabBarObscured.value = overlays.size > 0
  }
  watch(open, value => {
    if (value) {
      overlays.add(key)
      tabBarObscured.value = true
      // Never restore a second native bar underneath the application's custom tab bar.
      hideNativeTabBar()
    } else restore()
  }, { flush: 'sync', immediate: true })
  onScopeDispose(restore)
}
