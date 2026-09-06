<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import Sortable from 'sortablejs'
import { useExamStore } from '../stores/exam'
import { TYPE_DEFAULT, TYPE_NAME } from '../constants'
import type { CustomType, PaperData } from '../types'
import PaperView from './PaperView.vue'
import { useFitZoom } from '../useFitZoom'

const store = useExamStore()

/* ── 实时预览数据 ── */
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

/* ── 大题拖拽排序 ── */
const secListEl = ref<HTMLElement | null>(null)
let sortable: Sortable | null = null
onMounted(() => {
  if (secListEl.value) {
    sortable = new Sortable(secListEl.value, {
      animation: 150,
      handle: '.drag-handle',
      draggable: '.sec-card',
      ghostClass: 'sortable-ghost',
      onEnd: e => {
        if (e.oldIndex != null && e.newIndex != null) store.moveSection(e.oldIndex, e.newIndex)
      },
    })
  }
})
onBeforeUnmount(() => sortable?.destroy())

/* ── 版式弹层 ── */
const openLayId = ref('')
function toggleLay(e: Event, id: string) {
  e.stopPropagation()
  openLayId.value = openLayId.value === id ? '' : id
}
function onDocClick() {
  openLayId.value = ''
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))

/* ── 数量编辑（防抖） ── */
let cntTimer: ReturnType<typeof setTimeout> | null = null
function onCountInput(e: Event, id: string) {
  if (cntTimer) clearTimeout(cntTimer)
  const raw = (e.target as HTMLInputElement).value
  cntTimer = setTimeout(() => {
    const n = Math.min(99, Math.max(1, parseInt(raw) || 1))
    ;(e.target as HTMLInputElement).value = String(n)
    store.setSectionCount(id, n)
  }, 600)
}

const previewOf = (sec: any): string => {
  const q = sec.data?.questions?.[0]
  if (!q) return ''
  const stem = String(q.stem || '').replace(/<[^>]*>/g, '')
  return stem.length > 20 ? stem.slice(0, 20) + '…' : stem
}

/* ── 我的模板 ── */
const showMyTpl = ref(false)
const saveTplName = ref('')
function saveTpl() {
  const name = saveTplName.value.trim()
  if (!name || !store.sections.length) return
  store.saveMyTemplate(name)
  saveTplName.value = ''
}
</script>

<template>
  <div class="build-view">
    <!-- 大题列表（紧凑） -->
    <div class="card secs-card">
      <div class="card-head">
        <h2>卷面内容</h2>
        <span style="font-size: 12px; color: var(--ink3);">⠿ 拖动排序</span>
        <span style="margin-left: auto;">
          <button class="btn mini" :disabled="!store.sections.length && !store.myTemplates.length" @click="showMyTpl = !showMyTpl">我的模板</button>
        </span>
      </div>

      <!-- 我的模板下拉 -->
      <div v-if="showMyTpl" style="padding: 10px 20px 0;">
        <div class="card" style="padding: 12px;">
          <div style="display: flex; gap: 8px; margin-bottom: 10px;">
            <input class="input" v-model="saveTplName" placeholder="保存当前卷面为模板（输入名称）">
            <button class="btn primary mini" :disabled="!saveTplName.trim() || !store.sections.length" @click="saveTpl">保存</button>
          </div>
          <div v-if="!store.myTemplates.length" style="font-size: 12px; color: var(--ink3);">还没有保存的模板</div>
          <div v-for="t in store.myTemplates" :key="t.name" style="display: flex; align-items: center; gap: 8px; padding: 6px 0; border-top: 1px solid var(--border);">
            <b style="font-size: 13px;">{{ t.name }}</b>
            <span style="font-size: 12px; color: var(--ink3); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
              {{ t.grade }}{{ t.subject }}：{{ t.cards.map(c => `${TYPE_NAME[c.type] || c.type}×${c.count}`).join('、') }}
            </span>
            <button class="btn mini primary" @click="store.loadMyTemplate(t.name); showMyTpl = false">使用</button>
            <button class="btn mini danger" @click="store.deleteMyTemplate(t.name)">删除</button>
          </div>
        </div>
      </div>

      <div class="sec-scroll">
        <div v-if="!store.sections.length" class="empty" style="padding: 18px;">
          <b>卷面还是空的</b>
          <span>点击左侧题型卡片，题目会实时出现在下面的预览里</span>
        </div>

        <div ref="secListEl">
          <div v-for="(sec, i) in store.sections" :key="sec.id" class="sec-card" @click.stop>
            <span class="drag-handle" title="拖拽调整顺序">⠿</span>
            <span class="sec-idx">{{ i + 1 }}</span>
            <span class="sec-name">{{ TYPE_NAME[sec.type] || sec.type }}</span>

            <span class="stepper">
              <button title="减少一题" @click="store.setSectionCount(sec.id, Math.max(1, sec.count - 1))">－</button>
              <input type="number" min="1" max="99" :value="sec.count" @input="onCountInput($event, sec.id)">
              <span class="unit">题</span>
              <button title="增加一题" @click="store.setSectionCount(sec.id, Math.min(99, sec.count + 1))">＋</button>
            </span>

            <span class="lay-wrap" :class="{ open: openLayId === sec.id }">
              <button class="lay-btn" @click="toggleLay($event, sec.id)">版式</button>
              <div class="lay-pop" @click.stop>
                <div class="lay-row"><em>分栏</em>
                  <button v-for="c in [1, 2, 3, 4, 5]" :key="'q' + c" class="lay-opt" :class="{ on: sec.layout.qCols === c }" @click="sec.layout.qCols = c">{{ c }}</button>
                </div>
                <div class="lay-row"><em>选项</em>
                  <button v-for="c in [1, 2, 3, 4, 5]" :key="'o' + c" class="lay-opt" :class="{ on: sec.layout.optCols === c }" @click="sec.layout.optCols = c">{{ c }}</button>
                </div>
                <div class="lay-row"><em>表格</em>
                  <button class="lay-opt" :class="{ on: sec.layout.tableBorder === 'none' }" @click="sec.layout.tableBorder = 'none'">无</button>
                  <button class="lay-opt" :class="{ on: sec.layout.tableBorder === 'solid' }" @click="sec.layout.tableBorder = 'solid'">实线</button>
                  <button class="lay-opt" :class="{ on: sec.layout.tableBorder === 'dashed' }" @click="sec.layout.tableBorder = 'dashed'">虚线</button>
                </div>
                <div class="lay-row"><em>字号</em>
                  <button class="lay-opt" :class="{ on: !sec.layout.fontSize }" @click="sec.layout.fontSize = ''">默认</button>
                  <button v-for="fs in ['9pt', '10pt', '10.5pt', '11pt', '12pt']" :key="fs" class="lay-opt" :class="{ on: sec.layout.fontSize === fs }" @click="sec.layout.fontSize = fs">{{ fs.replace('pt', '') }}</button>
                </div>
                <div class="lay-row"><em>题号</em>
                  <button class="lay-opt" :class="{ on: sec.layout.showNo }" @click="sec.layout.showNo = true">显示</button>
                  <button class="lay-opt" :class="{ on: !sec.layout.showNo }" @click="sec.layout.showNo = false">隐藏</button>
                </div>
              </div>
            </span>

            <button v-if="sec.status === 'error'" class="btn mini" @click="store.retrySection(sec.id)">重试</button>
            <button class="x-btn" title="删除" @click="store.removeSection(sec.id)">✕</button>

            <span class="sec-preview" style="flex-basis: auto; margin-top: 0; width: 0;">
              <span v-if="sec.status === 'loading'" class="loading-txt"><span class="spin"></span></span>
              <span v-else-if="sec.status === 'error'" class="err-txt">失败</span>
              <template v-else>{{ previewOf(sec) }}</template>
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- A4 实时预览 -->
    <div class="card preview-card">
      <div class="card-head">
        <h2>实时预览</h2>
        <span style="font-size: 12px; color: var(--ink3);">占位题仅供参考，点「生成试卷」后由 AI 替换</span>
      </div>
      <div ref="previewBox" class="preview-scroll">
        <PaperView :paper="previewPaper" :template="store.template" :style="store.style" :editable="false" :zoom="zoom" />
      </div>
    </div>
  </div>
</template>
