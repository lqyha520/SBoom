<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useExamStore } from './stores/exam'
import LeftPanel from './components/LeftPanel.vue'
import MiddleColumn from './components/MiddleColumn.vue'
import PreviewPane from './components/PreviewPane.vue'
import StepResult from './components/StepResult.vue'
import AdvancedDrawer from './components/AdvancedDrawer.vue'
import LlmDialog from './components/LlmDialog.vue'
import MyTemplatesDialog from './components/MyTemplatesDialog.vue'

const store = useExamStore()
const showAdv = ref(false)
const showLlm = ref(false)
const showTpl = ref(false)

onMounted(() => store.init())
</script>

<template>
  <div class="app shell">
    <!-- 顶栏 -->
    <header class="topbar no-print">
      <div class="brand">
        <span class="logo">✏️</span>
        <div>
          <div class="brand-name">出题工作台</div>
          <div class="brand-slogan">AI 帮你出好每一份卷子</div>
        </div>
      </div>

      <div class="topbar-actions" style="margin-left: auto;">
        <button class="btn mini" @click="showTpl = true">📋 我的模板</button>
        <button
          v-if="store.papers.length"
          class="btn mini"
          @click="store.view === 'result' ? store.backToBuild() : (store.view = 'result')"
        >{{ store.view === 'result' ? '← 返回搭建' : '查看试卷' }}</button>
        <button class="btn mini" title="卷面风格、自定义题型等" @click="showAdv = true">高级设置</button>
        <button class="btn mini" title="LLM 接口配置" @click="showLlm = true">⚙ 模型配置</button>
      </div>
    </header>

    <!-- 单屏工作区：左条件 / 中题型+卷面 / 右 A4 预览 -->
    <main class="workbench" :class="{ 'result-only': store.view === 'result' }">
      <template v-if="store.view === 'build'">
        <LeftPanel />
        <MiddleColumn @open-templates="showTpl = true" />
        <PreviewPane />
      </template>
      <StepResult v-else />
    </main>

    <!-- 弹层 -->
    <AdvancedDrawer :open="showAdv" @close="showAdv = false" />
    <LlmDialog :open="showLlm" @close="showLlm = false" />
    <MyTemplatesDialog :open="showTpl" @close="showTpl = false" />
  </div>
</template>
