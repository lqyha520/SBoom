<script setup lang="ts">
import * as api from '../api'
import LoginForm from './LoginForm.vue'

const emit = defineEmits<{ logined: [user: api.UserInfo] }>()
</script>

<template>
  <div class="auth-page">
    <header class="auth-header">
      <div class="brand"><span class="brand-mark"><UIcon name="i-lucide-notebook-pen" class="size-5" /></span><div class="brand-name">管理控制台</div></div>
      <UButton href="/" icon="i-lucide-arrow-up-right" label="出题工作台" color="neutral" variant="ghost" size="sm" />
    </header>
    <main class="auth-main">
      <div class="auth-form">
        <div class="auth-emblem"><UIcon name="i-lucide-shield-check" class="size-6" /></div>
        <h1>管理员登录</h1>
        <LoginForm @logined="emit('logined', $event)" />
      </div>
    </main>
  </div>
</template>
