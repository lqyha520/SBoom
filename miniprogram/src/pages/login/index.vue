<script setup lang="ts">
import { ref } from 'vue'
import { onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import PageChrome from '../../components/PageChrome.vue'
import { errorMessage, request } from '../../services/api'
import { ensureSession, loginMini } from '../../services/session'
import type { Authenticated } from '../../types'
import { HOME, safeDestination } from '../../services/return-route'
import { openCatalog, visitDestination } from '../../services/navigation'
import { registrationAccountError } from '../../../../shared/mini-profile'

const agreed = ref(false)
const busy = ref(false)
const error = ref('')
let active = true
let revision = 0
let returnTo = HOME
onLoad(options => { returnTo = safeDestination(options?.returnTo) })
// #ifdef H5
const accountOpen = ref(false)
const username = ref('')
const password = ref('')
const webMode = ref<'login' | 'register'>('login')
// #endif
function home() { visitDestination(returnTo, true) }
function legal(kind: 'privacy' | 'agreement') { uni.navigateTo({ url: '/pages/privacy/index?kind=' + kind }) }
function requireConsent() {
  if (agreed.value) return true
  error.value = '请先阅读并同意用户协议和隐私政策'
  return false
}
function primary() {
  if (busy.value || !requireConsent()) return
  error.value = ''
  // #ifdef H5
  accountOpen.value = true
  // #endif
  // #ifdef MP-WEIXIN
  void wechatLogin()
  // #endif
}
// #ifdef H5
async function submitWeb() {
  if (busy.value || !requireConsent()) return
  const name = username.value.trim()
  if (name.length < 2 || name.length > 32) { error.value = '用户名需为 2 至 32 位'; return }
  if (webMode.value === 'register' && registrationAccountError(name)) { error.value = registrationAccountError(name); return }
  if (password.value.length < 6) { error.value = '密码至少需要 6 位'; return }
  const current = ++revision
  busy.value = true; error.value = ''
  try {
    const endpoint = webMode.value === 'register' ? '/api/v1/mini/register' : '/api/v1/mini/login-password'
    const result = await request<Authenticated>(endpoint, 'POST', { username: name, password: password.value })
    if (!active || current !== revision) return
    password.value = ''; loginMini(result); home()
  } catch (cause) { if (active && current === revision) error.value = errorMessage(cause) }
  finally { if (current === revision) busy.value = false }
}
function closeAccount() {
  if (busy.value) return
  accountOpen.value = false; password.value = ''; error.value = ''
}
// #endif
// #ifdef MP-WEIXIN
async function wechatLogin() {
  if (busy.value || !requireConsent()) return
  const current = ++revision
  busy.value = true; error.value = ''
  try {
    const wxCode = await new Promise<string>((resolve, reject) => uni.login({
      provider: 'weixin',
      success(result) { result.code ? resolve(result.code) : reject(new Error('未获得微信登录凭证')) },
      fail() { reject(new Error('微信登录未完成，请重试')) },
    }))
    if (!active || current !== revision) return
    const result = await request<Authenticated>('/api/v1/mini/login', 'POST', { code: wxCode })
    if (!active || current !== revision) return
    loginMini(result); home()
  } catch (cause) { if (active && current === revision) error.value = errorMessage(cause) }
  finally { if (current === revision) busy.value = false }
}
// #endif
onShow(async () => { active = true; if (await ensureSession() && active) home() })
function leave() {
  active = false; revision++; busy.value = false
  // #ifdef H5
  password.value = ''; accountOpen.value = false
  // #endif
}
onHide(leave)
onUnload(leave)
</script>

<template>
  <view class="login-page">
    <view class="login-intro">
      <PageChrome back />
      <view class="login-art"><image src="/static/illustrations/notebook.png" mode="aspectFit" aria-hidden="true" /></view>
      <text class="login-title">习题库</text><text class="login-subtitle">每天一点进步</text>
    </view>
    <view class="login-body">
      <wd-button block role="button" :loading="busy" :disabled="busy" custom-class="login-primary" @click="primary">
        <!-- #ifdef H5 -->
        <text>账号登录</text>
        <!-- #endif -->
        <!-- #ifdef MP-WEIXIN -->
        <text>{{ busy ? '正在登录' : '微信一键登录' }}</text>
        <!-- #endif -->
        <view v-if="!busy" class="login-trail"><wd-icon name="arrow-right" size="19px" /></view>
      </wd-button>
      <view class="login-feedback" role="status" aria-live="polite">{{ error }}</view>
      <view class="consent">
        <wd-checkbox v-model="agreed" type="circle" :disabled="busy" role="checkbox" :aria-checked="agreed" aria-label="已阅读并同意用户协议和隐私政策" custom-class="consent-checkbox" @change="error = ''" />
        <view class="consent-copy"><text>我已阅读并同意</text><view class="consent-links"><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="legal-link" role="button" :disabled="busy" @click="legal('agreement')">《用户协议》</button><text>与</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="legal-link" role="button" :disabled="busy" @click="legal('privacy')">《隐私政策》</button></view></view>
      </view>
      <button class="browse-entry" hover-class="control-pressed" role="button" :disabled="busy" @click="openCatalog()">暂不登录，先逛习题库<wd-icon name="arrow-right" size="14px" /></button>
    </view>
    <!-- #ifdef H5 -->
    <wd-popup :model-value="accountOpen" position="bottom" :z-index="1200" :close-on-click-modal="!busy" root-portal safe-area-inset-bottom custom-style="border-radius:22px 22px 0 0" @update:model-value="!$event && closeAccount()">
      <view class="sheet account-login-sheet" role="dialog" aria-modal="true" aria-label="账号登录">
        <view class="sheet-handle" />
        <view class="sheet-head"><text class="sheet-title">习题库账号</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="bare-icon" role="button" aria-label="关闭账号登录" :disabled="busy" @click="closeAccount"><wd-icon name="close" size="20px" /></button></view>
        <wd-tabs v-model="webMode" line-theme="text" @change="error = ''"><wd-tab name="login" title="登录" :disabled="busy" /><wd-tab name="register" title="注册" :disabled="busy" /></wd-tabs>
        <view class="login-form"><text class="field-label">账号</text><wd-input v-model="username" prefix-icon="user" custom-class="login-input" :placeholder="webMode === 'register' ? '设置英文或数字账号' : '请输入登录账号'" aria-label="用户名" :maxlength="32" :disabled="busy" /><text v-if="webMode === 'register'" class="account-hint">2-32 位英文、数字、下划线或短横线；中文昵称可在个人资料中设置。</text><text class="field-label">密码</text><wd-input v-model="password" prefix-icon="lock" custom-class="login-input" show-password placeholder="密码" aria-label="密码" :maxlength="128" :disabled="busy" confirm-type="done" @confirm="submitWeb" /></view>
        <view v-if="error" class="error-strip" role="alert">{{ error }}</view>
        <view class="login-submit"><wd-button role="button" block :loading="busy" :disabled="!agreed || busy" @click="submitWeb">{{ webMode === 'register' ? '注册并登录' : '登录' }}</wd-button></view>
      </view>
    </wd-popup>
    <!-- #endif -->
  </view>
</template>

<style scoped>
.account-hint { display:block;margin-top:8px;color:var(--lc-muted);font-size:12px;line-height:1.7; }
.login-page { display: flex; flex-direction: column; min-height: 100vh; }
.login-intro { padding: 0 24px 32px; text-align: center; background-color: var(--lc-hero); background-image: radial-gradient(58% 58% at 90% -8%, #ffffff75 0%, #ffffff00 68%), radial-gradient(46% 46% at 4% 106%, #ffffff40 0%, #ffffff00 70%), linear-gradient(168deg, #ebf6ed 0%, #daebde 62%, #e6f2e8 100%); border-radius: 0 0 47% 8% / 0 0 6% 2%; }
.login-art { display: flex; align-items: center; justify-content: center; height: 226px; width: 100%; margin-top: 27px; }
.login-art image { width: 226px; height: 226px; max-width: 100%; }
.login-title { display: block; font-size: 26px; line-height: 1.4; font-weight: 650; margin: 10px 0 7px; }
.login-subtitle { display: block; color: var(--lc-secondary); font-size: 13px; }
.login-body { padding: 35px 26px 28px; }
.login-body :deep(.login-primary) { position: relative; --wot-button-height-medium: 54px; font-size: 15px; font-weight: 600; }
.login-trail { position: absolute; right: 20px; top: 0; height: 100%; display: flex; align-items: center; }
.login-feedback { min-height: 31px; padding: 8px 0 3px; color: #a33e37; text-align: center; font-size: 12px; overflow-wrap: anywhere; }
.browse-entry { display:flex;align-items:center;justify-content:center;gap:6px;min-height:44px;margin:12px auto 0;padding:8px;background:transparent;color:var(--lc-primary);font-size:13px;line-height:1.6; }
.consent { display: flex; align-items: flex-start; justify-content: center; margin-top: 8px; color: var(--lc-muted); font-size: 12px; }
.consent :deep(.consent-checkbox) { display: flex; align-items: center; justify-content: center; min-height: 44px; width: 44px; flex: none; margin: 0; }
.consent-copy { padding-top: 9px; }
.consent-links { display: flex; align-items: center; flex-wrap: wrap; gap: 0; margin-top: -3px; }
.legal-link { display: inline-flex; align-items: center; min-height: 44px; padding: 0; margin: 0; background: transparent; border-radius: 0; color: var(--lc-primary); font-size: 12px; line-height: 1.5; }
.account-login-sheet { max-height: 84vh; overflow-y: auto; }
.login-form :deep(.login-input) { background: var(--lc-background); border-radius: 8px; --wot-input-padding: 14px; --wot-input-inner-height: 24px; --wot-input-bg: transparent; }
.login-submit { padding-top: 24px; }
@media (max-width: 359px) { .login-body { padding-left: 22px; padding-right: 22px; } }
@media (max-height: 680px) { .login-art { height: 190px; margin-top: 12px; } .login-art image { width: 190px; height: 190px; } .login-body { padding-top: 26px; } }
</style>
