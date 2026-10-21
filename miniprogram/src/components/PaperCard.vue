<script setup lang="ts">
import { ref, watch } from 'vue'
import type { PaperSummary } from '../types'
import { answerReadinessLabel, exerciseText, exerciseTitle, subjectTone, paperExtent } from '../presentation'
import { openCatalogPaper } from '../services/navigation'
import PrivateImage from './PrivateImage.vue'
import PaperAccessBadge from './PaperAccessBadge.vue'

const props = withDefaults(defineProps<{ paper: PaperSummary; busy?: boolean; active?: boolean }>(), { active: true })
const popping = ref(false)
let popTimer: ReturnType<typeof setTimeout> | undefined
watch(() => props.paper.favorite, favorite => {
  clearTimeout(popTimer)
  if (!favorite) { popping.value = false; return }
  popping.value = true
  popTimer = setTimeout(() => { popping.value = false }, 400)
})
const emit = defineEmits<{ favorite: [] }>()
</script>

<template>
  <view class="paper-card" :class="subjectTone(paper.subject)">
    <button class="paper-card-open" hover-class="paper-card-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" :aria-label="'打开习题：' + exerciseText(paper.title)" @click="openCatalogPaper(paper.id)">
      <view class="paper-cover">
        <view v-if="!paper.can_view" class="cover-sheet cover-locked"><wd-icon name="lock" size="20px" /><text>会员专享</text></view>
        <view v-else-if="paper.download_mode === 'external' && !paper.thumbnail_url" class="cover-sheet cover-locked"><wd-icon name="folder" size="20px" /><text>网盘资料</text></view>
        <view v-else class="cover-sheet"><PrivateImage :src="paper.thumbnail_url" :active="active" fit crop /></view>
        <view class="cover-access"><PaperAccessBadge :paper="paper" /></view>
      </view>
      <view class="paper-card-copy">
        <text class="paper-card-title">{{ exerciseTitle(paper) }}</text>
        <view class="paper-card-foot">
          <text class="paper-card-meta">{{ paper.grade.replace(/^小学/, '') }} · {{ paper.subject }} · {{ paperExtent(paper) }}</text>
          <text class="paper-answer" :class="{ available: paper.answer_readiness === 'included' || paper.answer_readiness === 'separate' }">{{ answerReadinessLabel(paper.answer_readiness) }}</text>
        </view>
      </view>
    </button>
    <button class="paper-card-favorite bare-icon favorite-control" :class="{ 'is-favorite': paper.favorite, 'favorite-pop': popping }" :disabled="busy" hover-class="control-pressed" role="button" :aria-pressed="paper.favorite" :aria-label="paper.favorite ? '取消收藏' : '收藏习题'" :title="paper.favorite ? '取消收藏' : '收藏习题'" @click="emit('favorite')"><wd-icon :name="paper.favorite ? 'heart-fill' : 'heart'" size="21px" /></button>
  </view>
</template>

<style scoped>
.paper-card { position: relative; display: flex; min-width: 0; padding: 10px 12px 10px 10px; border: 1px solid var(--lc-card-line); border-radius: 16px; background: var(--lc-card); box-shadow: var(--lc-card-shadow-soft); transition: transform .18s ease, box-shadow .18s ease; }
.paper-card:active { transform: scale(.99); }
@media (hover: hover) { .paper-card:hover { transform: translateY(-1px); box-shadow: var(--lc-card-shadow); } }
.paper-card-open { display: flex; align-items: center; gap: 12px; flex: 1; min-width: 0; margin: 0; padding: 0; border: 0; border-radius: 0; background: transparent; text-align: left; white-space: normal; line-height: 1.5; }
.paper-cover { position: relative; flex: none; width: 68px; height: 92px; padding: 4px; border-radius: 10px; background: linear-gradient(145deg, var(--subject-tint), #eef4f0); }
.cover-sheet { width: 100%; height: 100%; background: #fff; border-radius: 7px; overflow: hidden; box-shadow: 0 2px 6px #28372f14; }
.cover-locked { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; font-size: 10px; line-height: 1.3; color: var(--lc-warning); text-align: center; }
.cover-access { position: absolute; right: 4px; bottom: 4px; display: flex; line-height: 1; padding: 1px; border-radius: 6px; background: rgba(255, 255, 255, .92); box-shadow: 0 1px 3px #28372f14; }
.cover-access :deep(.access-badge) { padding: 1px 4px; border-radius: 4px; font-size: 10px; line-height: 1.4; }
.paper-card-copy { display: flex; flex-direction: column; justify-content: center; gap: 7px; flex: 1; min-width: 0; align-self: stretch; padding: 1px 0; }
.paper-card-title { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; color: var(--lc-text); font-size: 15px; line-height: 1.45; font-weight: 600; overflow-wrap: anywhere; transition: color .2s ease; }
.paper-card-foot { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 6px; min-width: 0; padding-right: 38px; }
.paper-card-meta { display: block; min-width: 0; color: var(--lc-secondary); font-size: 12px; line-height: 1.6; overflow-wrap: anywhere; }
.paper-card-foot .paper-answer { flex: none; padding: 1px 5px; font-size: 10.5px; line-height: 1.5; }
.paper-card-favorite { position: absolute; right: 6px; bottom: 4px; }
.paper-card-open.paper-card-pressed { opacity: .82; }
.paper-card-open.paper-card-pressed .paper-card-title { color: var(--lc-primary); }
@media (hover: hover) { .paper-card-open:hover .paper-card-title { color: var(--lc-primary); } }
@media (max-width: 359px) { .paper-card { padding: 9px 10px 9px 9px; }.paper-card-open { gap: 10px; }.paper-cover { width: 64px; height: 86px; }.paper-card-title { font-size: 14px; }.paper-card-foot { gap: 3px 5px; }.paper-card-meta { font-size: 11.5px; }.paper-card-foot .paper-answer { font-size: 10px; } }
@media (prefers-reduced-motion: reduce) { .paper-card, .paper-card-title { transition: none; }.paper-card:active, .paper-card:hover { transform: none; } }
</style>
