<script setup lang="ts">
import { computed, ref } from 'vue'
import { useExamStore } from '../stores/exam'
import type { PaperData } from '../types'
import PaperView from './PaperView.vue'
import FormatBar from './FormatBar.vue'
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
  hiddenElements: [...store.hiddenElements],
} as PaperData))

const previewBox = ref<HTMLElement | null>(null)
const paperViewEl = ref<InstanceType<typeof PaperView> | null>(null)
const { zoom, manual, setManual } = useFitZoom(previewBox)

/* ── 排版模式 ── */
const layoutMode = ref(false)
const showSaveTpl = ref(false)
const saveName = ref('')

function toggleLayout() {
  if (layoutMode.value) {
    // 完成：DOM 顺序/删除/编辑回写，并同步回 store（previewPaper 是 computed 快照）
    const newSections = paperViewEl.value?.applyLayout()
    if (newSections?.length) store.syncSections(newSections)
    layoutMode.value = false
    // 排版成果值得留存：询问是否保存为模板
    showSaveTpl.value = true
  } else {
    layoutMode.value = true
  }
}
function cancelLayout() {
  layoutMode.value = false
  paperViewEl.value?.repaginate()
}

function confirmSaveTpl() {
  const name = saveName.value.trim()
  if (name) store.saveMyTemplate(name)
  saveName.value = ''
  showSaveTpl.value = false
}
</script>

<template>
  <div class="card preview-pane">
    <div class="card-head" style="flex: none; flex-wrap: wrap; gap: 8px;">
      <h2 style="flex: none;">实时预览</h2>

      <template v-if="!layoutMode">
        <span style="font-size: 12px; color: var(--ink3); flex: none;">纸面文字可直接点击修改</span>
        <FormatBar />
        <span style="margin-left: auto; display: flex; align-items: center; gap: 6px;">
          <button class="btn mini" :class="{ 'btn-primary-on': manual === 0 }" title="缩放到容器宽度" @click="setManual(0)">适应</button>
          <input
            type="range" min="25" max="100" step="5"
            :value="manual > 0 ? manual * 100 : Math.round(zoom * 100)"
            @input="setManual(parseInt(($event.target as HTMLInputElement).value) / 100)"
            style="width: 90px; accent-color: var(--primary);"
            title="缩放比例"
          >
          <span style="font-size: 11px; color: var(--ink3); width: 36px;">{{ Math.round(zoom * 100) }}%</span>
          <button class="btn mini" @click="toggleLayout">✏️ 排版模式</button>
        </span>
      </template>

      <template v-else>
        <span style="font-size: 12px; color: var(--amber); flex: 1;">⠿ 拖动排序 · 点击编辑 · ✕ 删除 · ⤡ 调整大小</span>
        <button class="btn mini primary" @click="toggleLayout">✓ 完成排版</button>
        <button class="btn mini" @click="cancelLayout">取消</button>
      </template>
    </div>
    <div ref="previewBox" class="preview-fill">
      <PaperView
        ref="paperViewEl"
        :paper="previewPaper"
        :template="store.template"
        :style="store.style"
        :editable="true"
        :layout-mode="layoutMode"
        :zoom="zoom"
        @toggle-element="store.toggleHiddenElement($event)"
      />
    </div>

    <!-- 完成排版后：保存为模板询问 -->
    <teleport to="body">
      <div v-if="showSaveTpl" class="modal-mask" @click.self="showSaveTpl = false">
        <div class="modal" style="width: 400px;">
          <div class="modal-head">
            <h3>排版已应用</h3>
            <button class="x-btn" @click="showSaveTpl = false">✕</button>
          </div>
          <div class="modal-body">
            <p style="font-size: 13px; color: var(--ink2); margin-bottom: 12px; line-height: 1.7;">
              排版结果已同步到卷面。要不要把这套<b>排版 + 题目样式 + 装饰风格</b>保存为模板？<br>
              <span style="font-size: 12px; color: var(--ink3);">下次从「我的模板」一键导入，原样恢复。</span>
            </p>
            <input class="input" v-model="saveName" maxlength="20" placeholder="模板名称，如：三年级口算每日一练" @keyup.enter="confirmSaveTpl">
          </div>
          <div class="modal-foot">
            <button class="btn" @click="showSaveTpl = false">暂不保存</button>
            <button class="btn primary" :disabled="!saveName.trim()" @click="confirmSaveTpl">保存模板</button>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<style scoped>
.preview-pane { height: 100%; display: flex; flex-direction: column; min-height: 0; }
.preview-fill { flex: 1; min-height: 0; overflow: auto; }
.btn-primary-on { border-color: var(--primary); color: var(--primary); }
</style>
