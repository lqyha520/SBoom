<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { onHide } from '@dcloudio/uni-app'
import { batchFavorites, fetchGroups, type FavoriteGroup } from '../services/experience'
import { errorMessage } from '../services/api'
import { session } from '../services/session'
import { confirmAction } from '../services/navigation'
import { createLatestRequest } from '../services/latest-request'
import { useTabBarOverlay } from '../services/tabbar-overlay'

const props = defineProps<{ ids: string[] }>()
const emit = defineEmits<{ busy: [value: boolean]; completed: []; close: []; refresh: [] }>()
const busy = ref(false), error = ref(''), groupOpen = ref(false), groups = ref<FavoriteGroup[]>([])
const reads = createLatestRequest()
let revision = 0
useTabBarOverlay(() => true)
function leave() { revision++; reads.invalidate(); groupOpen.value = false; busy.value = false; emit('busy', false) }
onHide(leave); onBeforeUnmount(leave)
watch(() => session.user?.id, leave, { flush: 'sync' })
function setBusy(value: boolean) { busy.value = value; emit('busy', value) }
async function chooseGroup() {
  if (busy.value || !props.ids.length) return
  const run = ++revision
  groupOpen.value = true; error.value = ''; setBusy(true)
  try {
    const result = await fetchGroups({ scope: reads.begin() })
    if (run === revision) groups.value = result.items
  } catch (cause) { if (run === revision) error.value = errorMessage(cause) }
  finally { if (run === revision) setBusy(false) }
}
async function apply(action: 'remove' | 'assign', groupId: string | null = null) {
  if (busy.value || !props.ids.length || !session.user) return
  const ids = [...props.ids], run = ++revision, owner = session.user.id
  const valid = () => run === revision && session.user?.id === owner
  setBusy(true); error.value = ''
  try {
    if (action === 'remove' && !await confirmAction('取消所选收藏', `确认取消这 ${ids.length} 份资料的收藏？下载记录不受影响。`)) return
    if (!valid()) return
    await batchFavorites(ids, action, groupId)
    if (!valid()) return
    groupOpen.value = false
    uni.showToast({ title: action === 'remove' ? `已取消 ${ids.length} 份收藏` : `已整理 ${ids.length} 份收藏`, icon: 'none' })
    emit('completed')
  } catch (cause) { if (valid()) error.value = errorMessage(cause) }
  finally { if (valid()) setBusy(false) }
}
</script>

<template>
  <view class="batch-dock">
    <view v-if="error && !groupOpen" class="batch-error" role="alert"><text class="grow">{{ error }}</text><button class="bare-icon" role="button" aria-label="刷新收藏列表" title="刷新列表" :disabled="busy" @click="emit('refresh')"><wd-icon name="refresh" size="20px" /></button></view>
    <view class="batch-heading"><text role="status">已选 {{ ids.length }} 份</text><button class="section-link" role="button" hover-class="control-pressed" :disabled="busy" @click="emit('close')">完成</button></view>
    <view class="batch-commands"><wd-button block role="button" aria-label="移至分组" variant="plain" icon="folder" :disabled="busy || !ids.length" @click="chooseGroup">移至分组</wd-button><wd-button block role="button" aria-label="取消收藏" type="danger" variant="plain" icon="delete" :loading="busy && !groupOpen" :disabled="busy || !ids.length" @click="apply('remove')">取消收藏</wd-button></view>
  </view>
  <wd-popup v-model="groupOpen" position="bottom" :z-index="1200" :close-on-click-modal="!busy" root-portal safe-area-inset-bottom custom-style="border-radius:8px 8px 0 0">
    <view class="sheet"><view class="sheet-head"><text class="sheet-title">移至分组</text><button class="bare-icon" role="button" aria-label="关闭分组选择" :disabled="busy" @click="groupOpen = false"><wd-icon name="close" size="20px" /></button></view>
      <view v-if="error" class="batch-error" role="alert"><text class="grow">{{ error }}</text><button class="bare-icon" role="button" aria-label="重新加载分组" :disabled="busy" @click="chooseGroup"><wd-icon name="refresh" size="20px" /></button></view>
      <view v-if="busy" class="loading-line"><wd-loading /><text>正在处理</text></view>
      <scroll-view scroll-y class="batch-groups"><button class="batch-group" role="button" :disabled="busy" @click="apply('assign')">未分组</button><button v-for="group in groups" :key="group.id" class="batch-group" role="button" :disabled="busy" @click="apply('assign', group.id)">{{ group.name }}</button></scroll-view>
    </view>
  </wd-popup>
</template>

<style scoped>
.batch-dock { position:fixed;z-index:900;bottom:0;left:0;right:0;max-width:520px;margin:auto;padding:8px var(--lc-page-gutter) calc(12px + env(safe-area-inset-bottom));background:var(--lc-surface);border-top:1px solid var(--lc-border); }
.batch-heading,.batch-error { display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:13px; }.batch-error { color:#a34040;line-height:1.6;max-height:88px;overflow:auto; }
.batch-commands { display:grid;grid-template-columns:1fr 1fr;gap:10px; }.batch-groups { height:40vh; }.batch-group { width:100%;min-height:48px;margin:0;padding:12px 0;background:transparent;color:var(--lc-text);font-size:14px;line-height:1.6;text-align:left;white-space:normal;overflow-wrap:anywhere;border-bottom:1px solid var(--lc-border); }
</style>
