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
    <wd-loading v-if="!session.ready" color="#307e61" />
    <wd-empty v-else-if="session.error" icon="wifi" tip="暂时无法恢复登录"><template #bottom><text class="auth-caption">{{ session.error }}，请重试连接</text><view class="empty-actions auth-actions"><wd-button icon="refresh" :loading="reconnecting" :disabled="reconnecting" @click="reconnect">重新连接</wd-button><wd-button v-if="browse" variant="plain" @click="openCatalog()">先逛习题库</wd-button></view></template></wd-empty>
    <wd-empty v-else icon="lock" :icon-size="64" :tip="title"><template #bottom><text v-if="description" class="auth-caption">{{ description }}</text><view class="empty-actions auth-actions"><wd-button icon="user" role="button" @click="login">去登录</wd-button><wd-button v-if="browse" role="button" variant="plain" @click="openCatalog()">先逛习题库</wd-button></view></template></wd-empty>
  </view>
</template>
<style scoped>
.auth-caption { display:block;margin-top:12px;font-size:13px;line-height:1.8;color:var(--lc-secondary); }
.auth-actions { gap:12px;flex-wrap:wrap; }
</style>
