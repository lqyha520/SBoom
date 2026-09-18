<script setup lang="ts">
import type { PaperSummary } from '../types'
import { fileStatus, formatDate } from '../content'
import PrivateImage from './PrivateImage.vue'
import SwipeAction from './SwipeAction.vue'
import { exerciseText, exerciseTitle, subjectTone } from '../presentation'
import { openCatalogPaper } from '../services/navigation'
import { vibrate } from '../utils/performance'

defineProps<{ paper: PaperSummary; busy?: boolean }>()
const emit = defineEmits<{ favorite: []; download: []; share: [] }>()

const swipeActions = [
  { key: 'favorite', label: '收藏', icon: 'heart', color: '#ff6b6b' },
  { key: 'download', label: '下载', icon: 'download', color: '#4ecdc4' },
  { key: 'share', label: '分享', icon: 'share', color: '#45b7d1' }
]

function handleSwipeAction(key: string) {
  vibrate(10)
  if (key === 'favorite') {
    emit('favorite')
  } else if (key === 'download') {
    emit('download')
  } else if (key === 'share') {
    emit('share')
  }
}
</script>

<template>
  <SwipeAction :actions="swipeActions" @action="handleSwipeAction">
    <view class="paper-row" :class="subjectTone(paper.subject)">
      <button class="paper-main" role="button" :aria-label="'打开习题：' + exerciseText(paper.title)" @click="openCatalogPaper(paper.id)">
        <view class="paper-thumb"><view v-if="!paper.can_view" class="row-vip-cover"><wd-icon name="lock" size="20px" /></view><view v-else-if="paper.download_mode === 'external' && !paper.thumbnail_url" class="row-vip-cover"><wd-icon name="folder" size="23px" /></view><view v-else class="paper-thumb-sheet"><PrivateImage :src="paper.thumbnail_url" /></view></view>
        <view class="grow"><view class="paper-labels"><text>{{ paper.grade }}</text><text>·</text><text>{{ paper.subject }}</text></view><text class="paper-name">{{ exerciseTitle(paper) }}</text></view><view class="paper-meta"><text v-if="paper.download_mode === 'external'">网盘资料</text><template v-else><text>{{ paper.question_count }} 题</text><text>·</text><text v-if="paper.file_status !== 'ready'" class="file-pending">{{ fileStatus(paper.file_status) }}</text><text v-else>{{ paper.page_count }} 页</text></template><text>·</text><text :class="{ 'paper-editorial': paper.required_download === 'vip' }">{{ paper.required_view === 'vip' ? 'VIP 专享' : paper.required_download === 'vip' ? 'VIP 下载' : paper.download_mode === 'external' ? '获取链接' : 'PDF' }}</text></view><text v-if="paper.activity_at" class="paper-topic">{{ formatDate(paper.activity_at) }}</text></view>
      </button>
      <wd-button :icon="paper.favorite ? 'heart-fill' : 'heart'" type="info" variant="text" :disabled="busy" role="button" :aria-label="paper.favorite ? '取消收藏' : '收藏习题'" :title="paper.favorite ? '取消收藏' : '收藏习题'" :custom-class="'favorite-control' + (paper.favorite ? ' is-favorite' : '')" @click="emit('favorite')" />
    </view>
  </SwipeAction>
</template>

<style scoped>
.row-vip-cover { display: flex; align-items: center; justify-content: center; width: 100%; color: var(--subject-color); }
</style>