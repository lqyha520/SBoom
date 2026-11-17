<script setup lang="ts">
import { ref } from 'vue'
import * as api from '../api'
const props = defineProps<{ expectedUser?: api.UserInfo }>()
const emit = defineEmits<{ logined: [user: api.UserInfo] }>()
const username = ref(props.expectedUser?.username || '')
const password = ref('')
const visible = ref(false)
const busy = ref(false)
const error = ref('')
const mfa = ref<{ challenge: string; username: string } | null>(null)
const code = ref('')
async function submit() {
  if (busy.value) return
  error.value = ''
  if (mfa.value ? !/^\d{6}$/.test(code.value) : !username.value.trim() || !password.value) { error.value = mfa.value ? '请输入 6 位动态验证码' : '请输入用户名和密码'; return }
  busy.value = true
  try {
    const user = mfa.value ? await api.verifyMfa(mfa.value.challenge, code.value) : await api.login(props.expectedUser?.username || username.value.trim(), password.value)
    if ('mfa_required' in user) { mfa.value = { challenge: user.challenge, username: user.username }; password.value = ''; return }
    if (user.role !== 'admin' || props.expectedUser && user.id !== props.expectedUser.id) {
      await api.logout()
      error.value = props.expectedUser ? '请使用原管理员账号验证，当前编辑尚未保存' : '该账号没有管理员权限'
      return
    }
    emit('logined', user)
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '登录失败，请重试' }
  finally { busy.value = false }
}
</script>

<template>
  <form class="field-stack admin-login-form" @submit.prevent="submit">
    <UFormField label="管理员账号" required><UInput v-model="username" autocomplete="username" placeholder="输入用户名" maxlength="32" size="lg" icon="i-lucide-user-round" :readonly="!!expectedUser" :disabled="busy" class="w-full" /></UFormField>
    <UFormField v-if="!mfa" label="密码" required>
      <UInput v-model="password" :type="visible ? 'text' : 'password'" autocomplete="current-password" placeholder="输入密码" size="lg" icon="i-lucide-lock-keyhole" :disabled="busy" :autofocus="!!expectedUser" class="w-full">
        <template #trailing><UButton :icon="visible ? 'i-lucide-eye-off' : 'i-lucide-eye'" :aria-label="visible ? '隐藏密码' : '显示密码'" color="neutral" variant="link" size="sm" @click="visible = !visible" /></template>
      </UInput>
    </UFormField>
    <UFormField v-else label="动态验证码" required><UInput v-model="code" inputmode="numeric" maxlength="6" autocomplete="one-time-code" placeholder="输入验证器中的 6 位验证码" size="lg" icon="i-lucide-shield-check" :disabled="busy" /></UFormField>
    <UAlert v-if="error" :title="error" color="error" role="alert" />
    <UButton v-if="mfa" label="返回账号密码登录" variant="link" :disabled="busy" @click="mfa = null; code = ''; error = ''" />
    <UButton type="submit" :loading="busy" :disabled="busy" :label="mfa ? '验证并登录' : expectedUser ? '验证并继续' : '登录管理后台'" trailing-icon="i-lucide-arrow-right" size="lg" block />
  </form>
</template>
