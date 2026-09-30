<script setup lang="ts">
import * as api from '../api'
import LoginForm from './LoginForm.vue'

const emit = defineEmits<{ logined: [user: api.UserInfo] }>()
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
        <LoginForm @logined="emit('logined', $event)" />
      </div>
    </main>
    <footer class="auth-footer">Learning Coach</footer>
  </div>
</template>
