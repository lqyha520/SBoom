import { onBeforeUnmount, onMounted, type Ref } from 'vue'

/** 页面缓存保留草稿；离开整个后台时提示尚未保存的内容。 */
export function useBeforeUnload(pending: Ref<boolean>) {
  const guard = (event: BeforeUnloadEvent) => { if (pending.value) { event.preventDefault(); event.returnValue = '' } }
  onMounted(() => window.addEventListener('beforeunload', guard))
  onBeforeUnmount(() => window.removeEventListener('beforeunload', guard))
}
