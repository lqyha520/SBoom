<script setup lang="ts">
import { lazyComponent } from '../../shared/async-component'
import { onMounted, onUnmounted, ref } from 'vue'
import { zh_cn } from '@nuxt/ui/locale'
import * as api from './api'
import LoginPage from './components/LoginPage.vue'

const ReauthDialog = lazyComponent(() => import('./components/ReauthDialog.vue'))
const Dashboard = lazyComponent(() => import('./components/Dashboard.vue'))
const user = ref<api.UserInfo | null>(null)
const ready = ref(false)
const forbidden = ref(false)
const bootError = ref('')
const reauth = ref(false)
const workspaceEpoch = ref(0)

function onAuthExpired() {
  api.bindAdminAccount(null)
  reauth.value = !!user.value
  forbidden.value = false
}
function onAccountChanged() {
  onAuthExpired()
  user.value = null
  reauth.value = false
  workspaceEpoch.value++
  bootError.value = '登录账号已变化，请重新加载后继续操作'
}
function storageChanged(event: StorageEvent) {
  if (user.value && (event.key === null || event.key === api.ACCOUNT_KEY && event.newValue !== String(user.value.id))) api.accountChanged()
}
function logined(value: api.UserInfo) {
  if (user.value && user.value.id !== value.id) workspaceEpoch.value++
  api.bindAdminAccount(value.id); user.value = value.role === 'admin' ? value : null
  reauth.value = false; forbidden.value = value.role !== 'admin'; bootError.value = ''
}
function onForbidden() { reauth.value = false; user.value = null; forbidden.value = true }
async function boot() {
  ready.value = false
  bootError.value = ''
  try {
    const me = await api.fetchMe()
    api.bindAdminAccount(me?.id ?? null)
    user.value = me?.role === 'admin' ? me : null
    forbidden.value = !!me && me.role !== 'admin'
  } catch (e: unknown) {
    bootError.value = e instanceof Error ? e.message : '无法连接服务'
  } finally { ready.value = true }
}
async function leaveForbidden() {
  bootError.value = ''
  try { await api.logout(); forbidden.value = false }
  catch (error) { bootError.value = error instanceof Error ? error.message : '退出失败，请重试' }
}
onMounted(() => {
  window.addEventListener(api.FORBIDDEN_EVENT, onForbidden)
  window.addEventListener(api.AUTH_EXPIRED_EVENT, onAuthExpired)
  window.addEventListener(api.ACCOUNT_CHANGED_EVENT, onAccountChanged)
  window.addEventListener('storage', storageChanged)
  void boot()
})
onUnmounted(() => {
  window.removeEventListener(api.FORBIDDEN_EVENT, onForbidden)
  window.removeEventListener(api.AUTH_EXPIRED_EVENT, onAuthExpired)
  window.removeEventListener(api.ACCOUNT_CHANGED_EVENT, onAccountChanged)
  window.removeEventListener('storage', storageChanged)
})
</script>

<template>
  <UApp :locale="zh_cn">
    <div v-if="!ready" class="loading-screen" role="status">
      <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin text-primary" />
      <p>正在加载管理后台</p>
    </div>
    <Dashboard v-else-if="user" :key="workspaceEpoch" :user="user" :inert="reauth || undefined" @logout="user = null" />
    <div v-else-if="forbidden" class="loading-screen">
      <UIcon name="i-lucide-shield-x" class="size-9 text-warning" />
      <h1 class="text-lg font-semibold">当前账号没有管理员权限</h1>
      <UAlert v-if="bootError" :title="bootError" color="error" role="alert" />
      <div class="actions-row"><UButton href="/" color="neutral" variant="outline" label="返回工作台" /><UButton label="切换账号" @click="leaveForbidden" /></div>
    </div>
    <div v-else-if="bootError" class="loading-screen p-6">
      <UAlert :title="bootError" color="error" variant="soft" class="max-w-md" />
      <UButton icon="i-lucide-refresh-cw" label="重试" @click="boot" />
    </div>
    <LoginPage v-else @logined="logined" />
    <ReauthDialog v-if="reauth" @logined="logined" />
  </UApp>
</template>
