<script setup lang="ts">
import { computed, ref } from 'vue'
import { useExamStore } from '../stores/exam'
import { DIFF_NAME, TEMPLATES } from '../constants'
import type { Difficulty } from '../types'

const store = useExamStore()

const grades = computed(() => Object.keys(store.available))
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
      <div class="fgroup" style="margin-bottom: 0;">
        <div class="fgroup-label">
          知识点
          <span v-if="store.grade && store.subject" style="font-weight: 500; color: var(--primary); font-size: 12px;">{{ store.grade }}·{{ store.subject }}</span>
          <span v-else style="font-weight: 400; color: var(--ink3); font-size: 11px;">选好年级科目后显示</span>
        </div>
        <template v-if="store.grade && store.subject">
          <input
            class="input"
            maxlength="100"
            placeholder="手动输入或点选下方标签"
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
            <div v-else class="scope-empty">暂无知识点清单，可直接输入关键词</div>
          </div>
        </template>
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
  </div>
</template>

<style scoped>
.scope-box { margin-top: 8px; }
</style>
