<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import QRCode from 'qrcode'
import { changeMfa, listSessions, mfaStatus, revokeSession, setupMfa, type AdminSession, type MfaSetup } from '../account-security'
import { AUTH_EXPIRED_EVENT } from '../api'

const enabled = ref<boolean | null>(null)
const setup = shallowRef<MfaSetup | null>(null)
const sessions = ref<AdminSession[]>([])
const code = ref('')
const busy = ref(false)
const error = ref('')
const message = ref('')
const qrImage = ref('')
const qrFailed = ref(false)
const manual = ref(false)
const copyMessage = ref('')
const expiresAt = ref(0)
const now = ref(Date.now())
const expired = ref(false)
const remaining = computed(() => {
  const seconds = Math.max(0, Math.ceil((expiresAt.value - now.value) / 1000))
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
})
let clock: ReturnType<typeof setInterval> | undefined
let active = true
function clearSetup() {
  setup.value = null; qrImage.value = ''; code.value = ''; expiresAt.value = 0
  qrFailed.value = false; manual.value = false; copyMessage.value = ''
  clearInterval(clock)
}
function tick() {
  now.value = Date.now()
  if (expiresAt.value && now.value >= expiresAt.value) {
    clearSetup(); expired.value = true
  }
}
const stamp = (value: number) => new Date(value * 1000).toLocaleString('zh-CN')
async function run(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; message.value = ''
  try { await action() } catch (cause) { error.value = cause instanceof Error ? cause.message : '操作失败，请重试' }
  finally { busy.value = false }
}
async function refresh() {
  const [status, devices] = await Promise.all([mfaStatus(), listSessions()])
  if (!active) return
  enabled.value = status.enabled; sessions.value = devices.sessions
  if (status.enabled) { clearSetup(); expired.value = false }
}
function initialize() {
  void run(async () => {
    clearSetup(); expired.value = false
    const startedAt = Date.now()
    const result = await setupMfa()
    if (!active) return
    if (!URL.canParse(result.otpauth_url)) throw new Error('未能生成有效的绑定信息，请重新点击生成二维码。')
    const uri = new URL(result.otpauth_url)
    if (!/^[A-Z2-7]{32}$/.test(result.secret) || uri.protocol !== 'otpauth:' || uri.hostname !== 'totp' || uri.searchParams.get('secret') !== result.secret) {
      throw new Error('未能生成有效的绑定信息，请重新点击生成二维码。')
    }
    setup.value = result
    expiresAt.value = startedAt + 10 * 60 * 1000
    tick()
    if (!setup.value) return
    clock = setInterval(tick, 1000)
    try {
      const image = await QRCode.toDataURL(result.otpauth_url, { width: 240, margin: 4, errorCorrectionLevel: 'M' })
      if (active && setup.value === result) qrImage.value = image
    } catch {
      if (active && setup.value === result) { qrFailed.value = true; manual.value = true }
    }
  })
}
async function copySecret() {
  tick()
  if (!setup.value) return
  try {
    await navigator.clipboard.writeText(setup.value.secret)
    if (active && setup.value) copyMessage.value = '已复制，请粘贴到验证器的“密钥”栏。'
  } catch { copyMessage.value = '浏览器未允许复制，请选中下面的密钥手动复制。' }
}
function cancel() { clearSetup(); expired.value = false; error.value = ''; message.value = '' }
function update(action: 'confirm' | 'disable') {
  tick()
  if (action === 'confirm' && !setup.value) return
  if (action === 'disable' && enabled.value !== true) return
  if (!/^\d{6}$/.test(code.value)) return
  void run(async () => {
    enabled.value = (await changeMfa(action, code.value)).enabled
    clearSetup(); expired.value = false; await refresh()
    message.value = action === 'confirm' ? '登录二次验证已开启。其他设备已退出，下次登录时请输入验证器中的 6 位验证码。' : '登录二次验证已关闭'
  })
}
function revoke(session: AdminSession) {
  if (!window.confirm(session.current ? '退出当前设备？' : '撤销此设备的登录？')) return
  void run(async () => {
    await revokeSession(session.id)
    if (session.current) window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT))
    else { await refresh(); message.value = '设备登录已撤销' }
  })
}
onMounted(() => run(refresh))
onBeforeUnmount(() => { active = false; clearSetup() })
</script>

<template>
  <section class="space-y-5">
    <div class="flex items-center justify-between"><h2 class="text-lg font-semibold">我的账号安全</h2><UButton label="刷新" variant="soft" :loading="busy" @click="run(refresh)" /></div>
    <UAlert v-if="error" color="error" :title="error" />
    <UAlert v-if="message" color="success" :title="message" />
    <UCard>
      <h3 class="font-semibold">登录二次验证</h3>
      <p class="text-sm text-muted my-3">{{ enabled === null ? '正在读取安全设置…' : enabled ? '已开启。登录时，打开手机验证器，输入 LearnCoach 账号下的 6 位验证码即可。' : '给管理员账号多加一道保护：登录时除了密码，再输入手机验证器显示的 6 位验证码。首次按下面三步设置即可。' }}</p>
      <div v-if="enabled === false" class="space-y-5">
        <div class="rounded-lg bg-muted p-4 space-y-2">
          <h4 class="font-semibold">1. 在手机上安装验证器</h4>
          <p class="text-sm">验证器是生成登录验证码的手机应用。可安装 Microsoft Authenticator（微软验证器）或 Google Authenticator（谷歌身份验证器），已安装可直接进行下一步。</p>
          <a class="text-primary underline text-sm" href="https://www.microsoft.com/zh-cn/security/mobile-authenticator-app" target="_blank" rel="noopener noreferrer">打开微软官方下载页面</a>
          <p class="text-sm text-muted">手机装好后再生成二维码。完成第 3 步才会开启二次验证。</p>
        </div>
        <div class="space-y-3">
          <h4 class="font-semibold">2. 用验证器扫描二维码</h4>
          <template v-if="!setup">
            <UAlert v-if="expired" color="warning" title="本次二维码已过期，请重新生成，并在验证器中重新添加 LearnCoach 账号。" />
            <UButton :label="expired ? '重新生成二维码' : '手机已准备好，生成二维码'" :loading="busy" @click="initialize" />
          </template>
          <template v-else>
            <p class="text-sm">打开手机验证器，点“＋”或“添加账号”，选择“扫描二维码”，对准下方图片。微软验证器请先选“其他帐户”。</p>
            <img v-if="qrImage" :src="qrImage" alt="用手机验证器扫描此二维码，添加 LearnCoach 账号" width="240" height="240" class="max-w-full rounded-lg border border-default bg-white" />
            <p v-else-if="!qrFailed" role="status" class="text-sm text-muted">正在生成二维码…</p>
            <UAlert v-if="qrFailed" color="warning" title="二维码暂时无法显示，请使用下方的复制添加方式。" />
            <p class="text-sm text-muted">本次绑定剩余 {{ remaining }}，超时后可重新生成。二维码和密钥只供本人绑定，请勿分享。</p>
            <details :open="manual" @toggle="manual = ($event.target as HTMLDetailsElement).open" class="rounded-lg border border-default p-3">
              <summary class="cursor-pointer text-sm font-medium">无法扫码，或正在同一部手机上操作？</summary>
              <div class="space-y-3 mt-3">
                <a :href="setup.otpauth_url" class="text-primary underline text-sm">在手机上尝试直接打开验证器添加</a>
                <p class="text-sm">如果没有打开验证器，在验证器中点“＋”或“添加账号”，选择“手动输入”或“输入设置密钥”，填写：</p>
                <p class="text-sm">账号名称：<strong>LearnCoach</strong>；类型：<strong>基于时间</strong>（通常是默认选项）。</p>
                <UFormField label="设置密钥（网站已生成，无需自己填写）"><UInput :model-value="setup.secret" readonly class="w-full font-mono" aria-label="设置密钥" /></UFormField>
                <UButton label="复制密钥" variant="soft" :disabled="busy" @click="copySecret" />
                <p v-if="copyMessage" role="status" class="text-sm">{{ copyMessage }}</p>
                <p class="text-sm text-muted">将密钥粘贴到验证器的“密钥”栏，再点添加。请在安全位置保留备份，以便更换手机时使用。</p>
              </div>
            </details>
          </template>
        </div>
        <div class="space-y-3">
          <h4 class="font-semibold">3. 填入手机上显示的 6 位验证码</h4>
          <p class="text-sm text-muted">添加成功后，验证器会显示 LearnCoach 账号和不断更新的 6 位数字。将当前数字填到下方，这不是短信验证码。</p>
          <p v-if="!setup" class="text-sm text-muted">完成扫码添加后，就可以在这里验证并开启。</p>
        </div>
      </div>
      <form v-if="setup || enabled" class="flex flex-wrap items-end gap-3 mt-3" @submit.prevent="update(setup ? 'confirm' : 'disable')">
        <UFormField label="验证器中的 6 位验证码"><UInput v-model="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="6 位验证码" :disabled="busy" /></UFormField>
        <UButton type="submit" :label="setup ? '验证并开启' : '验证并关闭二次验证'" :color="setup ? 'primary' : 'warning'" :disabled="busy || !/^\d{6}$/.test(code)" />
        <UButton v-if="setup" type="button" label="暂不设置" variant="ghost" :disabled="busy" @click="cancel" />
      </form>
    </UCard>
    <UCard>
      <h3 class="font-semibold mb-3">已登录设备</h3>
      <p class="text-sm text-muted mb-3">列出仍有效的设备会话。撤销后，该设备下次请求需要重新登录。</p>
      <div v-for="session in sessions" :key="session.id" class="flex items-center justify-between gap-3 py-3 border-b border-default">
        <div class="min-w-0"><p class="break-all">{{ session.user_agent || '设备信息未记录' }} <UBadge v-if="session.current" label="当前设备" /></p><p class="text-xs text-muted">{{ session.client_ip || '历史会话' }} · 登录 {{ stamp(session.created_at) }} · 最近活动 {{ stamp(session.last_seen_at) }}</p></div>
        <UButton label="撤销登录" color="warning" variant="soft" :disabled="busy" @click="revoke(session)" />
      </div>
      <p v-if="!sessions.length && !busy" class="text-muted">暂无设备记录；旧版会话重新登录后会显示。</p>
    </UCard>
  </section>
</template>
