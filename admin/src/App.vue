<script setup lang="ts">
import { onMounted, ref } from 'vue'
import * as api from './api'
import LoginPage from './components/LoginPage.vue'
import Dashboard from './components/Dashboard.vue'

const user = ref<api.UserInfo | null>(null)
const ready = ref(false)
const forbidden = ref(false) // 已登录但不是管理员
const bootError = ref('')

onMounted(async () => {
  try {
    const me = await api.fetchMe()
    if (me) {
      if (me.role === 'admin') user.value = me
      else forbidden.value = true
    }
  } catch (e: any) {
    bootError.value = e?.message || '无法连接服务，请确认后端已启动'
  } finally {
    ready.value = true
  }
})

function onLogin(u: api.UserInfo) {
  user.value = u
  forbidden.value = false
}

async function onLogout() {
  user.value = null
}

async function leaveForbidden() {
  await api.logout()
  forbidden.value = false
}

function reload() {
  window.location.reload()
}
</script>

<template>
  <div v-if="!ready" class="boot">正在加载后台系统…</div>

  <Dashboard v-else-if="user" :user="user" @logout="onLogout" />

  <div v-else-if="forbidden" class="boot">
    <div class="boot-card">
      <div class="boot-icon">🚫</div>
      <div class="boot-text">当前账号不是管理员，无法使用后台系统</div>
      <div class="boot-actions">
        <a class="btn" href="/" target="_self">← 返回出题工作台</a>
        <button class="btn primary" @click="leaveForbidden">切换账号</button>
      </div>
    </div>
  </div>

  <div v-else-if="bootError" class="boot">
    <div class="boot-card">
      <div class="boot-icon">⚠️</div>
      <div class="boot-text">{{ bootError }}</div>
      <button class="btn" @click="reload">重试</button>
    </div>
  </div>

  <LoginPage v-else @logined="onLogin" />
</template>

<style scoped>
.boot {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f3f5fa;
  color: #7b869e;
  font-size: 14px;
}
.boot-card {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 12px 40px rgba(30, 42, 80, 0.12);
  padding: 36px 40px;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 14px;
  align-items: center;
}
.boot-icon { font-size: 40px; }
.boot-text { color: #2c3550; font-size: 15px; }
.boot-actions { display: flex; gap: 10px; }
</style>
