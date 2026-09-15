<script setup lang="ts">
import { ref } from 'vue'
import * as api from '../api'

const emit = defineEmits<{ logined: [user: api.UserInfo] }>()
const username = ref('')
const password = ref('')
const visible = ref(false)
const busy = ref(false)
const error = ref('')

async function submit() {
  if (busy.value) return
  error.value = ''
  if (!username.value.trim() || !password.value) { error.value = '请输入用户名和密码'; return }
  busy.value = true
  try {
    const user = await api.login(username.value.trim(), password.value)
    if (user.role !== 'admin') {
      await api.logout()
      error.value = '该账号没有管理员权限'
      return
    }
    emit('logined', user)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '登录失败，请重试'
  } finally { busy.value = false }
}
</script>

<template>
  <div class="auth-page">
    <header class="auth-header">
      <div class="brand"><span class="brand-mark"><UIcon name="i-lucide-notebook-pen" class="size-5" /></span><div><div class="brand-name">Learning Coach</div><div class="brand-caption">管理控制台</div></div></div>
      <UButton href="/" icon="i-lucide-arrow-up-right" label="出题工作台" color="neutral" variant="ghost" size="sm" />
    </header>
    <main class="auth-main">
      <div class="auth-form">
        <div class="auth-emblem"><UIcon name="i-lucide-shield-check" class="size-6" /></div>
        <h1>管理员登录</h1>
        <p>Learning Coach 管理控制台</p>
        <form @submit.prevent="submit">
          <UFormField label="管理员账号" required><UInput v-model="username" autocomplete="username" placeholder="输入用户名" maxlength="32" size="lg" icon="i-lucide-user-round" :disabled="busy" /></UFormField>
          <UFormField label="密码" required>
            <UInput v-model="password" :type="visible ? 'text' : 'password'" autocomplete="current-password" placeholder="输入密码" size="lg" icon="i-lucide-lock-keyhole" :disabled="busy">
              <template #trailing><UButton :icon="visible ? 'i-lucide-eye-off' : 'i-lucide-eye'" :aria-label="visible ? '隐藏密码' : '显示密码'" color="neutral" variant="link" size="xs" @click="visible = !visible" /></template>
            </UInput>
          </UFormField>
          <UAlert v-if="error" :title="error" color="error" variant="soft" icon="i-lucide-circle-alert" role="alert" />
          <UButton type="submit" :loading="busy" :disabled="busy" label="登录管理后台" trailing-icon="i-lucide-arrow-right" size="lg" block class="mt-2" />
        </form>
      </div>
    </main>
    <footer class="auth-footer">Learning Coach</footer>
  </div>
</template>
