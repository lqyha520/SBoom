import { ref, watch } from 'vue'
import { onHide, onPullDownRefresh, onShow, onUnload } from '@dcloudio/uni-app'
import { errorMessage } from './api'
import { ensureSession, session } from './session'
import { usePageLifecycle, type PageTicket } from './page-lifecycle'
import { resumeCheckouts } from './checkout'

export type ConsumerTicket = PageTicket

/** A hidden page or different account never receives an old request's result. */
export function useConsumerPage(loader: (valid: ConsumerTicket) => Promise<void>, clear: () => void) {
  const error = ref(''), loading = ref(false), busy = ref(false)
  const lifecycle = usePageLifecycle(() => session.user?.id)
  let active = false
  let activation = 0
  let reconnectPending = false
  const invalidate = lifecycle.invalidate
  function flushReconnect() { if (reconnectPending && active && !loading.value && !busy.value) { reconnectPending = false; void refresh() } }
  const ticket = lifecycle.ticket
  async function refresh() {
    if (!active || !session.user || loading.value || busy.value) { uni.stopPullDownRefresh(); return }
    const valid = ticket(); loading.value = true; error.value = ''
    try { await loader(valid) } catch (cause) { if (valid()) error.value = errorMessage(cause) }
    finally { if (valid()) loading.value = false; uni.stopPullDownRefresh(); flushReconnect() }
  }
  async function act(operation: (valid: ConsumerTicket) => Promise<void>) {
    if (!active || !session.user || busy.value || loading.value) return
    const valid = ticket(); busy.value = true; error.value = ''
    try { await operation(valid) } catch (cause) { if (valid()) error.value = errorMessage(cause) }
    finally { if (valid()) busy.value = false; flushReconnect() }
  }
  function leave() { active = false; activation++; lifecycle.leave(); loading.value = false; busy.value = false; reconnectPending = false; uni.stopPullDownRefresh() }
  watch(() => session.user?.id, () => { invalidate(); loading.value = false; busy.value = false; error.value = ''; clear() }, { flush: 'sync' })
  function reconnect() { if (active) { reconnectPending = true; flushReconnect() } }
  uni.$on?.('lc-network-restored', reconnect)
  function checkoutConfirmed() { if (active) { reconnectPending = true; flushReconnect() } }
  uni.$on?.('lc-checkout-confirmed', checkoutConfirmed)
  onShow(async () => {
    active = true; lifecycle.show()
    const run = ++activation
    if (!await ensureSession() || !active || run !== activation) return
    const valid = ticket()
    // 先读取当前页，查单在后台继续；查单完成后再更新，避免所有服务页等待付款同步。
    void refresh()
    void resumeCheckouts().then(confirmed => {
      if (confirmed && valid() && run === activation) { reconnectPending = true; flushReconnect() }
    })
  })
  onPullDownRefresh(refresh); onHide(leave); onUnload(() => { leave(); clear(); uni.$off?.('lc-network-restored', reconnect); uni.$off?.('lc-checkout-confirmed', checkoutConfirmed) })
  return { error, loading, busy, refresh, act, ticket }
}
