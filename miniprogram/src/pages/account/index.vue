<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onHide, onShow, onUnload } from '@dcloudio/uni-app'
import AuthGate from '../../components/AuthGate.vue'
import AppTabBar from '../../components/AppTabBar.vue'
import PageChrome from '../../components/PageChrome.vue'
import MembershipSheet from '../../components/MembershipSheet.vue'
import PasswordSheet from '../../components/PasswordSheet.vue'
import ProfileSheet from '../../components/ProfileSheet.vue'
import { errorMessage, fetchCatalogSummary } from '../../services/api'
import { ensureSession, logout, refreshMembership, session } from '../../services/session'
import { createLatestRequest } from '../../services/latest-request'
import { useTabBarOverlay } from '../../services/tabbar-overlay'
import { membershipBadge, membershipExpiry, profileAvatar } from '../../presentation'
import type { CatalogSummary } from '../../types'

const summary = ref<CatalogSummary | null>(null)
const error = ref('')
const busy = ref(false)
const settingsOpen = ref(false)
const membershipOpen = ref(false)
const logoutOpen = ref(false)
const profileOpen = ref(false)
const passwordOpen = ref(false)
// 头像：选了预设形象就用它，没选则回退到「首字 + 由账号 id 派生的配色」
const avatar = computed(() => profileAvatar(session.user))
const vipBadge = computed(() => membershipBadge(session.user))
useTabBarOverlay(() => settingsOpen.value || logoutOpen.value)
const requests = createLatestRequest()
let active = true
watch(() => session.user?.id, () => {
  requests.invalidate(); summary.value = null; error.value = ''
  settingsOpen.value = false; membershipOpen.value = false; logoutOpen.value = false
  profileOpen.value = false; passwordOpen.value = false
}, { flush: 'sync' })
// 弹层之间不叠着开：先收起账号设置，再开编辑资料/改密码
function openProfile() { settingsOpen.value = false; passwordOpen.value = false; profileOpen.value = true }
function openPassword() { settingsOpen.value = false; profileOpen.value = false; passwordOpen.value = true }
async function load() {
  error.value = ''
  if (!active || !await ensureSession() || !active) return
  const current = requests.begin()
  try {
    await refreshMembership()
    if (!current()) return
    const result = await fetchCatalogSummary()
    if (current()) summary.value = result
  } catch (cause) { if (current()) error.value = errorMessage(cause) }
}
async function signOut() {
  if (busy.value || !logoutOpen.value || !session.user) return
  busy.value = true; error.value = ''
  try {
    await logout()
  } catch (cause) { if (active) error.value = errorMessage(cause) }
  finally { busy.value = false }
}
function privacy() { uni.navigateTo({ url: '/pages/privacy/index' }) }
function favorites() { uni.switchTab({ url: '/pages/favorites/index' }) }
function downloads() { uni.navigateTo({ url: '/pages/downloads/index' }) }
function profileSaved() { profileOpen.value = false; uni.showToast({ title: '资料已更新', icon: 'none' }) }
function passwordSaved() { passwordOpen.value = false; uni.showToast({ title: session.user?.has_password ? '密码已保存' : '密码已设置', icon: 'none' }) }
onShow(() => { active = true; void load() })
function leave() {
  active = false; requests.invalidate()
  settingsOpen.value = false; membershipOpen.value = false; logoutOpen.value = false
  profileOpen.value = false; passwordOpen.value = false
}
onHide(leave)
onUnload(leave)
</script>

<template>
  <view class="account-page has-tabbar">
    <view class="profile-band" :class="{ guest: !session.user }">
      <PageChrome />
      <view class="content-width profile-content">
        <view class="account-tools"><button v-if="session.user" class="bare-icon" role="button" aria-label="账号设置" title="账号设置" @click="settingsOpen = true"><wd-icon name="settings" size="22px" /></button></view>
        <view class="profile">
          <button v-if="session.user" class="avatar-button" role="button" aria-label="编辑资料：头像与昵称" @click="openProfile">
            <view class="avatar" :style="{ background: avatar.background, color: avatar.color }"><text v-if="avatar.glyph" class="avatar-glyph">{{ avatar.glyph }}</text><text v-else>{{ avatar.initial }}</text></view>
            <view class="avatar-edit" aria-hidden="true"><wd-icon name="camera" size="13px" /></view>
          </button>
          <view v-else class="avatar"><wd-icon name="user" size="29px" /></view>
          <view class="grow">
            <text class="profile-name">{{ session.user?.username || '欢迎来到习题库' }}</text>
            <view v-if="session.user" class="membership-chip" :class="{ vip: session.user.is_vip }"><wd-icon :name="session.user.is_vip ? 'star-fill' : 'check-circle'" size="12px" /><text>{{ session.user.is_vip ? 'VIP 会员' : '普通用户' }}</text></view>
            <text v-else class="profile-caption">每天一点进步</text>
          </view>
        </view>
      </view>
    </view>
    <AuthGate v-if="!session.user" />
    <template v-else>
      <view v-if="error" class="content-width"><view class="error-strip"><text class="grow">{{ error }}</text><wd-button icon="refresh" type="danger" variant="text" role="button" aria-label="重试" @click="load" /></view></view>
      <view class="content-width stats-wrap">
        <view class="stats-card" role="group" aria-label="账号概览">
          <view class="stat"><text class="stat-value">{{ summary ? summary.favorites : '—' }}</text><text class="stat-label">收藏的题</text></view>
          <view class="stat-sep" aria-hidden="true" />
          <view class="stat"><text class="stat-value">{{ summary ? summary.downloads : '—' }}</text><text class="stat-label">下载过</text></view>
          <view class="stat-sep" aria-hidden="true" />
          <view class="stat"><text class="stat-value">{{ vipBadge }}</text><text class="stat-label">会员</text></view>
        </view>
      </view>
      <view class="content-width membership-section">
        <button class="membership-entry" role="button" aria-label="查看会员状态" @click="membershipOpen = true">
          <view class="membership-symbol"><wd-icon name="star-fill" size="22px" /></view>
          <view class="grow"><text class="membership-title">{{ session.user.is_vip ? '我的 VIP 会员' : '开通 VIP 会员' }}</text><text class="membership-caption">{{ membershipExpiry(session.user) }}</text></view>
          <view class="membership-go"><text>{{ session.user.is_vip ? '管理' : '了解' }}</text><wd-icon name="arrow-right" size="14px" /></view>
        </button>
        <view class="membership-perks"><view><wd-icon name="check" size="14px" /><text>专享习题</text></view><view><wd-icon name="check" size="14px" /><text>原稿预览</text></view><view><wd-icon name="check" size="14px" /><text>PDF 下载</text></view></view>
      </view>
      <view class="content-width account-menu">
        <view class="menu-card">
          <wd-cell-group :border="false" center>
            <wd-cell title="我的收藏" :label="summary ? summary.favorites + ' 份习题' : '收藏的习题'" is-link role="button" aria-label="我的收藏" @click="favorites"><template #prefix><view class="menu-symbol favorite-symbol"><wd-icon name="heart" size="21px" /></view></template></wd-cell>
            <wd-cell title="下载记录" :label="summary ? summary.downloads + ' 份习题' : '下载过的习题'" is-link role="button" aria-label="下载记录" @click="downloads"><template #prefix><view class="menu-symbol download-symbol"><wd-icon name="download" size="21px" /></view></template></wd-cell>
            <wd-cell title="隐私与服务" is-link role="button" aria-label="隐私与服务" @click="privacy"><template #prefix><view class="menu-symbol privacy-symbol"><wd-icon name="safe" size="21px" /></view></template></wd-cell>
          </wd-cell-group>
        </view>
      </view>
      <text class="account-foot">每天一点进步</text>
    </template>
    <button v-if="!session.user" class="guest-privacy section-link" role="button" @click="privacy">隐私政策</button>
    <AppTabBar current="account" />
    <MembershipSheet :open="membershipOpen" @close="membershipOpen = false" @refreshed="load" />
    <ProfileSheet :open="profileOpen" @close="profileOpen = false" @saved="profileSaved" />
    <PasswordSheet :open="passwordOpen" @close="passwordOpen = false" @saved="passwordSaved" />
    <wd-popup v-model="settingsOpen" position="bottom" :z-index="1200" root-portal safe-area-inset-bottom custom-style="border-radius:8px 8px 0 0">
      <view class="sheet" role="dialog" aria-modal="true" aria-label="账号设置">
        <view class="sheet-handle" />
        <view class="sheet-head"><text class="sheet-title">账号设置</text><button class="bare-icon" role="button" aria-label="关闭账号设置" @click="settingsOpen = false"><wd-icon name="close" size="20px" /></button></view>
        <wd-cell-group :border="false" center>
          <wd-cell title="编辑资料" :label="session.user?.username" is-link role="button" aria-label="编辑头像与昵称" @click="openProfile"><template #prefix><view class="menu-symbol profile-symbol"><wd-icon name="user" size="21px" /></view></template></wd-cell>
          <wd-cell :title="session.user?.has_password ? '修改密码' : '设置密码'" :label="session.user?.has_password ? '定期更换更安全' : '设置后也能用昵称登录'" is-link role="button" aria-label="密码设置" @click="openPassword"><template #prefix><view class="menu-symbol lock-symbol"><wd-icon name="lock" size="21px" /></view></template></wd-cell>
        </wd-cell-group>
        <wd-cell title="应用版本" value="0.1.0" />
        <view v-if="error" class="error-strip">{{ error }}</view>
        <view class="settings-logout"><wd-button type="info" variant="plain" block icon="poweroff" role="button" :disabled="busy" @click="error = ''; logoutOpen = true">退出登录</wd-button></view>
      </view>
    </wd-popup>
    <wd-popup v-model="logoutOpen" transition="zoom-in" :z-index="1400" :close-on-click-modal="!busy" root-portal custom-style="width:calc(100% - 40px);max-width:340px;border-radius:8px">
      <view class="logout-confirm" role="alertdialog" aria-modal="true" aria-label="确认退出登录">
        <text class="sheet-title">退出登录？</text>
        <text class="logout-caption">收藏、下载记录和会员信息仍保留在账号中。</text>
        <view v-if="error" class="error-strip" role="alert">{{ error }}</view>
        <view class="logout-actions"><wd-button type="info" variant="plain" block role="button" :disabled="busy" @click="logoutOpen = false">取消</wd-button><wd-button block role="button" :loading="busy" :disabled="busy" @click="signOut">确认退出</wd-button></view>
      </view>
    </wd-popup>
  </view>
</template>

<style scoped>
.profile-band { border-radius: 0 0 40% 5% / 0 0 10% 2%; background-color: var(--lc-hero); background-image: radial-gradient(58% 62% at 92% -10%, #ffffff78 0%, #ffffff00 68%), radial-gradient(46% 50% at 2% 108%, #ffffff42 0%, #ffffff00 70%), linear-gradient(168deg, #ebf6ed 0%, #d9ebdd 60%, #e6f2e8 100%); }
.profile-content { padding-top: 13px; padding-bottom: 36px; }
.profile-band.guest .profile-content { padding-bottom: 28px; }
.account-tools { display: flex; justify-content: flex-end; height: 44px; }
.profile { display: flex; align-items: center; gap: 14px; padding: 8px 0 14px; }
.avatar { display: flex; align-items: center; justify-content: center; flex: none; width: 66px; height: 66px; border: 2px solid #ffffffcc; border-radius: 50%; color: var(--lc-primary); background: #fff; box-shadow: 0 8px 18px #2b453514; font-size: 25px; font-weight: 600; }
.avatar-glyph { font-size: 33px; line-height: 1; font-weight: 400; }
/* 头像即入口：右下角挂一个小小的相机标记，点它就能改头像和昵称 */
.avatar-button { position: relative; display: block; flex: none; width: 66px; height: 66px; padding: 0; margin: 0; background: transparent; border: 0; border-radius: 50%; line-height: 0; }
.avatar-button::after { border: 0; }
.avatar-button:active :deep(.avatar) { transform: scale(.96); }
.avatar-edit { position: absolute; right: -2px; bottom: -2px; display: flex; align-items: center; justify-content: center; width: 25px; height: 25px; border: 2px solid #ffffff; border-radius: 50%; color: #fff; background: var(--lc-primary); box-shadow: 0 3px 8px #307e6133; }
.profile-name { display: block; font-size: 22px; font-weight: 650; line-height: 1.4; overflow-wrap: anywhere; }
.profile-caption { display: block; margin-top: 8px; color: var(--lc-secondary); font-size: 12px; }
.membership-chip { display: inline-flex; align-items: center; gap: 4px; margin-top: 9px; padding: 3px 10px; border-radius: 999px; background: #ffffffa8; color: var(--lc-primary); font-size: 11px; line-height: 1.6; }
.membership-chip.vip { background: #fdf1d8; color: var(--lc-warning); }
/* 概览卡片上移压住 hero 下沿，让「头像区 → 内容区」有层次而不是一刀切 */
.stats-wrap { position: relative; z-index: 1; margin-top: -22px; }
.stats-card { display: flex; align-items: center; padding: 16px 8px; border: 1px solid var(--lc-card-line); border-radius: 14px; background: var(--lc-card); box-shadow: var(--lc-card-shadow); }
.stat { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; min-width: 0; }
.stat-value { font-size: 18px; font-weight: 650; line-height: 1.4; color: var(--lc-text); font-variant-numeric: tabular-nums; }
.stat-label { font-size: 11px; color: var(--lc-muted); }
.stat-sep { flex: none; width: 1px; height: 26px; background: var(--lc-border); }
.membership-section { padding-top: 18px; padding-bottom: 4px; }
.membership-entry { display: flex; align-items: center; gap: 12px; width: 100%; padding: 16px 18px; margin: 0; min-height: 48px; text-align: left; font-size: 14px; line-height: 1.5; border: 1px solid #f0e2c6; border-radius: 14px; background-color: #fffdf8; background-image: linear-gradient(135deg, #fdf4e3 0%, #fffdf8 58%, #fbf1dd 100%); box-shadow: 0 8px 20px #8a6a2a0f; }
.membership-entry:active { transform: scale(.99); }
.membership-symbol { display: flex; align-items: center; justify-content: center; width: 42px; height: 42px; border-radius: 50%; flex: none; color: var(--lc-warning); background: #fff; box-shadow: 0 3px 10px #b58a2c1a; }
.membership-title { display: block; font-size: 16px; font-weight: 600; color: var(--lc-text); }
.membership-caption { display: block; color: var(--lc-muted); font-size: 12px; margin-top: 4px; }
.membership-go { display: flex; align-items: center; gap: 2px; flex: none; color: var(--lc-warning); font-size: 12px; }
.membership-perks { display: flex; flex-wrap: wrap; gap: 9px 18px; padding: 14px 4px 12px; }
.membership-perks > view { display: flex; align-items: center; gap: 4px; color: var(--lc-muted); font-size: 11px; }
.membership-perks :deep(.wd-icon) { color: var(--lc-primary); }
.account-menu { padding-top: 0; padding-bottom: 18px; --wot-cell-padding: 12px 0; --wot-cell-title-font-size: 14px; --wot-cell-label-font-size: 11px; }
.menu-card { padding: 2px 16px; border: 1px solid var(--lc-card-line); border-radius: 14px; background: var(--lc-card); box-shadow: var(--lc-card-shadow-soft); }
.account-menu :deep(.wd-cell) { padding-left: 0; }
.account-menu :deep(.wd-cell__wrapper) { padding: 12px 0; min-height: 68px; }
.menu-symbol { display: flex; align-items: center; justify-content: center; width: 42px; height: 42px; margin-right: 14px; border-radius: 50%; flex: none; }
.favorite-symbol { color: #526eac; background: #e9effb; }
.download-symbol { color: var(--lc-primary); background: var(--lc-primary-soft); }
.privacy-symbol { color: #9772aa; background: #f1ebf6; }
.profile-symbol { color: var(--lc-primary); background: var(--lc-primary-soft); }
.lock-symbol { color: #8a6a3f; background: #f6efe4; }
.account-foot { display: block; text-align: center; color: var(--lc-muted); font-size: 11px; padding: 6px 0 28px; }
.settings-logout { padding-top: 24px; }
.logout-confirm { padding: 25px 22px 22px; }
.logout-caption { display: block; margin-top: 12px; font-size: 13px; line-height: 1.8; color: var(--lc-secondary); }
.logout-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 23px; }
.guest-privacy { display: flex; margin: 0 auto; }
</style>
