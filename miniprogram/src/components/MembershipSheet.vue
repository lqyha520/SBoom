<script setup lang="ts">
import { navigatePage } from '../services/page-navigation'

import { onBeforeUnmount, ref, watch } from 'vue'
import { errorMessage } from '../services/api'
import { refreshMembership, session } from '../services/session'
import { useTabBarOverlay } from '../services/tabbar-overlay'
import { fetchSupport, type SupportSettings } from '../services/experience'
import { computed } from 'vue'
import { membershipExpiry } from '../presentation'
import { iosRestricted } from '../services/checkout'
import { onHide } from '@dcloudio/uni-app'
import { createLatestRequest } from '../services/latest-request'
import { fetchPlans } from '../services/growth'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: []; refreshed: [] }>()
const busy = ref(false)
const error = ref('')
const contact = ref<SupportSettings | null>(null)
const iosEnabled = ref(false)
const plansKnown = ref(false), plansLoading = ref(false), contactLoading = ref(false)
const plansError = ref(''), contactError = ref('')
const restricted = computed(() => plansKnown.value && iosRestricted(iosEnabled.value))
const expiresSoon = computed(() => session.user?.is_vip && session.user.vip_expires_at && session.user.vip_expires_at - Date.now() / 1000 <= 7 * 86400)
const contactReads = createLatestRequest(), planReads = createLatestRequest(), memberReads = createLatestRequest()
function invalidate() { contactReads.invalidate(); planReads.invalidate(); memberReads.invalidate(); revision++; plansLoading.value = false; contactLoading.value = false; busy.value = false }
async function loadContact() {
  if (!props.open) return
  const current = contactReads.begin()
  contactLoading.value = true; contactError.value = ''
  try { const result = await fetchSupport({ scope: current }); if (current() && props.open) contact.value = result }
  catch (cause) { if (current() && props.open) contactError.value = errorMessage(cause) }
  finally { if (current()) contactLoading.value = false }
}
async function loadPlans() {
  if (!props.open) return
  const current = planReads.begin()
  plansKnown.value = false; iosEnabled.value = false; plansLoading.value = true; plansError.value = ''
  try { const result = await fetchPlans({ scope: current }); if (current() && props.open) { iosEnabled.value = result.ios_enabled; plansKnown.value = true } }
  catch (cause) { if (current() && props.open) plansError.value = errorMessage(cause) }
  finally { if (current()) plansLoading.value = false }
}
function reset() { invalidate(); contact.value = null; plansKnown.value = false; iosEnabled.value = false; plansError.value = ''; contactError.value = ''; error.value = '' }
watch(() => props.open, value => { reset(); if (value) { void loadContact(); void loadPlans() } })
watch(() => session.user?.id, () => { reset(); if (props.open) { void loadContact(); void loadPlans() } }, { flush: 'sync' })
onHide(invalidate)
onBeforeUnmount(invalidate)
function service() { emit('close'); navigatePage({ url: '/subpages/membership/index' }) }
function contactService() { emit('close'); navigatePage({ url: '/subpages/membership/index?contact=1' }) }
let revision = 0
useTabBarOverlay(() => props.open)
watch(() => props.open, () => { revision++; error.value = ''; busy.value = false })
onBeforeUnmount(() => { revision++ })
async function refresh() {
  if (busy.value || !session.user) return
  const current = ++revision
  busy.value = true; error.value = ''
  try {
    await refreshMembership({ scope: memberReads.begin(), force: true })
    if (current === revision && props.open) emit('refreshed')
  } catch (cause) { if (current === revision) error.value = errorMessage(cause) }
  finally { if (current === revision) busy.value = false }
}
</script>

<template>
  <wd-popup :model-value="open" position="bottom" :z-index="1200" root-portal safe-area-inset-bottom custom-style="border-radius:22px 22px 0 0" @update:model-value="!$event && emit('close')">
    <view class="sheet membership-sheet" aria-role="dialog" role="dialog" aria-modal="true" aria-label="会员状态">
      <view class="sheet-handle" />
      <view class="sheet-head"><text class="sheet-title">会员状态</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="bare-icon" role="button" aria-label="关闭会员状态" @click="emit('close')"><wd-icon name="close" size="20px" /></button></view>
      <view class="membership-identity"><view class="membership-symbol"><wd-icon name="star-fill" size="25px" /></view><view class="grow"><text class="membership-name">{{ session.user?.is_vip ? 'VIP 会员' : '普通用户' }}</text><text class="membership-expiry">{{ membershipExpiry(session.user) }}</text></view></view>
      <view class="membership-perks"><view><wd-icon name="book" size="17px" /><text>VIP 专享习题</text></view><view><wd-icon name="file-pdf" size="17px" /><text>完整原稿与 PDF</text></view></view>
      <text v-if="expiresSoon && !restricted" class="membership-contact">会员将在 7 天内到期，可提前查看续期套餐。</text>
      <text v-if="contact" class="membership-contact">{{ contact.benefits }}</text>
      <text v-if="plansLoading" class="membership-contact" role="status">正在确认当前平台的会员服务</text>
      <text v-else-if="restricted" class="membership-contact">当前平台暂不支持开通；已有会员权益可正常使用。</text>
      <view v-if="plansError" class="error-strip" role="alert"><text class="grow">开通方式暂时无法确认：{{ plansError }}</text><wd-button role="button" variant="text" :loading="plansLoading" @click="loadPlans()">重试套餐信息</wd-button></view>
      <view v-if="contactError" class="error-strip" role="alert"><text class="grow">客服信息暂时无法加载：{{ contactError }}</text><wd-button role="button" variant="text" :loading="contactLoading" @click="loadContact()">重试客服信息</wd-button></view>
      <view class="membership-refresh"><wd-button v-if="!restricted" role="button" block variant="plain" @click="service">{{ plansKnown ? '会员套餐与卡密' : '查看会员服务' }}</wd-button><wd-button role="button" block variant="text" @click="contactService">查看联系方式</wd-button></view>
      <view v-if="error" class="error-strip">{{ error }}</view>
      <view class="membership-refresh"><wd-button block icon="refresh" role="button" :loading="busy" :disabled="busy || !session.user" @click="refresh">刷新会员状态</wd-button></view>
    </view>
  </wd-popup>
</template>

<style scoped>
.membership-identity { display: flex; align-items: center; gap: 13px; padding: 8px 0 18px; }
.membership-symbol { display: flex; align-items: center; justify-content: center; flex: none; width: 50px; height: 50px; border-radius: 50%; color: var(--lc-warning); background: var(--lc-warning-bg); }
.membership-name { display: block; font-size: 18px; font-weight: 600; }
.membership-expiry { display: block; font-size: 12px; color: var(--lc-muted); margin-top: 4px; }
.membership-perks { display: flex; flex-wrap: wrap; gap: 14px 20px; padding: 12px 0; }
.membership-perks > view { display: flex; align-items: center; gap: 7px; font-size: 12px; color: var(--lc-secondary); }
.membership-perks :deep(.wd-icon) { color: var(--lc-primary); }
.membership-contact { display: block; color: var(--lc-muted); font-size: 12px; margin-top: 8px; }
.membership-refresh { margin-top: 25px; }
</style>
