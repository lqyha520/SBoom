<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PaperSummary } from '../types'
import { fileStatus, formatDate } from '../content'
import PrivateImage from './PrivateImage.vue'
import SwipeAction from './SwipeAction.vue'
import PaperAccessBadge from './PaperAccessBadge.vue'
import { exerciseText, exerciseTitle, subjectTone, paperExtent } from '../presentation'
import { openCatalogPaper } from '../services/navigation'

const props = defineProps<{ paper: PaperSummary; busy?: boolean; expanded?: boolean }>()
const swipe = ref<InstanceType<typeof SwipeAction> | null>(null)
const emit = defineEmits<{ favorite: []; download: []; share: []; expand: [open: boolean] }>()

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
function openPaper() { if (!swipe.value?.blocksClick(true)) openCatalogPaper(props.paper.id) }
function favorite() { if (!swipe.value?.blocksClick()) emit('favorite') }
</script>

<template>
  <SwipeAction ref="swipe" :actions="swipeActions" :open="expanded" :disabled="busy" :share-id="paper.id" :share-title="exerciseText(paper.title)" @update:open="emit('expand', $event)" @action="handleSwipeAction">
    <view class="paper-row" :class="subjectTone(paper.subject)">
      <button class="paper-main" role="button" :aria-label="'打开习题：' + exerciseText(paper.title)" hover-class="control-pressed" @click="openPaper">
        <view class="paper-thumb"><view v-if="!paper.can_view" class="row-vip-cover"><wd-icon name="lock" size="20px" /></view><view v-else-if="paper.download_mode === 'external' && !paper.thumbnail_url" class="row-vip-cover"><wd-icon name="folder" size="23px" /></view><view v-else class="paper-thumb-sheet"><PrivateImage :src="paper.thumbnail_url" lazy /></view></view>
        <view class="grow"><view class="paper-labels"><text>{{ paper.grade }}</text><text>·</text><text>{{ paper.subject }}</text></view><text class="paper-name">{{ exerciseTitle(paper) }}</text><view class="paper-meta"><text>{{ paperExtent(paper) }}</text><PaperAccessBadge :paper="paper" /><text v-if="paper.file_status !== 'ready' && paper.download_mode !== 'external'" class="file-pending">{{ fileStatus(paper.file_status) }}</text></view><text v-if="paper.activity_at" class="paper-topic">{{ formatDate(paper.activity_at) }}</text></view>
      </button>
      <view class="row-controls"><wd-button :icon="paper.favorite ? 'heart-fill' : 'heart'" type="info" variant="text" :disabled="busy" role="button" :aria-label="paper.favorite ? '取消收藏' : '收藏习题'" :title="paper.favorite ? '取消收藏' : '收藏习题'" :custom-class="'favorite-control' + (paper.favorite ? ' is-favorite' : '')" @click="favorite" /><button role="button" class="bare-icon row-more" :disabled="busy" :aria-expanded="expanded" aria-label="更多资料操作" hover-class="control-pressed" @click="emit('expand', !expanded)"><wd-icon name="more" size="20px" /></button></view>
    </view>
  </SwipeAction>
</template>

<style scoped>
.row-controls { display:flex;flex-direction:column;align-items:center;flex:none; }
.row-more { height:44px; }
.row-vip-cover { display: flex; align-items: center; justify-content: center; width: 100%; color: var(--subject-color); }
</style>
