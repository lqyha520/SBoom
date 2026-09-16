import { onActivated, onBeforeUnmount, onDeactivated, onMounted, ref } from 'vue'
export function useAdminPage(loader: (valid: () => boolean) => Promise<void>, close: () => void = () => {}) {
  const loading = ref(false), busy = ref(false), error = ref(''), notice = ref('')
  let active = false, revision = 0, loadVersion = 0, queued = false
  const ticket = () => { const current = revision; return () => active && current === revision }
  async function load() {
    if (!active) return
    const version = ++loadVersion
    if (loading.value) { queued = true; return }
    const alive = ticket(), valid = () => alive() && version === loadVersion
    loading.value = true; error.value = ''
    try { await loader(valid) } catch (cause) { if (valid()) error.value = cause instanceof Error ? cause.message : '加载失败，请重试' }
    finally { if (alive()) { loading.value = false; if (queued) { queued = false; void load() } } }
  }
  async function act(operation: (valid: () => boolean) => Promise<void>) {
    if (busy.value || !active) return
    const valid = ticket(); busy.value = true; error.value = ''; notice.value = ''
    try { await operation(valid) } catch (cause) { if (valid()) error.value = cause instanceof Error ? cause.message : '操作失败，请重试' }
    finally { if (valid()) busy.value = false }
  }
  function activate() { if (active) return; active = true; void load() }
  function deactivate() { active = false; revision++; loadVersion++; queued = false; loading.value = false; busy.value = false; close() }
  onMounted(activate); onActivated(activate); onDeactivated(deactivate); onBeforeUnmount(deactivate)
  return { loading, busy, error, notice, load, act, ticket }
}
