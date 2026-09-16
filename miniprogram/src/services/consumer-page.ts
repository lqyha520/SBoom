import { ref, watch } from 'vue'
import { onHide, onPullDownRefresh, onShow, onUnload } from '@dcloudio/uni-app'
import { errorMessage } from './api'
import { ensureSession, session } from './session'

/** A hidden page or different account never receives an old request's result. */
export function useConsumerPage(loader: (valid: () => boolean) => Promise<void>, clear: () => void) {
  const error = ref(''), loading = ref(false), busy = ref(false)
  let active = false, revision = 0
  const ticket = () => { const version = revision, owner = session.user?.id; return () => active && revision === version && owner === session.user?.id }
  async function refresh() {
    if (!active || !session.user || loading.value || busy.value) { uni.stopPullDownRefresh(); return }
    const valid = ticket(); loading.value = true; error.value = ''
    try { await loader(valid) } catch (cause) { if (valid()) error.value = errorMessage(cause) }
    finally { if (valid()) loading.value = false; uni.stopPullDownRefresh() }
  }
  async function act(operation: (valid: () => boolean) => Promise<void>) {
    if (!active || !session.user || busy.value || loading.value) return
    const valid = ticket(); busy.value = true; error.value = ''
    try { await operation(valid) } catch (cause) { if (valid()) error.value = errorMessage(cause) }
    finally { if (valid()) busy.value = false }
  }
  function leave() { active = false; revision++; loading.value = false; busy.value = false; uni.stopPullDownRefresh() }
  watch(() => session.user?.id, () => { revision++; loading.value = false; busy.value = false; error.value = ''; clear() }, { flush: 'sync' })
  onShow(async () => { active = true; if (await ensureSession() && active) void refresh() })
  onPullDownRefresh(refresh); onHide(leave); onUnload(() => { leave(); clear() })
  return { error, loading, busy, refresh, act, ticket }
}
