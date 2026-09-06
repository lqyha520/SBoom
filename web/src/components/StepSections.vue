<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import Sortable from 'sortablejs'
import { useExamStore } from '../stores/exam'
import { TYPE_DEFAULT, TYPE_NAME } from '../constants'
import type { CustomType, PaperData } from '../types'
import PaperView from './PaperView.vue'

const store = useExamStore()

/* ── 实时预览：搭建区当前状态 → 试卷数据 ── */
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

/* ── 自定义题型弹窗 ── */
const showAddType = ref(false)
const ctName = ref('')
const ctBase = ref('fill_blank')
const ctCount = ref(5)

function submitCustomType() {
  const name = ctName.value.trim()
  if (!name) return
  store.addCustomType(name, ctBase.value, Math.min(99, Math.max(1, ctCount.value || 5)))
  ctName.value = ''
  showAddType.value = false
}

/* ── 点击题型加入 ── */
function addType(v: string | CustomType) {
  if (typeof v === 'string') {
    store.addSection(v, TYPE_DEFAULT[v] || 4)
  } else {
    store.addSection(v.baseType, v.defaultCount)
  }
}

/* ── 大题列表拖拽排序 ── */
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
function toggleLay(id: string) {
  openLayId.value = openLayId.value === id ? '' : id
}
function closeLay() {
  openLayId.value = ''
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
function onDocClick() {
  closeLay()
}

/* ── 数量编辑 ── */
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
  return stem.length > 26 ? stem.slice(0, 26) + '…' : stem
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
function useTpl(name: string) {
  store.loadMyTemplate(name)
  showMyTpl.value = false
}

async function generate() {
  await store.generate()
}
</script>

<template>
  <div class="step-page" @click="closeLay">
    <div style="display: grid; grid-template-columns: 340px 1fr; gap: 16px; align-items: start;">
      <!-- 左：题型 -->
      <div class="card">
        <div class="card-head"><h2>选择题型</h2></div>
        <div class="card-body">
          <div v-for="([label, types], gi) in store.typeGroups" :key="gi" class="type-group">
            <div class="tg-head">{{ label }}</div>
            <div class="tg-body">
              <template v-if="label !== '自定义'">
                <button
                  v-for="t in (types as string[])"
                  :key="t"
                  class="type-pill"
                  @click.stop="addType(t)"
                >{{ TYPE_NAME[t] || t }}<span class="cnt">+{{ TYPE_DEFAULT[t] || 4 }}题</span></button>
              </template>
              <template v-else>
                <button
                  v-for="t in (types as CustomType[])"
                  :key="t.id"
                  class="type-pill"
                  @click.stop="addType(t)"
                >{{ t.name }}<span class="cnt">+{{ t.defaultCount }}题</span></button>
              </template>
            </div>
          </div>
          <button class="type-add-btn" @click.stop="showAddType = true">＋ 添加自定义题型</button>
        </div>
      </div>

      <!-- 右：大题列表 -->
      <div class="card">
        <div class="card-head">
          <h2>卷面内容</h2>
          <span style="font-size: 12px; color: var(--ink3);">拖动 ⠿ 可调整顺序</span>
          <span style="margin-left: auto; display: flex; gap: 8px;">
            <button class="btn mini" :disabled="!store.sections.length" @click.stop="showMyTpl = !showMyTpl">我的模板</button>
          </span>
        </div>
        <div class="card-body">
          <!-- 我的模板下拉 -->
          <div v-if="showMyTpl" class="card" style="padding: 12px; margin-bottom: 14px;">
            <div style="display: flex; gap: 8px; margin-bottom: 10px;">
              <input class="input" v-model="saveTplName" placeholder="保存当前卷面为模板（输入名称）" @click.stop>
              <button class="btn primary mini" :disabled="!saveTplName.trim() || !store.sections.length" @click.stop="saveTpl">保存</button>
            </div>
            <div v-if="!store.myTemplates.length" style="font-size: 12px; color: var(--ink3);">还没有保存的模板</div>
            <div v-for="t in store.myTemplates" :key="t.name" style="display: flex; align-items: center; gap: 8px; padding: 6px 0; border-top: 1px solid var(--border);">
              <b style="font-size: 13px;">{{ t.name }}</b>
              <span style="font-size: 12px; color: var(--ink3); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{ t.grade }}{{ t.subject }}：{{ t.cards.map(c => `${TYPE_NAME[c.type] || c.type}×${c.count}`).join('、') }}
              </span>
              <button class="btn mini primary" @click.stop="useTpl(t.name)">使用</button>
              <button class="btn mini danger" @click.stop="store.deleteMyTemplate(t.name)">删除</button>
            </div>
          </div>

          <div v-if="!store.sections.length" class="empty">
            <b>卷面还是空的</b>
            <span>点击左侧题型卡片，题目会加进这里<br>生成时 AI 会替换为真实题目</span>
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

              <!-- 版式弹层 -->
              <span class="lay-wrap" :class="{ open: openLayId === sec.id }">
                <button class="lay-btn" @click.stop="toggleLay(sec.id)">版式</button>
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

              <div class="sec-preview" style="flex-basis: 100%; margin-top: 8px;">
                <span v-if="sec.status === 'loading'" class="loading-txt"><span class="spin"></span> 正在出题…</span>
                <span v-else-if="sec.status === 'error'" class="err-txt">{{ sec.error }}，点击"重试"</span>
                <template v-else>{{ sec.data?.questions?.length || 0 }} 题 · {{ previewOf(sec) }}</template>
              </div>
            </div>
          </div>

          <!-- 汇总 + 生成 -->
          <div class="summary-bar" style="margin-top: 14px;">
            <template v-if="store.sections.length">
              <span>共 <b>{{ store.sections.length }}</b> 个大题</span>
              <span><b>{{ store.totalQuestions }}</b> 道题</span>
              <span v-if="store.hasLoading" class="loading-txt">出题中…</span>
              <span v-if="store.errorCount" class="err-txt">{{ store.errorCount }} 个失败</span>
              <span v-if="!store.hasLoading && !store.errorCount" class="ok-txt">全部就绪</span>
            </template>
            <span v-else>还没有安排任何大题</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 生成条（吸底，滚动时始终可见） -->
    <div class="card" style="margin-top: 16px; position: sticky; bottom: 12px; z-index: 60;">
      <div class="card-body" style="display: flex; align-items: center; gap: 16px; flex-wrap: wrap;">
        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--ink2);" title="一次生成多份，每份题目不同">
          份数
          <input class="input" type="number" min="1" max="20" style="width: 64px;" v-model.number="store.paperCount">
        </label>
        <label style="display: flex; align-items: center; gap: 4px; font-size: 13px; color: var(--ink2); cursor: pointer;" title="在每份试卷标题后加（第X天）标记">
          <input type="checkbox" v-model="store.addDayLabel"> 标题加（第X天）
        </label>
        <span style="flex: 1;"></span>
        <button class="btn" @click="store.step = 1">上一步</button>
        <button class="btn primary big" :disabled="!store.canGenerate" @click="generate">
          <span v-if="store.generating"><span class="spin"></span> AI 出题中…（约 3~15 秒）</span>
          <span v-else>生成试卷</span>
        </button>
      </div>
      <div v-if="store.generateError" style="padding: 0 20px 14px; color: var(--red); font-size: 13px;">{{ store.generateError }}</div>
    </div>

    <!-- 实时 A4 预览 -->
    <div v-if="store.sections.length" class="card" style="margin-top: 16px;">
      <div class="card-head">
        <h2>试卷实时预览</h2>
        <span style="font-size: 12px; color: var(--ink3);">当前为排版占位题，点「生成试卷」后由 AI 替换为真实题目</span>
      </div>
      <div class="card-body" style="overflow-x: auto;">
        <PaperView :paper="previewPaper" :template="store.template" :style="store.style" :editable="false" />
      </div>
    </div>

    <!-- 添加自定义题型弹窗 -->
    <div v-if="showAddType" class="modal-mask" @click.self="showAddType = false">
      <div class="modal">
        <div class="modal-head"><h3>添加自定义题型</h3><button class="x-btn" @click="showAddType = false">✕</button></div>
        <div class="modal-body">
          <div class="form-row">
            <label>题型名称（如：看图写话 / 口算天天练）</label>
            <input class="input" v-model="ctName" maxlength="10" placeholder="题型名称">
          </div>
          <div class="form-row">
            <label>生成方式（决定 AI 怎么出题）</label>
            <select class="input" v-model="ctBase">
              <option value="fill_blank">填空式（题干留空填写）</option>
              <option value="number_split">数的分成（数字拆分树状图）</option>
              <option value="compare">比大小（填 &gt; &lt; =）</option>
              <option value="quiz">选择式（四个选项选答案）</option>
              <option value="challenge">闯关式（由易到难多道题）</option>
              <option value="reading">阅读式（短文+理解问题）</option>
              <option value="match_pair">连线式（左右配对）</option>
            </select>
          </div>
          <div class="form-row">
            <label>默认题数</label>
            <input class="input" type="number" min="1" max="99" v-model.number="ctCount" style="width: 90px;">
          </div>
        </div>
        <div class="modal-foot">
          <button class="btn" @click="showAddType = false">取消</button>
          <button class="btn primary" @click="submitCustomType">添加</button>
        </div>
      </div>
    </div>
  </div>
</template>
