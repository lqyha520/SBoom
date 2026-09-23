import { ref, watch } from 'vue'
import { onHide, onPullDownRefresh, onShow, onUnload } from '@dcloudio/uni-app'
import { errorMessage } from './api'
import { ensureSession, session } from './session'
import type { RequestScope } from './latest-request'

export type ConsumerTicket = (() => boolean) & RequestScope

/** A hidden page or different account never receives an old request's result. */
export function useConsumerPage(loader: (valid: ConsumerTicket) => Promise<void>, clear: () => void) {
  const error = ref(''), loading = ref(false), busy = ref(false)
  let active = false, revision = 0
  let reconnectPending = false
  const cancellations = new Set<() => void>()
  function invalidate() { revision++; for (const cancel of cancellations) cancel(); cancellations.clear() }
  function flushReconnect() { if (reconnectPending && active && !loading.value && !busy.value) { reconnectPending = false; void refresh() } }
  const ticket = (): ConsumerTicket => {
    const version = revision, owner = session.user?.id
    const valid = () => active && revision === version && owner === session.user?.id
    return Object.assign(valid, { onCancel(cancel: () => void) {
      if (!valid()) { cancel(); return () => {} }
      cancellations.add(cancel)
      return () => { cancellations.delete(cancel) }
    } })
  }
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
  function leave() { active = false; invalidate(); loading.value = false; busy.value = false; reconnectPending = false; uni.stopPullDownRefresh() }
  watch(() => session.user?.id, () => { invalidate(); loading.value = false; busy.value = false; error.value = ''; clear() }, { flush: 'sync' })
  function reconnect() { if (active) { reconnectPending = true; flushReconnect() } }
  uni.$on?.('lc-network-restored', reconnect)
  onShow(async () => { active = true; if (await ensureSession() && active) void refresh() })
  onPullDownRefresh(refresh); onHide(leave); onUnload(() => { leave(); clear(); uni.$off?.('lc-network-restored', reconnect) })
  return { error, loading, busy, refresh, act, ticket }
}
