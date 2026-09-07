<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const password2 = ref('')
const busy = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (busy.value) return
  const u = username.value.trim()
  const p = password.value
  if (!u || !p) { error.value = '请输入用户名和密码'; return }
  if (mode.value === 'register') {
    if (p.length < 6) { error.value = '密码至少 6 位'; return }
    if (p !== password2.value) { error.value = '两次输入的密码不一致'; return }
  }
  busy.value = true
  try {
    if (mode.value === 'login') await auth.login(u, p)
    else await auth.register(u, p)
    // 成功后 auth store 会整页刷新，无需处理
  } catch (e: any) {
    error.value = e?.message || '操作失败，请重试'
  } finally {
    busy.value = false
  }
}

function switchMode(m: 'login' | 'register') {
  mode.value = m
  error.value = ''
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-brand">
        <span class="auth-logo">✏️</span>
        <div>
          <div class="auth-title">出题工作台</div>
          <div class="auth-sub">AI 帮你出好每一份卷子</div>
        </div>
      </div>

      <div class="auth-tabs">
        <button :class="{ on: mode === 'login' }" @click="switchMode('login')">登录</button>
        <button :class="{ on: mode === 'register' }" @click="switchMode('register')">注册</button>
      </div>

      <form @submit.prevent="submit">
        <div class="auth-field">
          <label>用户名</label>
          <input v-model="username" class="input" autocomplete="username" placeholder="2-32 位字母 / 数字 / 中文" />
        </div>
        <div class="auth-field">
          <label>密码</label>
          <input v-model="password" class="input" type="password" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" placeholder="至少 6 位" />
        </div>
        <div v-if="mode === 'register'" class="auth-field">
          <label>确认密码</label>
          <input v-model="password2" class="input" type="password" autocomplete="new-password" placeholder="再输入一次" />
        </div>

        <div v-if="error" class="auth-error">{{ error }}</div>

        <button class="btn primary auth-submit" :disabled="busy" type="submit">
          {{ busy ? '请稍候…' : mode === 'login' ? '登录' : '注册并登录' }}
        </button>
      </form>

      <div class="auth-tip">
        每个账号的模板、模型配置、生成缓存完全隔离；
        模型密钥加密存储在服务端，不在浏览器留存。
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
  background: linear-gradient(135deg, var(--bg-page, #f3f5fa), #e8edf7);
  padding: 16px;
}
.auth-card {
  width: 360px;
  max-width: 100%;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 12px 40px rgba(30, 42, 80, 0.12);
  padding: 28px 28px 22px;
}
.auth-brand { display: flex; gap: 12px; align-items: center; margin-bottom: 20px; }
.auth-logo { font-size: 34px; }
.auth-title { font-size: 20px; font-weight: 700; color: #22314f; }
.auth-sub { font-size: 12px; color: #7b869e; margin-top: 2px; }
.auth-tabs {
  display: flex;
  border: 1px solid #dfe4ef;
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 18px;
}
.auth-tabs button {
  flex: 1;
  padding: 9px 0;
  border: 0;
  background: #f6f8fc;
  color: #6b7690;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}
.auth-tabs button.on { background: #fff; color: var(--primary, #4b6ef5); font-weight: 600; }
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
  margin-top: 16px;
  font-size: 12px;
  color: #97a1b7;
  line-height: 1.7;
  border-top: 1px dashed #e6eaf3;
  padding-top: 12px;
}
.auth-loading {
  position: fixed; inset: 0;
  display: flex; align-items: center; justify-content: center;
  color: #7b869e; font-size: 14px;
  background: var(--bg-page, #f3f5fa);
}
</style>
