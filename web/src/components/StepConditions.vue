<script setup lang="ts">
import { computed, ref } from 'vue'
import { useExamStore } from '../stores/exam'
import { DIFF_NAME, TEMPLATES, TYPE_NAME } from '../constants'
import type { Difficulty } from '../types'

const store = useExamStore()

const grades = computed(() => Object.keys(store.available))
const customTpl = TEMPLATES.find(t => t.id === 'custom')!

/* 自定义模板表单 */
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
  }
}

function applyCustom() {
  store.saveCustomTemplate({ ...cfg.value })
  showCustomCfg.value = false
}

const canNext = computed(() => !!(store.grade && store.subject && store.keyword.trim()))

function next() {
  if (!canNext.value) return
  store.step = 2
}
</script>

<template>
  <div class="step-page">
    <!-- 难度 -->
    <div class="card" style="margin-bottom: 16px;">
      <div class="card-body" style="display: flex; align-items: center; gap: 16px; padding: 14px 20px;">
        <span style="font-size: 13px; font-weight: 600; flex: none;">难度</span>
        <div class="seg">
          <button
            v-for="(name, d) in DIFF_NAME"
            :key="d"
            :class="{ on: store.difficulty === d }"
            @click="store.difficulty = d as Difficulty"
          >{{ name }}</button>
        </div>
      </div>
    </div>

    <!-- 年级 / 科目 / 知识点 -->
    <div class="card" style="margin-bottom: 16px;">
      <div class="card-body">
        <div class="fgroup">
          <div class="fgroup-label"><i class="fi">1</i>年级</div>
          <div v-if="store.availableLoading" class="scope-empty">加载中…</div>
          <div v-else-if="store.availableError" class="scope-empty" style="color: var(--red);">{{ store.availableError }}</div>
          <div v-else class="pill-row">
            <button
              v-for="g in grades"
              :key="g"
              class="pill"
              :class="{ on: store.grade === g }"
              @click="store.selectGrade(g)"
            >{{ g }}</button>
          </div>
        </div>

        <div class="fgroup">
          <div class="fgroup-label"><i class="fi">2</i>科目</div>
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

        <div class="fgroup" style="margin-bottom: 0;">
          <div class="fgroup-label">
            <i class="fi">3</i>知识点
            <span style="font-weight: 400; color: var(--ink3); font-size: 12px;">点击下方标签可多选，也可手动输入</span>
          </div>
          <input
            class="input"
            style="max-width: 560px;"
            maxlength="100"
            placeholder="如：分数的初步认识"
            :value="store.keyword"
            @input="store.setKeyword(($event.target as HTMLInputElement).value)"
          >
          <div style="margin-top: 10px;">
            <div v-if="store.scopeLoading" class="scope-empty">知识点加载中…</div>
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
            <div v-else-if="store.grade && store.subject" class="scope-empty">该科目暂无知识点清单，可直接手动输入关键词</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 试卷标题 + 模板 -->
    <div class="card">
      <div class="card-body">
        <div class="fgroup">
          <div class="fgroup-label"><i class="fi">4</i>试卷标题 <span class="opt-tag">可选，不填自动生成</span></div>
          <input class="input" style="max-width: 560px;" maxlength="40" placeholder="如：第一单元测验卷" v-model="store.title">
        </div>
        <div class="fgroup" style="margin-bottom: 0;">
          <div class="fgroup-label"><i class="fi">5</i>卷面模板</div>
          <div class="tpl-grid">
            <button
              v-for="t in TEMPLATES"
              :key="t.id"
              class="tpl-card"
              :class="{ on: store.templateId === t.id }"
              @click="pickTemplate(t.id)"
            >
              <div class="t">{{ t.name }}</div>
              <div class="d">{{ t.tag }}</div>
            </button>
          </div>
          <div v-if="store.templateId === 'custom'" style="margin-top: 12px;">
            <button class="btn mini" @click="showCustomCfg = !showCustomCfg">
              {{ showCustomCfg ? '收起' : '展开' }}自定义模板配置
            </button>
            <div v-if="showCustomCfg" class="card" style="margin-top: 10px; padding: 14px; max-width: 560px;">
              <div class="form-row"><label>标题前缀</label><input class="input" v-model="cfg.titlePrefix" maxlength="20" placeholder="如：每日一练"></div>
              <div class="form-row"><label>标题后缀</label><input class="input" v-model="cfg.titleSuffix" maxlength="20" placeholder="如：测试卷"></div>
              <div class="form-row"><label>页脚文字</label><input class="input" v-model="cfg.footer" maxlength="40"></div>
              <div class="form-row" style="display: flex; gap: 18px; flex-wrap: wrap;">
                <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink2); cursor: pointer;">
                  <input type="checkbox" v-model="cfg.showInfoRow"> 信息栏
                </label>
                <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink2); cursor: pointer;">
                  <input type="checkbox" v-model="cfg.showNotice"> 注意事项
                </label>
                <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink2); cursor: pointer;">
                  <input type="checkbox" v-model="cfg.showScore"> 分数
                </label>
              </div>
              <button class="btn primary mini" @click="applyCustom">应用</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="step-foot">
      <span class="err" v-if="!canNext">请先选好年级、科目和知识点</span>
      <span v-else style="color: var(--ink3); font-size: 13px;">已选：{{ store.grade }} · {{ store.subject }} · {{ store.keyword }}</span>
      <button class="btn primary big" :disabled="!canNext" @click="next">下一步 · 选题型</button>
    </div>
  </div>
</template>
