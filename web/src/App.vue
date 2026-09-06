<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useExamStore } from './stores/exam'
import StepConditions from './components/StepConditions.vue'
import StepSections from './components/StepSections.vue'
import StepResult from './components/StepResult.vue'
import AdvancedDrawer from './components/AdvancedDrawer.vue'
import LlmDialog from './components/LlmDialog.vue'

const store = useExamStore()
const showAdv = ref(false)
const showLlm = ref(false)

onMounted(() => store.init())

function gotoStep(n: 1 | 2 | 3) {
  if (n === 3 && !store.papers.length) return
  if (n === 2 && !store.grade) n = 1
  store.step = n
}
</script>

<template>
  <div class="app">
    <!-- 顶栏 -->
    <header class="topbar no-print">
      <div class="brand">
        <span class="logo">✏️</span>
        <div>
          <div class="brand-name">出题工作台</div>
          <div class="brand-slogan">AI 帮你出好每一份卷子</div>
        </div>
      </div>

      <nav class="steps-nav" aria-label="操作步骤">
        <button class="step" :class="{ on: store.step === 1, done: store.step > 1 }" @click="gotoStep(1)"><i>1</i><span>选条件</span></button>
        <span class="step-arrow"></span>
        <button class="step" :class="{ on: store.step === 2, done: store.step > 2 }" :disabled="!store.grade" @click="gotoStep(2)"><i>2</i><span>选题型</span></button>
        <span class="step-arrow"></span>
        <button class="step" :class="{ on: store.step === 3 }" :disabled="!store.papers.length" @click="gotoStep(3)"><i>3</i><span>预览导出</span></button>
      </nav>

      <div class="topbar-actions">
        <button v-if="store.papers.length" class="btn mini" @click="gotoStep(3)">查看试卷</button>
        <button class="btn mini" title="卷面风格、自定义题型等" @click="showAdv = true">高级设置</button>
        <button class="btn mini" title="LLM 接口配置" @click="showLlm = true">⚙ 模型配置</button>
      </div>
    </header>

    <!-- 步骤页 -->
    <StepConditions v-if="store.step === 1" />
    <StepSections v-else-if="store.step === 2" />
    <StepResult v-else-if="store.step === 3" />

    <!-- 弹层 -->
    <AdvancedDrawer :open="showAdv" @close="showAdv = false" />
    <LlmDialog :open="showLlm" @close="showLlm = false" />
  </div>
</template>
