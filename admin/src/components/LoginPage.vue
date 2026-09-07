<script setup lang="ts">
import { ref } from 'vue'
import * as api from '../api'

const emit = defineEmits<{ (e: 'logined', u: api.UserInfo): void }>()

const username = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (busy.value) return
  if (!username.value.trim() || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  busy.value = true
  try {
    const u = await api.login(username.value.trim(), password.value)
    if (u.role !== 'admin') {
      // 非管理员：立即撤销会话并提示（后台系统仅管理员可用）
      await api.logout()
      error.value = `「${u.username}」不是管理员账号，无法登录后台`
      return
    }
    emit('logined', u)
  } catch (e: any) {
    error.value = e?.message || '登录失败，请重试'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-brand">
        <span class="auth-logo">🛠</span>
        <div>
          <div class="auth-title">后台管理</div>
          <div class="auth-sub">出题工作台 · Learning Coach</div>
        </div>
      </div>

      <form @submit.prevent="submit">
        <div class="auth-field">
          <label>管理员账号</label>
          <input v-model="username" class="input" autocomplete="username" placeholder="用户名" />
        </div>
        <div class="auth-field">
          <label>密码</label>
          <input v-model="password" class="input" type="password" autocomplete="current-password" placeholder="密码" />
        </div>

        <div v-if="error" class="auth-error">{{ error }}</div>

        <button class="btn primary auth-submit" :disabled="busy" type="submit">
          {{ busy ? '登录中…' : '登 录' }}
        </button>
      </form>

      <div class="auth-tip">
        本系统仅供管理员使用。普通用户请前往
        <a href="/" target="_self">出题工作台</a> 登录。
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #232a3d, #1a2032);
  padding: 16px;
}
.auth-card {
  width: 360px;
  max-width: 100%;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.35);
  padding: 30px 28px 22px;
}
.auth-brand { display: flex; gap: 12px; align-items: center; margin-bottom: 24px; }
.auth-logo { font-size: 36px; }
.auth-title { font-size: 20px; font-weight: 700; color: #22314f; }
.auth-sub { font-size: 12px; color: #7b869e; margin-top: 2px; }
.auth-field { margin-bottom: 14px; }
.auth-field label { display: block; font-size: 12px; color: #5c6880; margin-bottom: 6px; }
.auth-field .input { width: 100%; box-sizing: border-box; }
.auth-error {
  background: #fdecec;
  color: #c0392b;
  border-radius: 8px;
  font-size: 13px;
  padding: 8px 12px;
  margin-bottom: 12px;
}
.auth-submit { width: 100%; padding: 11px 0; font-size: 15px; }
.auth-tip {
  margin-top: 18px;
  font-size: 12px;
  color: #97a1b7;
  line-height: 1.7;
  border-top: 1px dashed #e6eaf3;
  padding-top: 12px;
}
.auth-tip a { color: #4b6ef5; }
</style>
