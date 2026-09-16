<script setup lang="ts">
import { ref, watch } from 'vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const mode = ref('login')
const username = ref('')
const password = ref('')
const confirmation = ref('')
const visible = ref(false)
const busy = ref(false)
const error = ref('')
const modes = [{ label: '登录', value: 'login' }, { label: '注册', value: 'register' }]
watch(mode, () => { error.value = ''; confirmation.value = '' })
async function submit() {
  if (busy.value) return
  error.value = ''
  const name = username.value.trim()
  if (!name || !password.value) { error.value = '请输入用户名和密码'; return }
  if (mode.value === 'register') {
    if (password.value.length < 6) { error.value = '密码至少需要 6 位'; return }
    if (password.value !== confirmation.value) { error.value = '两次输入的密码不一致'; return }
  }
  busy.value = true
  try {
    if (mode.value === 'login') await auth.login(name, password.value)
    else await auth.register(name, password.value)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '登录失败，请重试'
    if (mode.value === 'login' && error.value.includes('用户名或密码错误')) {
      error.value += '；还没有账号？切换到上方「注册」'
    }
  } finally { busy.value = false }
}
</script>

<template>
  <div class="auth-page">
    <header class="auth-header">
      <div class="brand"><span class="brand-mark"><UIcon name="i-lucide-notebook-pen" class="size-5" /></span><div><div class="brand-name">出题工作台</div><div class="brand-caption">Learning Coach</div></div></div>
      <UButton href="/admin/" icon="i-lucide-shield-check" label="后台管理" color="neutral" variant="ghost" size="sm" />
    </header>
    <main class="auth-main">
      <div class="auth-form">
        <div class="auth-emblem"><UIcon name="i-lucide-book-open-check" class="size-6" /></div>
        <h1>{{ mode === 'login' ? '欢迎回来' : '创建账号' }}</h1>
        <p>{{ mode === 'login' ? '登录你的教学工作空间' : '开启新的备课日常' }}</p>
        <UTabs v-model="mode" :items="modes" :content="false" :ui="{ list: 'w-full', trigger: 'flex-1' }" />
        <form @submit.prevent="submit">
          <UFormField label="用户名" name="username" required><UInput v-model="username" autocomplete="username" placeholder="输入用户名" maxlength="32" size="lg" icon="i-lucide-user-round" :disabled="busy" /></UFormField>
          <UFormField label="密码" name="password" required>
            <UInput v-model="password" :type="visible ? 'text' : 'password'" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" placeholder="输入密码" size="lg" icon="i-lucide-lock-keyhole" :disabled="busy">
              <template #trailing><UButton :icon="visible ? 'i-lucide-eye-off' : 'i-lucide-eye'" :aria-label="visible ? '隐藏密码' : '显示密码'" color="neutral" variant="link" size="xs" @click="visible = !visible" /></template>
            </UInput>
          </UFormField>
          <UFormField v-if="mode === 'register'" label="确认密码" name="confirmation" required><UInput v-model="confirmation" type="password" autocomplete="new-password" placeholder="再次输入密码" size="lg" icon="i-lucide-lock-keyhole" :disabled="busy" /></UFormField>
          <UAlert v-if="error" :title="error" color="error" variant="soft" icon="i-lucide-circle-alert" role="alert" />
          <UButton type="submit" :loading="busy" :disabled="busy" :label="mode === 'login' ? '登录工作台' : '注册并登录'" trailing-icon="i-lucide-arrow-right" size="lg" block class="mt-2" />
        </form>
      </div>
    </main>
    <footer class="auth-footer">Learning Coach</footer>
  </div>
</template>
