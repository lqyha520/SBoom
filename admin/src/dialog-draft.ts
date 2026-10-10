import { computed, onActivated, onDeactivated, ref, watch, type Ref } from 'vue'
import { useBeforeUnload } from './unsaved'
import { useAdminLeaveGuard } from './navigation'

/** 弹窗、Esc、页面切换和关闭标签页共用同一份修改状态。 */
export function useDialogDraft(open: Ref<boolean>, snapshot: () => unknown, busy: Ref<boolean>, label = '内容') {
  const revision = computed(() => JSON.stringify(snapshot()))
  const saved = ref('')
  const active = ref(true)
  const dirty = computed(() => active.value && open.value && revision.value !== saved.value)
  const markSaved = () => { saved.value = revision.value }
  const canLeave = () => !open.value || !active.value || (!busy.value && (!dirty.value || window.confirm(`有未保存的${label}，确认放弃修改？`)))
  const setOpen = (value: boolean) => { if (value || canLeave()) open.value = value }
  const model = computed({ get: () => open.value, set: setOpen })
  watch(open, value => { if (value) markSaved() }, { flush: 'sync', immediate: true })
  onActivated(() => { active.value = true })
  onDeactivated(() => { active.value = false })
  useBeforeUnload(computed(() => active.value && open.value && (dirty.value || busy.value)))
  useAdminLeaveGuard(canLeave)
  return { model, dirty, markSaved, canLeave, setOpen }
}
