import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch, type ComputedRef, type Ref } from 'vue'
import { downloadBlob } from '../../shared/download'

interface Backup<T> { version: 1; revision: string; updatedAt: string; data: T }
export interface DraftBackupController {
  recovery: Ref<{ updatedAt: string; revision: string } | null>
  storageError: Ref<string>; savedAt: Ref<string>; stale: ComputedRef<boolean>
  persist: () => void; clear: () => void; restore: () => void; discard: () => void; download: () => void
}
/** 仅备份编辑数据，不包含素材文件或浏览器登录凭据。 */
export function useXhsDraftBackup<T>(options: {
  adminId: number; scope: () => string; enabled: () => boolean; dirty: () => boolean
  snapshot: () => T; restore: (data: T) => void; revision: () => string
}): DraftBackupController {
  const recovery = shallowRef<Backup<T> | null>(null), storageError = ref(''), savedAt = ref('')
  const key = computed(() => `lc-xhs-editor-v1:${options.adminId}:${options.scope()}`)
  const stale = computed(() => !!recovery.value && recovery.value.revision !== options.revision())
  let timer: ReturnType<typeof setTimeout> | undefined
  const ownWrites = new Map<string, string>()
  function stop() { if (timer) clearTimeout(timer); timer = undefined }
  function read() {
    recovery.value = null; savedAt.value = ''; storageError.value = ''
    if (!options.enabled() || !options.scope()) return
    try {
      const encoded = localStorage.getItem(key.value) || 'null'
      const value = JSON.parse(encoded)
      if (ownWrites.get(key.value) === encoded) { savedAt.value = value.updatedAt; return }
      if (value?.version === 1 && typeof value.revision === 'string' && typeof value.updatedAt === 'string' && value.data && typeof value.data === 'object') recovery.value = value
    } catch { storageError.value = '本机草稿无法读取，请先将当前内容保存到后台。' }
  }
  function persist() {
    stop()
    if (!options.enabled() || !options.dirty() || !options.scope() || recovery.value) return
    try {
      const value: Backup<T> = { version: 1, revision: options.revision(), updatedAt: new Date().toISOString(), data: options.snapshot() }
      const encoded = JSON.stringify(value)
      localStorage.setItem(key.value, encoded); ownWrites.set(key.value, encoded); savedAt.value = value.updatedAt; storageError.value = ''
    } catch { storageError.value = '本机备份未成功，可能是存储空间不足；请立即保存到后台。' }
  }
  function clear() {
    stop()
    try { localStorage.removeItem(key.value); ownWrites.delete(key.value); recovery.value = null; savedAt.value = ''; storageError.value = '' }
    catch { storageError.value = '无法清除本机备份，再次打开时请核对后台版本。' }
  }
  function restore() {
    if (!recovery.value || stale.value) return
    if (options.dirty() && !window.confirm('恢复本机草稿会替换当前未保存的编辑，是否继续？')) return
    try { options.restore(JSON.parse(JSON.stringify(recovery.value.data))); savedAt.value = recovery.value.updatedAt; recovery.value = null }
    catch { storageError.value = '草稿内容无法恢复，可下载备份后手动核对。' }
  }
  function discard() { if (window.confirm('丢弃这份本机备份？后台已保存内容会保留。')) clear() }
  function download() { if (recovery.value) downloadBlob(new Blob([JSON.stringify(recovery.value, null, 2)], { type: 'application/json' }), '小红书编辑备份.json') }
  function beforeUnload(event: BeforeUnloadEvent) { if (options.dirty()) { persist(); event.preventDefault(); event.returnValue = '' } }
  watch(() => [key.value, options.enabled()], read, { flush: 'post' })
  watch(() => JSON.stringify(options.snapshot()), () => { stop(); if (options.enabled() && options.dirty()) timer = setTimeout(persist, 400) }, { flush: 'post' })
  onMounted(() => { read(); window.addEventListener('beforeunload', beforeUnload) })
  onBeforeUnmount(() => { persist(); stop(); window.removeEventListener('beforeunload', beforeUnload) })
  return { recovery, storageError, savedAt, stale, persist, clear, restore, discard, download }
}
