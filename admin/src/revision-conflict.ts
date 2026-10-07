import { ref, watch, type Ref } from 'vue'
import { ApiError } from './api'

/** 更新基线版本，保留调用方的表单；用户核对后再显式保存。 */
export function useRevisionConflict<T extends { id: string; revision: number }>(target: Ref<T | null>, latest: (id: string) => Promise<T>, error: Ref<string>) {
  const conflict = ref(false), recovering = ref(false)
  watch(() => target.value?.id, () => { conflict.value = false })
  function capture(cause: unknown) { conflict.value = cause instanceof ApiError && cause.status === 409 }
  async function reload() {
    const id = target.value?.id
    if (!id || recovering.value) return
    recovering.value = true
    try {
      const value = await latest(id)
      if (target.value?.id !== id) return
      target.value = value; conflict.value = false
      error.value = '已载入最新版本，您的修改已保留，请核对后保存'
    } catch (cause) { error.value = cause instanceof Error ? cause.message : '读取最新版本失败' }
    finally { recovering.value = false }
  }
  return { conflict, recovering, capture, reload }
}
