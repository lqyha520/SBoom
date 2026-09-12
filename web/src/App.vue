<script setup lang="ts">
import { defineAsyncComponent, onMounted, ref } from 'vue'
import { useExamStore } from './stores/exam'
import { useAuthStore } from './stores/auth'
import LeftPanel from './components/LeftPanel.vue'
import MiddleColumn from './components/MiddleColumn.vue'
import PreviewPane from './components/PreviewPane.vue'
import StepResult from './components/StepResult.vue'
import AdvancedDrawer from './components/AdvancedDrawer.vue'
import MyTemplatesDialog from './components/MyTemplatesDialog.vue'

// 登录页仅在未登录时才需要，异步加载不进主包
const LoginView = defineAsyncComponent(() => import('./components/LoginView.vue'))

const store = useExamStore()
const auth = useAuthStore()
const showAdv = ref(false)
const showTpl = ref(false)

onMounted(() => { if (auth.user) store.init() })
</script>

<template>
  <!-- 启动中：解析会话 -->
  <div v-if="!auth.ready" class="boot-splash">正在加载…</div>

  <!-- 未登录：登录/注册页 -->
  <LoginView v-else-if="!auth.user" />

  <!-- 已登录：工作台 -->
  <div v-else class="app shell">
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
        <a v-if="auth.user?.role === 'admin'" class="btn mini" href="/admin" target="_self" title="后台管理系统（独立入口）">🛠 后台管理</a>
        <span class="user-chip" :title="`当前用户：${auth.user?.username ?? ''}`">👤 {{ auth.user?.username }}</span>
        <button class="btn mini" title="退出登录" @click="auth.logout()">退出</button>
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
    <MyTemplatesDialog :open="showTpl" @close="showTpl = false" />
  </div>
</template>

<style scoped>
.boot-splash {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #7b869e;
  font-size: 14px;
  background: var(--bg-page, #f3f5fa);
}
.user-chip {
  font-size: 13px;
  color: #44506b;
  background: #eef1f9;
  border-radius: 999px;
  padding: 4px 12px;
  margin-left: 4px;
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
