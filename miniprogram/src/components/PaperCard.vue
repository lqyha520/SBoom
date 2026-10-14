<script setup lang="ts">
import type { PaperSummary } from '../types'
import { exerciseText, exerciseTitle, subjectTone, paperExtent, answerReadinessLabel } from '../presentation'
import { openCatalogPaper } from '../services/navigation'
import PrivateImage from './PrivateImage.vue'
import PaperAccessBadge from './PaperAccessBadge.vue'

withDefaults(defineProps<{ paper: PaperSummary; busy?: boolean; active?: boolean; compact?: boolean }>(), { active: true })
const emit = defineEmits<{ favorite: [] }>()
</script>

<template>
  <view class="paper-card" :class="[subjectTone(paper.subject), { 'paper-card-compact': compact }]">
    <button class="paper-card-open" hover-class="control-pressed" role="button" :aria-label="'打开习题：' + exerciseText(paper.title)" @click="openCatalogPaper(paper.id)">
      <view class="paper-cover">
        <view v-if="!paper.can_view" class="cover-sheet cover-locked"><wd-icon name="lock" size="21px" /><text>会员专享</text></view>
        <view v-else-if="paper.download_mode === 'external' && !paper.thumbnail_url" class="cover-sheet cover-locked"><wd-icon name="folder" size="21px" /><text>网盘资料</text></view><view v-else class="cover-sheet"><PrivateImage :src="paper.thumbnail_url" :active="active" /></view>
        <view class="cover-access"><PaperAccessBadge :paper="paper" /></view>
      </view>
      <text class="paper-card-title">{{ exerciseTitle(paper) }}</text>
      <text v-if="!compact" class="paper-card-keyword" :aria-hidden="!paper.keyword">{{ paper.keyword || '\u00a0' }}</text>
    </button>
    <view class="paper-card-bottom"><view class="paper-card-meta"><text>{{ compact ? paper.grade.replace(/^小学/, '') : paper.grade }} · {{ paper.subject }}</text><text>{{ paperExtent(paper) }}</text><text class="paper-answer" :class="{ available: paper.answer_readiness === 'included' || paper.answer_readiness === 'separate' }">{{ answerReadinessLabel(paper.answer_readiness) }}</text></view><wd-button :icon="paper.favorite ? 'heart-fill' : 'heart'" type="info" variant="text" :disabled="busy" role="button" :aria-pressed="paper.favorite" :aria-label="paper.favorite ? '取消收藏' : '收藏习题'" :title="paper.favorite ? '取消收藏' : '收藏习题'" :custom-class="'favorite-control' + (paper.favorite ? ' is-favorite' : '')" @click="emit('favorite')" /></view>
  </view>
</template>

<style scoped>
.paper-card { min-width: 0; padding: 10px 10px 8px; border: 1px solid var(--lc-card-line); border-radius: var(--lc-radius-card); background: var(--lc-card); box-shadow: var(--lc-card-shadow-soft); transition: transform .18s ease, box-shadow .18s ease; }
.paper-card:active { transform: scale(0.98); }
@media (hover: hover) { .paper-card:hover { transform: translateY(-2px); box-shadow: var(--lc-card-shadow); } }
.paper-card-open { display: block; width: 100%; padding: 0; margin: 0; border: 0; border-radius: 0; background: transparent; text-align: left; white-space: normal; line-height: 1.5; }
.paper-cover { position: relative; aspect-ratio: 1 / 1.5; display: flex; justify-content: center; align-items: center; background: var(--subject-tint); border-radius: 6px; padding: 8px; overflow: hidden; }
.cover-sheet { width: min(100%, 156px); flex: none; background: #fff; border: 1px solid var(--lc-card-line); }
.cover-locked { aspect-ratio: 1 / 1.4143; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; font-size: 12px; color: var(--lc-warning); }
.cover-access { position: absolute; right: 8px; bottom: 8px; }
.paper-card-title { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-height: 48px; margin-top: 10px; color: var(--lc-text); font-size: 16px; line-height: 1.5; font-weight: 600; overflow-wrap: anywhere; transition: color 0.2s ease; }
.paper-card-keyword { display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; min-height: 18px; margin-bottom: 8px; overflow: hidden; overflow-wrap: anywhere; font-size: 12px; line-height: 1.5; color: var(--lc-muted); }
.paper-card-bottom { position:relative;min-height:44px;margin-top:4px; }
.paper-card-bottom :deep(.favorite-control) { position:absolute;right:0;bottom:0; }
.paper-card-meta { min-width: 0; font-size: 13px; color: var(--lc-secondary); line-height: 1.7; overflow-wrap: anywhere; }
.paper-card-meta > text { display: block; }
.paper-card-meta .paper-answer { display:inline-flex;max-width:calc(100% - 44px);margin-top:5px; }
@media (hover: hover) { .paper-card-open:hover .paper-card-title { color: var(--lc-primary); } }
.paper-card-compact .paper-cover { height: 174px; aspect-ratio: auto; border-radius: 10px; padding: 8px; background: linear-gradient(145deg, var(--subject-tint), #f5f8f6); }
.paper-card-compact .cover-sheet { width: 112px; max-width: 100%; border-color: #dfe6e1; box-shadow: 0 3px 8px #28372f12; }
.paper-card-compact .cover-access { right: 6px; bottom: 6px; }
@media (max-height:680px) { .paper-card-compact .paper-cover { height:100px; }.paper-card-compact .cover-sheet { width:59px; } }
@media (prefers-reduced-motion: reduce) { .paper-card, .paper-card-title { transition: none; }.paper-card:active, .paper-card:hover { transform: none; } }
</style>
