<script setup lang="ts">
import { computed, ref } from 'vue'
import { useExamStore } from '../stores/exam'
import { TYPE_DEFAULT, TYPE_NAME } from '../constants'
import type { CustomType } from '../types'

const store = useExamStore()

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
  if (typeof v === 'string') {
    store.addSection(v, TYPE_DEFAULT[v] || 4)
  } else {
    store.addSection(v.baseType, v.defaultCount)
  }
}

const readyHint = computed(() => {
  if (!store.grade || !store.subject || !store.keyword.trim()) return '先在左侧选好年级、科目和知识点'
  if (!store.sections.length) return '点击题型加入卷面'
  return ''
})
</script>

<template>
  <div class="card types-col">
    <div class="card-head" style="padding: 12px 14px;">
      <h2 style="font-size: 14px;">题型</h2>
      <span style="font-size: 11px; color: var(--ink3);">点击加入</span>
    </div>

    <div class="types-scroll">
      <div v-if="!store.grade" class="empty" style="padding: 14px 10px; margin: 0;">
        <span>先在左侧选年级</span>
      </div>
      <div v-for="([label, types], gi) in store.typeGroups" :key="gi" class="type-group" style="margin-bottom: 12px;">
        <div class="tg-head" style="margin-bottom: 6px;">{{ label }}</div>
        <div class="tg-body" style="gap: 6px;">
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
      <button class="type-add-btn" style="width: 100%;" @click="showAddType = true">＋ 自定义</button>
    </div>

    <!-- 底部：大题摘要 + 生成 -->
    <div class="types-foot">
      <div v-if="store.generateError" style="color: var(--red); font-size: 12px; margin-bottom: 6px;">{{ store.generateError }}</div>
      <div v-else-if="readyHint" style="color: var(--ink3); font-size: 12px; margin-bottom: 6px;">{{ readyHint }}</div>
      <div v-else style="font-size: 12px; color: var(--ink2); margin-bottom: 6px;">
        <b>{{ store.sections.length }}</b> 个大题 · <b>{{ store.totalQuestions }}</b> 题
        <template v-if="store.hasLoading"> · <span style="color: var(--amber);">出题中…</span></template>
        <template v-if="store.errorCount"> · <span style="color: var(--red);">{{ store.errorCount }} 个失败</span></template>
      </div>
      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
        <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink2); flex: none;" title="一次生成多份，每份题目不同">
          份数 <input class="input" type="number" min="1" max="20" style="width: 48px; padding: 4px 6px;" v-model.number="store.paperCount">
        </label>
        <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink2); cursor: pointer; flex: none;" title="在每份试卷标题后加（第X天）标记">
          <input type="checkbox" v-model="store.addDayLabel"> 第X天
        </label>
      </div>
      <button class="btn primary" style="width: 100%;" :disabled="!store.canGenerate" @click="store.generate()">
        <span v-if="store.generating"><span class="spin"></span> AI 出题中…</span>
        <span v-else>生成试卷</span>
      </button>
    </div>

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
.types-col { height: 100%; display: flex; flex-direction: column; min-height: 0; }
.types-scroll { flex: 1; overflow-y: auto; min-height: 0; padding: 12px 14px; }
.types-foot { border-top: 1px solid var(--border); padding: 10px 14px; flex: none; background: var(--surface); border-radius: 0 0 var(--radius) var(--radius); }

.type-mini {
  padding: 6px 10px;
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
