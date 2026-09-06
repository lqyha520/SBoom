<script setup lang="ts">
import { computed, ref } from 'vue'
import { useExamStore } from '../stores/exam'
import { DIFF_NAME, TEMPLATES, TYPE_DEFAULT, TYPE_NAME } from '../constants'
import type { CustomType, Difficulty } from '../types'

const store = useExamStore()

const grades = computed(() => Object.keys(store.available))
const customTpl = TEMPLATES.find(t => t.id === 'custom')!

/* ── 自定义模板配置 ── */
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

/* ── 自定义题型 ── */
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

/* ── 点击题型加入卷面 ── */
function addType(v: string | CustomType) {
  if (typeof v === 'string') {
    store.addSection(v, TYPE_DEFAULT[v] || 4)
  } else {
    store.addSection(v.baseType, v.defaultCount)
  }
}

const readyHint = computed(() => {
  if (!store.grade || !store.subject || !store.keyword.trim()) return '请先选好年级、科目和知识点'
  if (!store.sections.length) return '点击题型加入卷面'
  return ''
})
</script>

<template>
  <div class="card left-panel">
    <div class="card-body left-scroll">
      <!-- 难度 -->
      <div class="fgroup" style="margin-bottom: 16px;">
        <div class="fgroup-label">难度</div>
        <div class="seg">
          <button
            v-for="(name, d) in DIFF_NAME"
            :key="d"
            :class="{ on: store.difficulty === d }"
            @click="store.difficulty = d as Difficulty"
          >{{ name }}</button>
        </div>
      </div>

      <!-- 年级 -->
      <div class="fgroup" style="margin-bottom: 16px;">
        <div class="fgroup-label">年级</div>
        <div v-if="store.availableLoading" class="scope-empty">加载中…</div>
        <div v-else-if="store.availableError" class="scope-empty" style="color: var(--red);">{{ store.availableError }}</div>
        <div v-else class="pill-row">
          <button
            v-for="g in grades"
            :key="g"
            class="pill"
            :class="{ on: store.grade === g }"
            @click="store.selectGrade(g)"
          >{{ g.replace('小学', '').replace('初中', '初') }}</button>
        </div>
      </div>

      <!-- 科目 -->
      <div class="fgroup" style="margin-bottom: 16px;">
        <div class="fgroup-label">科目</div>
        <div v-if="!store.grade" class="scope-empty">请先选择年级</div>
        <div v-else-if="!store.subjects.length" class="scope-empty">该年级暂无可选科目</div>
        <div v-else class="pill-row">
          <button
            v-for="s in store.subjects"
            :key="s"
            class="pill"
            :class="{ on: store.subject === s }"
            @click="store.selectSubject(s)"
          >{{ s }}</button>
        </div>
      </div>

      <!-- 知识点 -->
      <div class="fgroup" style="margin-bottom: 16px;">
        <div class="fgroup-label">知识点 <span style="font-weight: 400; color: var(--ink3); font-size: 11px;">可点选可输入</span></div>
        <input
          class="input"
          maxlength="100"
          placeholder="如：分数的初步认识"
          :value="store.keyword"
          @input="store.setKeyword(($event.target as HTMLInputElement).value)"
        >
        <div class="scope-box">
          <div v-if="store.scopeLoading" class="scope-empty">加载中…</div>
          <template v-else-if="store.scope">
            <div v-if="store.scope.semesters?.['上册']">
              <div class="semester-label">上册</div>
              <span
                v-for="k in store.scope.semesters['上册']"
                :key="'up' + k"
                class="tag"
                :class="{ on: store.selectedTags.includes('上册·' + k) }"
                @click="store.toggleTag('上册·' + k)"
              >{{ k }}（上）</span>
            </div>
            <div v-if="store.scope.semesters?.['下册']">
              <div class="semester-label">下册</div>
              <span
                v-for="k in store.scope.semesters['下册']"
                :key="'down' + k"
                class="tag"
                :class="{ on: store.selectedTags.includes('下册·' + k) }"
                @click="store.toggleTag('下册·' + k)"
              >{{ k }}（下）</span>
            </div>
            <span
              v-for="k in store.scope.allowed"
              :key="k"
              class="tag"
              :class="{ on: store.selectedTags.includes(k) }"
              @click="store.toggleTag(k)"
            >{{ k }}</span>
          </template>
          <div v-else-if="store.grade && store.subject" class="scope-empty">暂无知识点清单，可直接输入关键词</div>
        </div>
      </div>

      <!-- 题型 -->
      <div class="fgroup" style="margin-bottom: 16px;">
        <div class="fgroup-label">题型 <span style="font-weight: 400; color: var(--ink3); font-size: 11px;">点击加入卷面</span></div>
        <div v-for="([label, types], gi) in store.typeGroups" :key="gi" class="type-group">
          <div class="tg-head">{{ label }}</div>
          <div class="tg-body">
            <template v-if="label !== '自定义'">
              <button v-for="t in (types as string[])" :key="t" class="type-pill" @click="addType(t)">
                {{ TYPE_NAME[t] || t }}<span class="cnt">+{{ TYPE_DEFAULT[t] || 4 }}</span>
              </button>
            </template>
            <template v-else>
              <button v-for="t in (types as CustomType[])" :key="t.id" class="type-pill" @click="addType(t)">
                {{ t.name }}<span class="cnt">+{{ t.defaultCount }}</span>
              </button>
            </template>
          </div>
        </div>
        <button class="type-add-btn" style="width: 100%;" @click="showAddType = true">＋ 自定义题型</button>
      </div>

      <!-- 标题 + 模板 -->
      <div class="fgroup" style="margin-bottom: 0;">
        <div class="fgroup-label">卷面</div>
        <div class="form-row">
          <input class="input" maxlength="40" placeholder="试卷标题（可选，不填自动生成）" v-model="store.title">
        </div>
        <div style="display: flex; gap: 8px;">
          <select class="input" :value="store.templateId" @change="pickTemplate(($event.target as HTMLSelectElement).value)">
            <option v-for="t in TEMPLATES" :key="t.id" :value="t.id">{{ t.name }}（{{ t.tag }}）</option>
          </select>
          <button v-if="store.templateId === 'custom'" class="btn mini" style="flex: none;" @click="showCustomCfg = true">配置</button>
        </div>
      </div>
    </div>

    <!-- 底部生成条 -->
    <div class="left-foot">
      <div v-if="store.generateError" style="color: var(--red); font-size: 12px; margin-bottom: 8px;">{{ store.generateError }}</div>
      <div v-else-if="readyHint" style="color: var(--ink3); font-size: 12px; margin-bottom: 8px;">{{ readyHint }}</div>
      <div v-else style="font-size: 12px; color: var(--ink2); margin-bottom: 8px;">
        <b>{{ store.sections.length }}</b> 个大题 · <b>{{ store.totalQuestions }}</b> 题
        <template v-if="store.hasLoading"> · <span style="color: var(--amber);">出题中…</span></template>
        <template v-if="store.errorCount"> · <span style="color: var(--red);">{{ store.errorCount }} 个失败</span></template>
      </div>
      <div style="display: flex; align-items: center; gap: 10px;">
        <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink2); flex: none;" title="一次生成多份，每份题目不同">
          份数 <input class="input" type="number" min="1" max="20" style="width: 52px; padding: 5px 6px;" v-model.number="store.paperCount">
        </label>
        <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink2); cursor: pointer; flex: none;" title="在每份试卷标题后加（第X天）标记">
          <input type="checkbox" v-model="store.addDayLabel"> 第X天
        </label>
        <button class="btn primary" style="flex: 1;" :disabled="!store.canGenerate" @click="store.generate()">
          <span v-if="store.generating"><span class="spin"></span> AI 出题中…</span>
          <span v-else>生成试卷</span>
        </button>
      </div>
    </div>
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

    <!-- 添加自定义题型 -->
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
</template>

<style scoped>
.scope-box { margin-top: 8px; max-height: 130px; overflow-y: auto; }
</style>
