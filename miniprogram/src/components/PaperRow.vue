<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PaperSummary } from '../types'
import { fileStatus, formatDate } from '../content'
import PrivateImage from './PrivateImage.vue'
import SwipeAction from './SwipeAction.vue'
import { exerciseText, exerciseTitle, subjectTone, paperExtent, paperAccess, answerReadinessLabel } from '../presentation'
import { openCatalogPaper } from '../services/navigation'

const props = withDefaults(defineProps<{ paper: PaperSummary; busy?: boolean; expanded?: boolean; active?: boolean; selectable?: boolean; selected?: boolean }>(), { active: true })
const swipe = ref<InstanceType<typeof SwipeAction> | null>(null)
const emit = defineEmits<{ favorite: []; download: []; share: []; open: []; select: []; expand: [open: boolean] }>()

let shareLabel = '复制链接'
let shareType: 'share' | undefined
// #ifdef MP-WEIXIN
shareLabel = '分享'; shareType = 'share'
// #endif
const swipeActions = computed(() => [
  { key: 'favorite', label: props.paper.favorite ? '取消收藏' : '收藏', icon: 'heart', color: '#a74e60' },
  { key: 'download', label: '查看资料', icon: 'file', color: '#307e61' },
  { key: 'share', label: shareLabel, icon: 'link', color: '#456a9c', openType: shareType },
])
function handleSwipeAction(key: string) {
  if (props.busy) return
  if (key === 'favorite') emit('favorite')
  else if (key === 'download') emit('download')
  else if (key === 'share') emit('share')
}
function openPaper() {
  if (props.selectable) { if (!props.busy) emit('select'); return }
  if (!swipe.value?.blocksClick(true)) { emit('open'); openCatalogPaper(props.paper.id) }
}
function favorite() { if (!swipe.value?.blocksClick()) emit('favorite') }
</script>

<template>
  <SwipeAction ref="swipe" :actions="swipeActions" :open="selectable ? false : expanded" :disabled="busy || selectable" :share-id="paper.id" :share-title="exerciseText(paper.title)" @update:open="emit('expand', $event)" @action="handleSwipeAction">
    <view class="paper-row" :class="[subjectTone(paper.subject), { 'row-selected': selectable && selected }]">
      <button class="paper-main" role="button" :aria-label="(selectable ? selected ? '取消选择：' : '选择：' : '打开习题：') + exerciseText(paper.title)" hover-class="control-pressed" @click="openPaper">
        <view class="paper-thumb"><view v-if="!paper.can_view" class="row-vip-cover"><wd-icon name="lock" size="20px" /></view><view v-else-if="paper.download_mode === 'external' && !paper.thumbnail_url" class="row-vip-cover"><wd-icon name="folder" size="23px" /></view><view v-else class="paper-thumb-sheet"><PrivateImage :src="paper.thumbnail_url" :active="active" /></view></view>
        <view class="grow">
          <text class="paper-name">{{ exerciseTitle(paper) }}</text>
          <view class="paper-labels"><text>{{ paper.grade.replace(/^小学/, '') }} · {{ paper.subject }}</text><text>{{ paperExtent(paper) }}</text></view>
          <view class="paper-meta"><text class="paper-answer" :class="{ available: paper.answer_readiness === 'included' || paper.answer_readiness === 'separate' }">{{ answerReadinessLabel(paper.answer_readiness) }}</text><view class="access-badge" :class="{ 'is-free': paper.required_view !== 'vip' && paper.required_download !== 'vip' }"><text>{{ paperAccess(paper) }}</text></view><text v-if="paper.file_status !== 'ready' && paper.download_mode !== 'external'" class="file-pending">{{ fileStatus(paper.file_status) }}</text></view>
          <text v-if="paper.activity_at" class="paper-topic">{{ formatDate(paper.activity_at) }}</text>
        </view>
      </button>
      <view v-if="selectable" class="row-controls"><button class="bare-icon" role="checkbox" :aria-checked="selected" :aria-label="(selected ? '取消选择：' : '选择：') + exerciseText(paper.title)" :disabled="busy" @click="emit('select')"><view class="row-check" :class="{ checked: selected }"><wd-icon v-if="selected" name="check" size="15px" /></view></button></view>
      <view v-else class="row-controls"><button class="favorite-control bare-icon" :class="{ 'is-favorite': paper.favorite }" hover-class="control-pressed" :disabled="busy" role="button" :aria-pressed="paper.favorite" :aria-label="paper.favorite ? '取消收藏' : '收藏习题'" :title="paper.favorite ? '取消收藏' : '收藏习题'" @click="favorite"><wd-icon :name="paper.favorite ? 'heart-fill' : 'heart'" size="22px" /></button><button role="button" class="bare-icon row-more" :disabled="busy" :aria-expanded="expanded" aria-label="更多资料操作" hover-class="control-pressed" @click="emit('expand', !expanded)"><wd-icon name="more" size="20px" /></button></view>
    </view>
  </SwipeAction>
</template>

<style scoped>
.paper-name { margin-top:0; }.paper-labels { margin-top:5px;gap:2px 8px;font-size:12px;line-height:1.6; }.paper-meta { margin-top:5px;gap:4px; }
.row-controls { display:flex;flex-direction:column;align-items:center;flex:none; }
.row-more { height:44px; }.is-favorite { color:var(--lc-coral); }
.row-vip-cover { display: flex; align-items: center; justify-content: center; width: 100%; color: var(--subject-color); }
.row-selected { background:var(--lc-primary-soft); }.row-check { width:22px;height:22px;border:1px solid var(--lc-muted);border-radius:4px;display:flex;align-items:center;justify-content:center; }.row-check.checked { border-color:var(--lc-primary);background:var(--lc-primary);color:#fff; }
</style>
