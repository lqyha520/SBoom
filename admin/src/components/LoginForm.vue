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
async function submit() {
  if (busy.value) return
  error.value = ''
  if (!username.value.trim() || !password.value) { error.value = '请输入用户名和密码'; return }
  busy.value = true
  try {
    const user = await api.login(props.expectedUser?.username || username.value.trim(), password.value)
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
    <UFormField label="密码" required>
      <UInput v-model="password" :type="visible ? 'text' : 'password'" autocomplete="current-password" placeholder="输入密码" size="lg" icon="i-lucide-lock-keyhole" :disabled="busy" :autofocus="!!expectedUser" class="w-full">
        <template #trailing><UButton :icon="visible ? 'i-lucide-eye-off' : 'i-lucide-eye'" :aria-label="visible ? '隐藏密码' : '显示密码'" color="neutral" variant="link" size="sm" @click="visible = !visible" /></template>
      </UInput>
    </UFormField>
    <UAlert v-if="error" :title="error" color="error" role="alert" />
    <UButton type="submit" :loading="busy" :disabled="busy" :label="expectedUser ? '验证并继续' : '登录管理后台'" trailing-icon="i-lucide-arrow-right" size="lg" block />
  </form>
</template>
