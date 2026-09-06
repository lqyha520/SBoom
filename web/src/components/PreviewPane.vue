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
const zoom = useFitZoom(previewBox)
</script>

<template>
  <div class="card preview-pane">
    <div class="card-head" style="flex: none;">
      <h2>实时预览</h2>
      <span style="font-size: 12px; color: var(--ink3);">纸面文字可直接点击修改 · 生成后由 AI 替换为真实题目</span>
    </div>
    <div ref="previewBox" class="preview-fill">
      <PaperView :paper="previewPaper" :template="store.template" :style="store.style" :editable="true" :zoom="zoom" />
    </div>
  </div>
</template>

<style scoped>
.preview-pane { height: 100%; display: flex; flex-direction: column; min-height: 0; }
.preview-fill { flex: 1; min-height: 0; overflow: auto; display: flex; justify-content: center; }
</style>
