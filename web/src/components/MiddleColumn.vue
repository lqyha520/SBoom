<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import Sortable from 'sortablejs'
import { useExamStore } from '../stores/exam'
import { TEMPLATES, TYPE_DEFAULT, TYPE_NAME } from '../constants'
import type { CustomType, Section } from '../types'

const store = useExamStore()

/* ── 卷面（标题 + 模板） ── */
const customTpl = TEMPLATES.find(t => t.id === 'custom')!
const showCustomCfg = ref(false)
const cfg = ref({
  titlePrefix: customTpl.titlePrefix,
  titleSuffix: customTpl.titleSuffix,
  footer: customTpl.footer,
  showInfoRow: customTpl.showInfoRow,
  showNotice: customTpl.showNotice,
  showScore: customTpl.showScore,
})

function pickTemplate(id: string) {
  store.setTemplate(id)
  if (id === 'custom') {
    cfg.value = {
      titlePrefix: customTpl.titlePrefix,
      titleSuffix: customTpl.titleSuffix,
      footer: customTpl.footer,
      showInfoRow: customTpl.showInfoRow,
      showNotice: customTpl.showNotice,
      showScore: customTpl.showScore,
    }
    showCustomCfg.value = true
  }
}

function applyCustom() {
  store.saveCustomTemplate({ ...cfg.value })
  showCustomCfg.value = false
}

/* ── 题型 ── */
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

function addType(v: string | CustomType) {
  if (typeof v === 'string') store.addSection(v, TYPE_DEFAULT[v] || 4)
  else store.addSection(v.baseType, v.defaultCount)
}

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

/* ── 版式弹窗 ── */
const laySec = ref<Section | null>(null)

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
  return stem.length > 14 ? stem.slice(0, 14) + '…' : stem
}

/* ── 我的模板（弹窗由 App 级组件承载，这里只发事件） ── */
const emit = defineEmits<{ (e: 'open-templates'): void }>()

const readyHint = computed(() => {
  if (!store.grade || !store.subject || !store.keyword.trim()) return '先在左侧选好条件'
  if (!store.sections.length) return '点击上方题型加入卷面'
  return ''
})
</script>

<template>
  <div class="card middle-col">
    <!-- 卷面：标题 + 模板 -->
    <div style="padding: 12px 14px 4px; flex: none;">
      <div class="fgroup-label" style="margin-bottom: 8px;">卷面</div>
      <div class="form-row" style="margin-bottom: 8px;">
        <input class="input" maxlength="40" placeholder="试卷标题（可选，不填自动生成）" v-model="store.title">
      </div>
      <div style="display: flex; gap: 6px;">
        <select class="input" :value="store.templateId" @change="pickTemplate(($event.target as HTMLSelectElement).value)">
          <option v-for="t in TEMPLATES" :key="t.id" :value="t.id">{{ t.name }}（{{ t.tag }}）</option>
        </select>
        <button v-if="store.templateId === 'custom'" class="btn mini" style="flex: none;" @click="showCustomCfg = true">配置</button>
      </div>
    </div>

    <div class="mid-divider"></div>

    <!-- 题型 -->
    <div class="mid-types">
      <div v-if="!store.grade" class="scope-empty" style="padding: 4px 0;">先在左侧选年级</div>
      <div v-for="([label, types], gi) in store.typeGroups" :key="gi" class="type-group" style="margin-bottom: 10px;">
        <div class="tg-head" style="margin-bottom: 5px;">{{ label }}</div>
        <div class="tg-body" style="gap: 5px;">
          <template v-if="label !== '自定义'">
            <button v-for="t in (types as string[])" :key="t" class="type-mini" @click="addType(t)" :title="`${TYPE_NAME[t] || t}（默认 ${TYPE_DEFAULT[t] || 4} 题）`">
              {{ TYPE_NAME[t] || t }}
            </button>
          </template>
          <template v-else>
            <button v-for="t in (types as CustomType[])" :key="t.id" class="type-mini" @click="addType(t)" :title="`${t.name}（默认 ${t.defaultCount} 题）`">
              {{ t.name }}
            </button>
          </template>
        </div>
      </div>
      <button class="type-add-btn" style="width: 100%; padding: 6px;" @click="showAddType = true">＋ 自定义题型</button>
    </div>

    <div class="mid-divider"></div>

    <!-- 卷面内容 -->
    <div class="mid-head">
      <b>卷面内容</b>
      <span style="font-size: 11px; color: var(--ink3);">⠿ 排序</span>
      <button class="btn mini" style="margin-left: auto;" @click="emit('open-templates')">我的模板</button>
    </div>

    <div class="mid-secs">
      <div v-if="!store.sections.length" class="empty" style="padding: 14px 8px;">
        <span>点击上方题型，卷面会实时出现在右侧</span>
      </div>

      <div ref="secListEl">
        <div v-for="(sec, i) in store.sections" :key="sec.id" class="sec-card" style="padding: 8px 10px; gap: 7px; flex-wrap: wrap;">
          <span class="drag-handle" title="拖拽调整顺序">⠿</span>
          <span class="sec-idx" style="width: 20px; height: 20px; font-size: 11px;">{{ i + 1 }}</span>
          <span class="sec-name" style="font-size: 12px;">{{ TYPE_NAME[sec.type] || sec.type }}</span>

          <span class="stepper">
            <button @click="store.setSectionCount(sec.id, Math.max(1, sec.count - 1))">－</button>
            <input type="number" min="1" max="99" :value="sec.count" @input="onCountInput($event, sec.id)" style="height: 24px; width: 36px;">
            <span class="unit">题</span>
            <button @click="store.setSectionCount(sec.id, Math.min(99, sec.count + 1))">＋</button>
          </span>

          <button class="btn mini" style="padding: 3px 8px; font-size: 11px;" @click="laySec = sec">版式</button>
          <button v-if="sec.status === 'error'" class="btn mini" style="padding: 3px 8px; font-size: 11px;" @click="store.retrySection(sec.id)">重试</button>
          <button class="x-btn" style="font-size: 13px; padding: 2px 5px;" title="删除" @click="store.removeSection(sec.id)">✕</button>

          <span class="sec-preview" style="flex-basis: 100%; width: auto; font-size: 11px; margin-top: 2px;">
            <span v-if="sec.status === 'loading'"><span class="spin"></span></span>
            <span v-else-if="sec.status === 'error'" class="err-txt">失败</span>
            <template v-else>{{ previewOf(sec) }}</template>
          </span>
        </div>
      </div>
    </div>

    <!-- 生成条（吸底） -->
    <div class="mid-foot">
      <div v-if="store.generateError" style="color: var(--red); font-size: 12px; margin-bottom: 6px;">{{ store.generateError }}</div>
      <div v-else-if="readyHint" style="color: var(--ink3); font-size: 12px; margin-bottom: 6px;">{{ readyHint }}</div>
      <div v-else style="font-size: 12px; color: var(--ink2); margin-bottom: 6px;">
        <b>{{ store.sections.length }}</b> 大题 · <b>{{ store.totalQuestions }}</b> 题
        <template v-if="store.hasLoading"> · <span style="color: var(--amber);">出题中…</span></template>
        <template v-if="store.errorCount"> · <span style="color: var(--red);">{{ store.errorCount }} 失败</span></template>
      </div>
      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
        <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink2); flex: none;" title="一次生成多份，每份题目不同">
          份数 <input class="input" type="number" min="1" max="20" style="width: 48px; padding: 4px 6px;" v-model.number="store.paperCount">
        </label>
        <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink2); cursor: pointer; flex: none;" title="每份标题后加（第X天）">
          <input type="checkbox" v-model="store.addDayLabel"> 第X天
        </label>
      </div>
      <button class="btn primary" style="width: 100%;" :disabled="!store.canGenerate" @click="store.generate()">
        <span v-if="store.generating"><span class="spin"></span> AI 出题中…</span>
        <span v-else>生成试卷</span>
      </button>
    </div>

    <!-- 自定义模板配置 -->
    <teleport to="body">
      <div v-if="showCustomCfg" class="modal-mask" @click.self="showCustomCfg = false">
        <div class="modal">
          <div class="modal-head"><h3>自定义模板</h3><button class="x-btn" @click="showCustomCfg = false">✕</button></div>
          <div class="modal-body">
            <div class="form-row"><label>标题前缀</label><input class="input" v-model="cfg.titlePrefix" maxlength="20" placeholder="如：每日一练"></div>
            <div class="form-row"><label>标题后缀</label><input class="input" v-model="cfg.titleSuffix" maxlength="20" placeholder="如：测试卷"></div>
            <div class="form-row"><label>页脚文字</label><input class="input" v-model="cfg.footer" maxlength="40"></div>
            <div class="form-row" style="display: flex; gap: 18px; flex-wrap: wrap;">
              <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink2); cursor: pointer;"><input type="checkbox" v-model="cfg.showInfoRow"> 信息栏</label>
              <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink2); cursor: pointer;"><input type="checkbox" v-model="cfg.showNotice"> 注意事项</label>
              <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink2); cursor: pointer;"><input type="checkbox" v-model="cfg.showScore"> 分数</label>
            </div>
          </div>
          <div class="modal-foot">
            <button class="btn" @click="showCustomCfg = false">取消</button>
            <button class="btn primary" @click="applyCustom">应用</button>
          </div>
        </div>
      </div>
    </teleport>

    <!-- 版式弹窗 -->
    <teleport to="body">
      <div v-if="laySec" class="modal-mask" @click.self="laySec = null">
        <div class="modal" style="width: 360px;">
          <div class="modal-head">
            <h3>版式 · {{ TYPE_NAME[laySec.type] || laySec.type }}</h3>
            <button class="x-btn" @click="laySec = null">✕</button>
          </div>
          <div class="modal-body">
            <div class="lay-row"><em>分栏</em>
              <button v-for="c in [1, 2, 3, 4, 5]" :key="'q' + c" class="lay-opt" :class="{ on: laySec.layout.qCols === c }" @click="laySec!.layout.qCols = c">{{ c }}</button>
            </div>
            <div class="lay-row"><em>选项</em>
              <button v-for="c in [1, 2, 3, 4, 5]" :key="'o' + c" class="lay-opt" :class="{ on: laySec.layout.optCols === c }" @click="laySec!.layout.optCols = c">{{ c }}</button>
            </div>
            <div class="lay-row"><em>表格</em>
              <button class="lay-opt" :class="{ on: laySec.layout.tableBorder === 'none' }" @click="laySec!.layout.tableBorder = 'none'">无</button>
              <button class="lay-opt" :class="{ on: laySec.layout.tableBorder === 'solid' }" @click="laySec!.layout.tableBorder = 'solid'">实线</button>
              <button class="lay-opt" :class="{ on: laySec.layout.tableBorder === 'dashed' }" @click="laySec!.layout.tableBorder = 'dashed'">虚线</button>
            </div>
            <div class="lay-row"><em>字号</em>
              <button class="lay-opt" :class="{ on: !laySec.layout.fontSize }" @click="laySec!.layout.fontSize = ''">默认</button>
              <button v-for="fs in ['9pt', '10pt', '10.5pt', '11pt', '12pt']" :key="fs" class="lay-opt" :class="{ on: laySec.layout.fontSize === fs }" @click="laySec!.layout.fontSize = fs">{{ fs.replace('pt', '') }}</button>
            </div>
            <div class="lay-row" style="margin-bottom: 0;"><em>题号</em>
              <button class="lay-opt" :class="{ on: laySec.layout.showNo }" @click="laySec!.layout.showNo = true">显示</button>
              <button class="lay-opt" :class="{ on: !laySec.layout.showNo }" @click="laySec!.layout.showNo = false">隐藏</button>
            </div>
          </div>
          <div class="modal-foot">
            <button class="btn primary" @click="laySec = null">完成</button>
          </div>
        </div>
      </div>
    </teleport>

    <!-- 添加自定义题型 -->
    <teleport to="body">
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
    </teleport>
  </div>
</template>

<style scoped>
.middle-col { height: 100%; display: flex; flex-direction: column; min-height: 0; }
.mid-types { flex: none; max-height: 36%; overflow-y: auto; padding: 10px 14px 6px; }
.mid-divider { border-top: 1px solid var(--border); margin: 0 14px; flex: none; }
.mid-head { display: flex; align-items: center; gap: 6px; padding: 10px 14px 4px; font-size: 13px; flex: none; }
.mid-secs { flex: 1; overflow-y: auto; min-height: 0; padding: 8px 14px; }
.mid-foot { border-top: 1px solid var(--border); padding: 10px 14px; flex: none; background: var(--surface); border-radius: 0 0 var(--radius) var(--radius); }

.type-mini {
  padding: 5px 9px;
  border: 1px solid var(--border2);
  border-radius: 6px;
  background: var(--surface);
  color: var(--ink2);
  font-size: 12px;
  cursor: pointer;
  transition: all .12s;
  white-space: nowrap;
}
.type-mini:hover { border-color: var(--primary); color: var(--primary); background: var(--primary-light); }
</style>
