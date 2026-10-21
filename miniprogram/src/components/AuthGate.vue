<script setup lang="ts">
import { ref, watch } from 'vue'
import { openCatalog } from '../services/navigation'
withDefaults(defineProps<{ title?: string; description?: string; browse?: boolean }>(), { title: '登录习题库', description: '', browse: false })
import { ensureSession, requireLogin, session } from '../services/session'
const emit = defineEmits<{ restored: [] }>()
const reconnecting = ref(false)
// Notify the parent before v-if removes this gate after session.user changes.
watch(() => session.user, user => { if (user && reconnecting.value) emit('restored') }, { flush: 'sync' })
async function reconnect() {
  if (reconnecting.value) return
  reconnecting.value = true
  try { await ensureSession() }
  finally { reconnecting.value = false }
}
function login() { requireLogin() }
</script>

<template>
  <view class="state-block">
    <view v-if="!session.ready" class="gate-state" role="status">
      <view class="gate-badge loading"><wd-loading color="#307e61" size="20px" /></view>
      <text class="gate-title">正在恢复登录</text>
      <text class="gate-caption">稍等片刻，马上就好</text>
    </view>
    <view v-else-if="session.error" class="gate-state" role="alert">
      <view class="gate-badge error"><wd-icon name="info-circle-fill" size="26px" /></view>
      <text class="gate-title">暂时无法恢复登录</text>
      <text class="gate-caption">{{ session.error }}，请检查网络后重试</text>
      <view class="empty-actions auth-actions"><wd-button icon="refresh" :loading="reconnecting" :disabled="reconnecting" @click="reconnect">重新连接</wd-button><wd-button v-if="browse" variant="plain" @click="openCatalog()">先逛习题库</wd-button></view>
    </view>
    <view v-else class="gate-state">
      <view class="gate-badge"><wd-icon name="lock" size="26px" /></view>
      <text class="gate-title">{{ title }}</text>
      <text v-if="description" class="gate-caption">{{ description }}</text>
      <view class="empty-actions auth-actions"><wd-button icon="user" role="button" @click="login">去登录</wd-button><wd-button v-if="browse" role="button" variant="plain" @click="openCatalog()">先逛习题库</wd-button></view>
    </view>
  </view>
</template>
<style scoped>
.gate-state { display:flex;flex-direction:column;align-items:center;width:100%; }
.gate-badge { display:flex;align-items:center;justify-content:center;width:64px;height:64px;margin-bottom:15px;border-radius:22px;color:var(--lc-primary);background:linear-gradient(150deg,#eef7f0,#dfeee4);box-shadow:inset 0 0 0 1px #d9ebdf; }
.gate-badge.loading { background:var(--lc-primary-soft); }
.gate-badge.error { color:#a3542e;background:linear-gradient(150deg,#fbf2ea,#f5e4d7);box-shadow:inset 0 0 0 1px #efdbca; }
.gate-title { max-width:100%;color:var(--lc-text);font-size:17px;font-weight:600;line-height:1.5;text-align:center; }
.gate-caption { max-width:290px;margin-top:7px;color:var(--lc-secondary);font-size:13px;line-height:1.8;text-align:center;overflow-wrap:anywhere; }
.auth-actions { gap:10px;flex-wrap:wrap;margin-top:18px; }
</style>
