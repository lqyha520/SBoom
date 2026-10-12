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
    <main class="auth-main admin-login-main">
      <section class="login-intro" aria-label="管理中心介绍"><span class="login-intro-label"><UIcon name="i-lucide-notebook-pen" class="size-5" />出题工作台</span><h2>用心做内容，<br>从容管日常。</h2><p>连接教学资料、用户与服务，<br>让每一份好内容有序抵达。</p><div class="login-capabilities"><span><UIcon name="i-lucide-library" class="size-4" />资料发布</span><span><UIcon name="i-lucide-users-round" class="size-4" />用户服务</span><span><UIcon name="i-lucide-chart-column" class="size-4" />运营管理</span></div><div class="login-decoration" aria-hidden="true"><UIcon name="i-lucide-book-open" /></div></section>
      <div class="auth-form">
        <div class="auth-emblem"><UIcon name="i-lucide-shield-check" class="size-6" /></div>
        <h1>管理员登录</h1>
        <p>欢迎回来，请登录你的管理账号。</p>
        <LoginForm @logined="emit('logined', $event)" />
      </div>
    </main>
  </div>
</template>

<style scoped>
.admin-login-main { display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);width:min(1060px,100%);margin:auto;gap:80px;padding:56px 32px; }
.login-intro { width:100%;position:relative;isolation:isolate;overflow:hidden;align-self:stretch;display:flex;flex-direction:column;justify-content:center;background:#153c34;border-radius:24px;padding:52px 40px;color:#d2e8dc;min-height:470px; }
.login-intro-label { display:flex;align-items:center;gap:8px;font-size:12px;letter-spacing:2px; }
.login-intro h2 { color:#f0f8f4;font-size:34px;line-height:1.6;font-weight:600;margin:30px 0 18px;letter-spacing:1px; }
.login-intro p { font-size:13px;color:#b1cec0;line-height:2; }
.login-capabilities { display:flex;flex-wrap:wrap;gap:14px;margin-top:36px;font-size:11px; }
.login-capabilities > span { display:flex;align-items:center;gap:6px; }
.login-decoration { position:absolute;right:-50px;bottom:40px;z-index:-1;transform:rotate(-18deg);color:#ffffff06; }
.login-decoration > span { width:270px;height:270px; }
.auth-form { padding:12px 0; }
@media(max-width:800px) { .admin-login-main { grid-template-columns:1fr;gap:0;padding:36px 24px; }.login-intro { display:none; } }
</style>
