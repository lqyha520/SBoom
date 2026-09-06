<script setup lang="ts">
import { computed, ref } from 'vue'
import { useExamStore } from '../stores/exam'
import type { PaperData } from '../types'
import PaperView from './PaperView.vue'
import { useFitZoom } from '../useFitZoom'

const store = useExamStore()

/* ── 实时预览数据（搭建态：跟随大题列表） ── */
const previewPaper = computed<PaperData>(() => ({
  grade: store.grade || '',
  subject: store.subject,
  keyword: store.keyword,
  title: store.title,
  difficulty: store.difficulty,
  sections: store.sections.map(s => ({
    type: s.type,
    data: s.data || { questions: [] },
    layout: s.layout,
    _sid: s.id,
  })),
}))

const previewBox = ref<HTMLElement | null>(null)
const { zoom, manual, setManual } = useFitZoom(previewBox)
</script>

<template>
  <div class="card preview-pane">
    <div class="card-head" style="flex: none; flex-wrap: wrap; gap: 8px;">
      <h2>实时预览</h2>
      <span style="font-size: 12px; color: var(--ink3);">纸面文字可直接点击修改</span>
      <span style="margin-left: auto; display: flex; align-items: center; gap: 6px;">
        <button class="btn mini" :class="{ 'btn-primary-on': manual === 0 }" title="缩放到容器宽度" @click="setManual(0)">适应</button>
        <input
          type="range" min="25" max="180" step="5"
          :value="manual > 0 ? manual * 100 : Math.round(zoom * 100)"
          @input="setManual(parseInt(($event.target as HTMLInputElement).value) / 100)"
          style="width: 90px; accent-color: var(--primary);"
          title="缩放比例"
        >
        <span style="font-size: 11px; color: var(--ink3); width: 34px;">{{ Math.round(zoom * 100) }}%</span>
      </span>
    </div>
    <div ref="previewBox" class="preview-fill">
      <PaperView :paper="previewPaper" :template="store.template" :style="store.style" :editable="true" :zoom="zoom" />
    </div>
  </div>
</template>

<style scoped>
.preview-pane { height: 100%; display: flex; flex-direction: column; min-height: 0; }
.preview-fill { flex: 1; min-height: 0; overflow: auto; }
.btn-primary-on { border-color: var(--primary); color: var(--primary); }
</style>
