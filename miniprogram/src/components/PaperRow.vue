<script setup lang="ts">
import type { PaperSummary } from '../types'
import { fileStatus, formatDate } from '../content'
import PrivateImage from './PrivateImage.vue'
import { exerciseText, exerciseTitle, subjectTone } from '../presentation'
import { openCatalogPaper } from '../services/navigation'
defineProps<{ paper: PaperSummary; busy?: boolean }>()
const emit = defineEmits<{ favorite: [] }>()
</script>

<template>
  <view class="paper-row" :class="subjectTone(paper.subject)">
    <button class="paper-main" role="button" :aria-label="'打开习题：' + exerciseText(paper.title)" @click="openCatalogPaper(paper.id)">
      <view class="paper-thumb"><view v-if="!paper.can_view" class="row-vip-cover"><wd-icon name="lock" size="20px" /></view><view v-else class="paper-thumb-sheet"><PrivateImage :src="paper.thumbnail_url" /></view></view>
      <view class="grow"><view class="paper-labels"><text>{{ paper.grade }}</text><text>·</text><text>{{ paper.subject }}</text></view><text class="paper-name">{{ exerciseTitle(paper) }}</text><view class="paper-meta"><text>{{ paper.question_count }} 题</text><text>·</text><text v-if="paper.file_status !== 'ready'" class="file-pending">{{ fileStatus(paper.file_status) }}</text><text v-else>{{ paper.page_count }} 页</text><text>·</text><text :class="{ 'paper-editorial': paper.required_download === 'vip' }">{{ paper.required_view === 'vip' ? 'VIP 专享' : paper.required_download === 'vip' ? 'VIP 下载' : 'PDF' }}</text></view><text v-if="paper.activity_at" class="paper-topic">{{ formatDate(paper.activity_at) }}</text></view>
    </button>
    <wd-button :icon="paper.favorite ? 'heart-fill' : 'heart'" type="info" variant="text" :disabled="busy" role="button" :aria-label="paper.favorite ? '取消收藏' : '收藏习题'" :title="paper.favorite ? '取消收藏' : '收藏习题'" :custom-class="'favorite-control' + (paper.favorite ? ' is-favorite' : '')" @click="emit('favorite')" />
  </view>
</template>

<style scoped>
.row-vip-cover { display: flex; align-items: center; justify-content: center; width: 100%; color: var(--subject-color); }
</style>
