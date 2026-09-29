<script setup lang="ts">
import { navigatePage } from '../../services/page-navigation'

import { copyWithPrivacy } from '../../services/privacy'
import { ref, watch } from 'vue'
import { onHide, onShow, onUnload } from '@dcloudio/uni-app'
import AuthGate from '../../components/AuthGate.vue'
import AppTabBar from '../../components/AppTabBar.vue'
import PageChrome from '../../components/PageChrome.vue'
import PasswordSheet from '../../components/PasswordSheet.vue'
import ProfileSheet from '../../components/ProfileSheet.vue'
import ProfileAvatar from '../../components/ProfileAvatar.vue'
import { errorMessage, fetchCatalogSummary } from '../../services/api'
import { ensureSession, logout, refreshMembership, session } from '../../services/session'
import { usePageLifecycle } from '../../services/page-lifecycle'
import { version as appVersion } from '../../../package.json'
import { useTabBarOverlay } from '../../services/tabbar-overlay'
import { membershipExpiry } from '../../presentation'
import { openSupport } from '../../services/experience'
import type { CatalogSummary } from '../../types'
import { inboxState, refreshUnread, openRequests } from '../../services/growth'

const summary = ref<CatalogSummary | null>(null)
const error = ref('')
const busy = ref(false)
const settingsOpen = ref(false)
const logoutOpen = ref(false)
const profileOpen = ref(false)
const passwordOpen = ref(false)
useTabBarOverlay(() => settingsOpen.value || logoutOpen.value)
const requests = usePageLifecycle(() => session.user?.id)
requests.show()
let active = true
watch(() => session.user?.id, () => {
  requests.invalidate(); summary.value = null; error.value = ''
  settingsOpen.value = false; logoutOpen.value = false
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
    const [result] = await Promise.all([fetchCatalogSummary({ scope: current }), refreshUnread({ scope: current }), refreshMembership({ scope: current })])
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
function privacy() { navigatePage({ url: '/subpages/privacy/index' }) }
function favorites() { uni.switchTab({ url: '/pages/favorites/index' }) }
function recent() { navigatePage({ url: '/pages/recent/index' }) }
function downloads() { navigatePage({ url: '/pages/downloads/index' }) }
function messages() { navigatePage({ url: '/subpages/messages/index' }) }
function orders() { navigatePage({ url: '/subpages/orders/index' }) }
function membership() { navigatePage({ url: '/subpages/membership/index' }) }
function copyAccount() {
  if (!session.user) return
  copyWithPrivacy({ data: session.user.username, success: () => uni.showToast({ title: '账号已复制', icon: 'none' }) })
}
function closure() { settingsOpen.value = false; navigatePage({ url: '/subpages/closure/index' }) }
function profileSaved() { profileOpen.value = false; void load(); uni.showToast({ title: '资料已更新', icon: 'none' }) }
function passwordSaved() { passwordOpen.value = false; uni.showToast({ title: session.user?.has_password ? '密码已保存' : '密码已设置', icon: 'none' }) }
onShow(() => { active = true; requests.show(); if (!profileOpen.value) void load() })
function suspend() {
  active = false; requests.leave()
  settingsOpen.value = false; logoutOpen.value = false
  passwordOpen.value = false
}
// WeChat's native avatar/album picker can hide the page. Keep the draft and
// popup alive until the picker returns; only unloading discards the draft.
onHide(suspend)
onUnload(() => { suspend(); profileOpen.value = false })
</script>

<template>
  <view class="account-page has-tabbar">
    <view class="profile-hero" :class="{ guest: !session.user }">
      <PageChrome />
      <view class="content-width hero-content">
        <view class="identity-card">
          <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-if="session.user" class="avatar-button" role="button" aria-label="编辑头像和昵称" @click="openProfile">
            <view class="avatar"><ProfileAvatar :user="session.user" /></view>
            <view class="avatar-edit" aria-hidden="true"><wd-icon name="camera" size="12px" /></view>
          </button>
          <view v-else class="avatar guest-avatar"><wd-icon name="user" size="28px" /></view>
          <view class="grow identity-copy">
            <text class="profile-name">{{ session.user?.nickname || session.user?.username || '欢迎来到习题库' }}</text>
            <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-if="session.user" class="account-name copy-account" role="button" aria-label="复制登录账号" @click="copyAccount"><text>账号 {{ session.user.username }}</text><wd-icon name="copy" size="11px" /></button>
            <text v-else class="account-name">登录后同步收藏、下载和会员权益</text>
            <view v-if="session.user" class="membership-chip" :class="{ vip: session.user.is_vip }"><wd-icon :name="session.user.is_vip ? 'star-fill' : 'user'" size="11px" /><text>{{ session.user.is_vip ? 'VIP 会员' : '普通用户' }}</text></view>
          </view>
          <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-if="session.user" class="edit-button" role="button" aria-label="编辑个人资料" @click="openProfile"><text>编辑资料</text><wd-icon name="arrow-right" size="12px" /></button>
        </view>
      </view>
    </view>
    <AuthGate v-if="!session.user" @restored="load" />
    <template v-else>
      <view v-if="error" class="content-width"><view class="error-strip"><text class="grow">{{ error }}</text><wd-button icon="refresh" type="danger" variant="text" role="button" aria-label="重试" @click="load" /></view></view>
      <view class="content-width dashboard">
        <view class="quick-grid" role="group" aria-label="个人数据快捷入口">
          <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="quick-card" role="button" @click="favorites"><view class="quick-icon favorite"><wd-icon name="heart" size="20px" /></view><text class="quick-value">{{ summary ? summary.favorites : '—' }}</text><text class="quick-label">我的收藏</text></button>
          <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="quick-card" role="button" @click="downloads"><view class="quick-icon download"><wd-icon name="download" size="20px" /></view><text class="quick-value">{{ summary ? summary.downloads : '—' }}</text><text class="quick-label">下载记录</text></button>
          <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="quick-card" role="button" @click="recent"><view class="quick-icon recent"><wd-icon name="history" size="20px" /></view><text class="quick-value small">继续学习</text><text class="quick-label">最近浏览</text></button>
        </view>
        <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="membership-card" :class="{ active: session.user.is_vip }" role="button" aria-label="查看会员服务" @click="membership">
          <view class="membership-top"><view class="membership-mark"><wd-icon name="star-fill" size="19px" /></view><view class="grow"><text class="membership-title">{{ session.user.is_vip ? 'VIP 会员' : '会员服务' }}</text><text class="membership-caption">{{ session.user.is_vip || session.user.membership_status === 'expired' ? membershipExpiry(session.user) : '好资料，陪你每天进步' }}</text></view><view class="membership-action"><text>{{ session.user.is_vip ? '查看权益' : '去看看' }}</text><wd-icon name="arrow-right" size="13px" /></view></view>
          <view class="perk-row"><view><wd-icon name="check" size="12px" /><text>专享资料</text></view><view><wd-icon name="check" size="12px" /><text>完整原稿</text></view><view><wd-icon name="check" size="12px" /><text>PDF 下载</text></view></view>
        </button>
        <view class="section-head"><text>常用服务</text></view>
        <view class="service-grid">
          <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="service-item" role="button" :aria-label="inboxState.unread ? '消息中心，' + inboxState.unread + ' 条未读' : '消息中心'" @click="messages"><view class="service-icon message"><wd-icon name="notification" size="22px" /><text v-if="inboxState.unread" class="unread-badge">{{ inboxState.unread > 99 ? '99+' : inboxState.unread }}</text></view><text>消息中心</text></button>
          <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="service-item" role="button" @click="openRequests()"><view class="service-icon request"><wd-icon name="list" size="22px" /></view><text>资料需求</text></button>
          <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="service-item" role="button" @click="orders"><view class="service-icon order"><wd-icon name="file" size="22px" /></view><text>会员订单</text></button>
          <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="service-item" role="button" @click="openSupport()"><view class="service-icon support"><wd-icon name="headset" size="22px" /></view><text>联系客服</text></button>
        </view>
        <view class="section-head compact"><text>账号与帮助</text></view>
        <view class="more-card">
          <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" aria-label="账号与安全" @click="settingsOpen = true"><view class="more-icon"><wd-icon name="lock" size="18px" /></view><view class="grow"><text>账号与安全</text></view><wd-icon name="arrow-right" size="15px" /></button>
          <view class="more-divider" />
          <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" @click="privacy"><view class="more-icon privacy"><wd-icon name="safe" size="18px" /></view><view class="grow"><text>隐私与服务</text></view><wd-icon name="arrow-right" size="15px" /></button>
        </view>
      </view>
      <text class="account-foot">每天一点进步 · 让学习更有方向</text>
    </template>
    <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-if="!session.user" class="guest-privacy section-link" role="button" @click="privacy">隐私政策</button>
    <AppTabBar current="account" />
    <ProfileSheet :open="profileOpen" @close="profileOpen = false" @saved="profileSaved" />
    <PasswordSheet :open="passwordOpen" @close="passwordOpen = false" @saved="passwordSaved" />
    <wd-popup v-model="settingsOpen" position="bottom" :z-index="1200" root-portal safe-area-inset-bottom custom-style="border-radius:22px 22px 0 0">
      <view class="sheet" role="dialog" aria-modal="true" aria-label="账号设置">
        <view class="sheet-handle" />
        <view class="sheet-head"><text class="sheet-title">账号设置</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="bare-icon" role="button" aria-label="关闭账号设置" @click="settingsOpen = false"><wd-icon name="close" size="20px" /></button></view>
        <wd-cell-group :border="false" center>
          <wd-cell title="编辑资料" :label="session.user?.nickname || session.user?.username" is-link role="button" aria-label="编辑头像与昵称" @click="openProfile"><template #prefix><view class="menu-symbol profile-symbol"><wd-icon name="user" size="21px" /></view></template></wd-cell>
          <wd-cell :title="session.user?.has_password ? '修改密码' : '设置密码'" :label="session.user?.has_password ? '定期更换更安全' : '设置后可使用固定账号登录'" is-link role="button" aria-label="密码设置" @click="openPassword"><template #prefix><view class="menu-symbol lock-symbol"><wd-icon name="lock" size="21px" /></view></template></wd-cell>
        </wd-cell-group>
        <wd-cell title="登录账号" :value="session.user?.username" /><wd-cell title="应用版本" :value="appVersion" />
        <wd-cell title="注销账号" label="申请、查看审核进度或撤回" is-link role="button" @click="closure" />
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
.profile-hero { padding-bottom:34px;background:radial-gradient(ellipse at 95% 0,#cce6d5 0,transparent 65%),linear-gradient(160deg,#e8f4eb,#f3f8f4); }
.profile-hero.guest { padding-bottom: 28px; }
.hero-content { padding-top:20px; }
.identity-card { display:flex;align-items:center;gap:15px;min-height:86px; }
.identity-copy { min-width:0; }
.avatar,.avatar-button { width:68px;height:68px;border-radius:50%; }
.avatar { display:flex;align-items:center;justify-content:center;overflow:hidden;border:3px solid #fff;color:var(--lc-primary);background:#fff;box-shadow:0 8px 20px #36594314;font-size:30px; }
.avatar-button { position:relative;display:block;flex:none;overflow:visible;margin:0;padding:0;border:0;background:transparent;line-height:0; }
.avatar-button::after { border:0; }
.avatar-button:active { transform:scale(.97); }
.avatar-edit { position:absolute;right:-4px;bottom:-4px;display:flex;align-items:center;justify-content:center;width:24px;height:24px;border:2px solid #fff;border-radius:50%;color:#fff;background:var(--lc-primary); }
.guest-avatar { border-radius:50%; }
.profile-name { display:block;overflow:hidden;color:var(--lc-text);font-size:22px;font-weight:700;line-height:1.4;text-overflow:ellipsis;white-space:nowrap; }
.account-name { display:block;overflow:hidden;margin-top:3px;color:var(--lc-secondary);font-size: 12px;line-height:1.5;text-overflow:ellipsis;white-space:nowrap; }
.copy-account { display:flex;align-items:center;gap:6px;max-width:100%;margin:2px 0 0;padding:3px 0;background:transparent;text-align:left; }.copy-account text { overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }.copy-account :deep(.wd-icon) { flex:none; }
.membership-chip { display:inline-flex;align-items:center;gap:4px;margin-top:8px;padding:3px 9px;border-radius:999px;color:#52705f;background:#fff;font-size: 12px;line-height:1.5; }
.membership-chip.vip { color:#9a691e;background:#fff4d8; }
.edit-button { display:flex;align-items:center;gap:2px;flex:none;min-height:44px;margin:0;padding:7px 0;color:var(--lc-primary);background:transparent;font-size: 12px;line-height:1.4; }
.dashboard { position:relative;z-index:2;margin-top:-20px;padding-bottom:18px; }
.quick-grid { display:grid;grid-template-columns:repeat(3,1fr);padding:12px 0;border:1px solid var(--lc-card-line);border-radius:18px;background:var(--lc-card);box-shadow:var(--lc-card-shadow-soft); }
.quick-card { display:flex;flex-direction:column;align-items:center;min-width:0;margin:0;padding:0 5px;border-radius:0;background:transparent; }.quick-card+.quick-card { border-left:1px solid var(--lc-border); }
.quick-card:active,.service-item:active,.membership-card:active,.more-card button:active { transform:scale(.98); }
.quick-icon { display:flex;align-items:center;justify-content:center;width:30px;height:30px;margin-bottom:5px;border-radius:10px; }
.quick-icon.favorite { color:#c75e6b;background:#fbeaec; }.quick-icon.download { color:#397761;background:#e5f2eb; }.quick-icon.recent { color:#526eac;background:#e8eefb; }
.quick-value { height:23px;color:var(--lc-text);font-size:17px;font-weight:700;line-height:23px;font-variant-numeric:tabular-nums; }
.quick-value.small { font-size:12px;font-weight:600; }
.quick-label { margin-top:3px;color:var(--lc-muted);font-size: 12px;line-height:1.5; }
.membership-card { display:block;width:100%;margin:15px 0 0;padding:17px;border:0;border-radius:18px;text-align:left;background:linear-gradient(135deg,#233d32 0%,#315945 58%,#3f7257 100%);box-shadow:0 12px 26px #29473824; }
.membership-card.active { background:linear-gradient(135deg,#58401f 0%,#80602d 55%,#a67b36 100%); }
.membership-top { display:flex;align-items:center;gap:11px; }
.membership-mark { display:flex;align-items:center;justify-content:center;width:38px;height:38px;flex:none;border-radius:13px;color:#f8d88d;background:#ffffff18; }
.membership-title { display:block;color:#fff;font-size:16px;font-weight:650;line-height:1.4; }
.membership-caption { display:block;margin-top:4px;color:#d3e6db;font-size: 12px;line-height:1.5; }
.membership-card.active .membership-caption { color:#ffedcd; }
.membership-action { display:flex;align-items:center;gap:2px;flex:none;color:#f8d88d;font-size: 12px; }
.perk-row { display:flex;justify-content:space-between;gap:8px;margin-top:12px;padding-top:10px;border-top:1px solid #ffffff1f; }
.perk-row > view { display:flex;align-items:center;gap:4px;color:#ffffffc7;font-size: 12px; }
.section-head { display:flex;align-items:flex-end;justify-content:space-between;margin:20px 2px 11px; }
.section-head > text:first-child { color:var(--lc-text);font-size:16px;font-weight:650; }.section-head > text+text { color:var(--lc-muted);font-size: 12px; }.section-head.compact { margin-top:20px; }
.service-grid { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px;padding:16px 7px;border:1px solid var(--lc-card-line);border-radius:18px;background:var(--lc-card);box-shadow:var(--lc-card-shadow-soft); }
.service-item { display:flex;flex-direction:column;align-items:center;min-width:0;margin:0;padding:0;background:transparent; }
.service-icon { position:relative;display:flex;align-items:center;justify-content:center;width:40px;height:40px;margin-bottom:9px;border-radius:13px; }
.service-icon.message { color:#526eac;background:#e9effb; }.service-icon.request { color:#8b6b36;background:#f7efdf; }.service-icon.order { color:#397761;background:#e5f2eb; }.service-icon.support { color:#92699f;background:#f2eaf5; }
.service-item > text { overflow:hidden;color:var(--lc-text);font-size:12px;font-weight:600;line-height:1.5;text-overflow:ellipsis;white-space:nowrap; }
.unread-badge { position:absolute;right:-9px;top:-8px;min-width:18px;height:18px;padding:0 3px;border:2px solid #fff;border-radius:12px;color:#fff;background:#a94e47;font-size:12px;line-height:18px;text-align:center;box-sizing:content-box; }
.more-card { overflow:hidden;padding:0 15px;border:1px solid var(--lc-card-line);border-radius:16px;background:var(--lc-card);box-shadow:var(--lc-card-shadow-soft); }
.more-card button { display:flex;align-items:center;gap:11px;width:100%;min-height:60px;margin:0;padding:10px 0;text-align:left;background:transparent; }
.more-card button > .grow > text { display:block;color:var(--lc-text);font-size:13px;line-height:1.5; }
.more-icon { display:flex;align-items:center;justify-content:center;width:36px;height:36px;flex:none;border-radius:12px;color:#397761;background:#e5f2eb; }.more-icon.privacy { color:#92699f;background:#f2eaf5; }
.more-card button > :deep(.wd-icon):last-child { color:var(--lc-muted); }.more-divider { height:1px;margin-left:47px;background:var(--lc-border); }
.menu-symbol { display:flex;align-items:center;justify-content:center;width:42px;height:42px;margin-right:14px;border-radius:50%;flex:none; }
.profile-symbol { color: var(--lc-primary); background: var(--lc-primary-soft); }
.lock-symbol { color: #8a6a3f; background: #f6efe4; }
.account-foot { display:block;padding:2px 0 28px;color:var(--lc-muted);font-size: 12px;text-align:center; }
.settings-logout { padding-top: 24px; }
.logout-confirm { padding: 25px 22px 22px; }
.logout-caption { display: block; margin-top: 12px; font-size: 13px; line-height: 1.8; color: var(--lc-secondary); }
.logout-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 23px; }
.guest-privacy { display: flex; margin: 0 auto; }
@media (max-width:350px) {
  .identity-card { gap:11px; }.avatar,.avatar-button { width:58px;height:58px; }.profile-name { font-size:20px; }.edit-button { font-size: 12px; }
  .quick-card { padding-left:2px;padding-right:2px; }.service-grid { padding-right:3px;padding-left:3px; }.service-item > text { font-size: 12px; }
}
@media (max-width:359px) {
  .service-grid { grid-template-columns:repeat(2,minmax(0,1fr));gap:20px 12px;padding:18px 12px; }
  .service-item { display:grid;grid-template-columns:36px minmax(0,1fr);column-gap:8px;min-height:44px;text-align:left; }
  .service-icon { width:36px;height:36px;margin:0; }
  .unread-badge { right:-3px; }
  .service-item > text { justify-self:start;max-width:100%; }
}
</style>
