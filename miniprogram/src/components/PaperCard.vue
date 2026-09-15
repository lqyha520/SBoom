<script setup lang="ts">
import type { PaperSummary } from '../types'
import { exerciseText, exerciseTitle, subjectTone } from '../presentation'
import { openCatalogPaper } from '../services/navigation'
import PrivateImage from './PrivateImage.vue'

defineProps<{ paper: PaperSummary; busy?: boolean }>()
const emit = defineEmits<{ favorite: [] }>()
</script>

<template>
  <view class="paper-card" :class="subjectTone(paper.subject)">
    <button class="paper-card-open" role="button" :aria-label="'打开习题：' + exerciseText(paper.title)" @click="openCatalogPaper(paper.id)">
      <view class="paper-cover">
        <view v-if="!paper.can_view" class="cover-sheet cover-locked"><wd-icon name="lock" size="21px" /><text>会员专享</text></view>
        <view v-else class="cover-sheet"><PrivateImage :src="paper.thumbnail_url" /></view>
        <view v-if="paper.required_download === 'vip'" class="access-badge cover-access"><wd-icon v-if="paper.required_view === 'vip'" name="star" size="12px" /><text>{{ paper.required_view === 'vip' ? 'VIP' : 'VIP 下载' }}</text></view>
      </view>
      <text class="paper-card-title">{{ exerciseTitle(paper) }}</text>
    </button>
    <view class="paper-card-bottom"><view class="paper-card-meta"><text>{{ paper.grade }}</text><text>{{ paper.subject }} · {{ paper.question_count }} 题</text></view><wd-button :icon="paper.favorite ? 'heart-fill' : 'heart'" type="info" variant="text" :disabled="busy" role="button" :aria-pressed="paper.favorite" :aria-label="paper.favorite ? '取消收藏' : '收藏习题'" :title="paper.favorite ? '取消收藏' : '收藏习题'" :custom-class="'favorite-control' + (paper.favorite ? ' is-favorite' : '')" @click="emit('favorite')" /></view>
  </view>
</template>

<style scoped>
.paper-card { min-width: 0; padding: 9px 9px 3px; border: 1px solid var(--lc-card-line); border-radius: 14px; background: var(--lc-card); box-shadow: var(--lc-card-shadow-soft); }
.paper-card-open { display: block; width: 100%; padding: 0; margin: 0; border: 0; border-radius: 0; background: transparent; text-align: left; white-space: normal; line-height: 1.5; }
.paper-cover { position: relative; height: 152px; display: flex; justify-content: center; align-items: center; background: var(--subject-tint); border-radius: 10px; }
.cover-sheet { width: 91px; flex: none; transform: rotate(-6deg); background: #fff; box-shadow: 4px 5px 0 #ffffff80, 0 7px 16px #37496a18; transition: transform .2s; }
.language .cover-sheet { transform: rotate(5deg); }
.cover-locked { height: 129px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; font-size: 11px; color: var(--lc-warning); }
.cover-access { position: absolute; right: 8px; bottom: 8px; }
.paper-card-title { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-height: 42px; margin-top: 11px; color: var(--lc-text); font-size: 14px; line-height: 21px; font-weight: 600; overflow-wrap: anywhere; }
.paper-card-bottom { display: flex; justify-content: space-between; align-items: center; gap: 2px; min-height: 44px; }
.paper-card-meta { min-width: 0; font-size: 11px; color: var(--lc-muted); line-height: 1.6; overflow-wrap: anywhere; }
.paper-card-meta > text { display: block; }
@media (hover: hover) { .paper-card-open:hover .cover-sheet { transform: translateY(-4px) rotate(-2deg); } }
.paper-card-open:active .cover-sheet { transform: rotate(0); }
@media (max-width: 359px) { .paper-cover { height: 132px; } .cover-sheet { width: 80px; } .cover-locked { height: 113px; } }
</style>
