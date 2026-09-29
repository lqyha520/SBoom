<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { createGroup, deleteGroup, fetchGroups, renameGroup, type FavoriteGroup } from '../services/experience'
import { errorMessage } from '../services/api'
import { session } from '../services/session'
import { onHide } from '@dcloudio/uni-app'
import { createLatestRequest } from '../services/latest-request'
import { confirmAction } from '../services/navigation'
const props = defineProps<{ selected: string }>()
const emit = defineEmits<{ select: [id: string] }>()
const groups = ref<FavoriteGroup[]>([])
const managing = ref(false)
const busy = ref(false)
const error = ref('')
let generation = 0
const reads = createLatestRequest()
function leave() { generation++; reads.invalidate(); managing.value = false }
onHide(leave); onBeforeUnmount(leave)
async function load() {
  const current = ++generation
  const scope = reads.begin()
  try { const data = await fetchGroups({ scope }); if (current === generation) { groups.value = data.items; if (props.selected && !data.items.some(item => item.id === props.selected)) emit('select', '') } }
  catch (cause) { if (current === generation) error.value = errorMessage(cause) }
}
watch(() => session.user?.id, id => { generation++; groups.value = []; error.value = ''; managing.value = false; if (id) void load() }, { immediate: true })
async function edit(group?: FavoriteGroup) {
  if (busy.value) return
  const owner = session.user?.id
  const result = await new Promise<UniApp.ShowModalRes>(resolve => uni.showModal({ title: group ? '重命名收藏分组' : '新建收藏分组', editable: true, placeholderText: group?.name || '例如：期末复习', success: resolve, fail: () => resolve({ confirm: false, cancel: true }) }))
  if (!result.confirm || !result.content?.trim() || owner !== session.user?.id) return
  busy.value = true; error.value = ''
  try { if (group) await renameGroup(group, result.content.trim()); else await createGroup(result.content.trim()); await load() }
  catch (cause) { error.value = errorMessage(cause) }
  finally { busy.value = false }
}
async function remove(group: FavoriteGroup) {
  const owner = session.user?.id
  if (busy.value || !await confirmAction('删除收藏分组', '组内资料仍会保留在全部收藏中。') || owner !== session.user?.id) return
  busy.value = true; error.value = ''
  try { await deleteGroup(group); if (props.selected === group.id) emit('select', ''); await load() }
  catch (cause) { error.value = errorMessage(cause) }
  finally { busy.value = false }
}
defineExpose({ refresh: load })
</script>
<template>
  <view class="favorite-groups">
    <scroll-view scroll-x class="group-scroll"><view class="group-chips"><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" :class="{ chosen: !selected }" @click="emit('select', '')">全部收藏</button><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" v-for="group in groups" :key="group.id" :class="{ chosen: selected === group.id }" @click="emit('select', group.id)">{{ group.name }}</button></view></scroll-view>
    <view class="group-tools"><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" class="section-link" :disabled="busy" @click="edit()">新建分组</button><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" class="section-link" @click="managing = !managing">{{ managing ? '收起管理' : '管理分组' }}</button></view>
    <view v-if="error" class="error-strip">{{ error }}</view>
    <view v-if="managing"><view v-for="group in groups" :key="group.id" class="group-row"><text class="grow">{{ group.name }}</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" :disabled="busy" class="section-link" @click="edit(group)">改名</button><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" :disabled="busy" class="section-link" @click="remove(group)">删除</button></view></view>
  </view>
</template>
<style scoped>
.favorite-groups { padding: 12px 0; }.group-chips,.group-tools,.group-row { display:flex;gap:12px;align-items:center;flex-wrap:wrap; }.group-scroll { width:100%;white-space:nowrap; }.group-chips { flex-wrap:nowrap;width:max-content; }.group-chips button { flex:none;max-width:240px;overflow:hidden;text-overflow:ellipsis; margin:0;padding:5px 12px;font-size:12px;background:var(--lc-background);color:var(--lc-secondary);border-radius:20px; }.group-chips .chosen { background:var(--lc-primary-soft);color:var(--lc-primary); }.group-tools { margin-top:10px; }.group-row { padding:10px 0;border-bottom:1px solid var(--lc-card-line); }
</style>
