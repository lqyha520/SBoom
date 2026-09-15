<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { errorMessage } from '../services/api'
import { refreshMembership, session } from '../services/session'
import { useTabBarOverlay } from '../services/tabbar-overlay'
import { membershipExpiry } from '../presentation'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: []; refreshed: [] }>()
const busy = ref(false)
const error = ref('')
let revision = 0
useTabBarOverlay(() => props.open)
watch(() => props.open, () => { revision++; error.value = ''; busy.value = false })
onBeforeUnmount(() => { revision++ })
async function refresh() {
  if (busy.value || !session.user) return
  const current = ++revision
  busy.value = true; error.value = ''
  try {
    await refreshMembership()
    if (current === revision && props.open) emit('refreshed')
  } catch (cause) { if (current === revision) error.value = errorMessage(cause) }
  finally { if (current === revision) busy.value = false }
}
</script>

<template>
  <wd-popup :model-value="open" position="bottom" :z-index="1200" root-portal safe-area-inset-bottom custom-style="border-radius:8px 8px 0 0" @update:model-value="!$event && emit('close')">
    <view class="sheet membership-sheet" role="dialog" aria-modal="true" aria-label="会员状态">
      <view class="sheet-handle" />
      <view class="sheet-head"><text class="sheet-title">会员状态</text><button class="bare-icon" role="button" aria-label="关闭会员状态" @click="emit('close')"><wd-icon name="close" size="20px" /></button></view>
      <view class="membership-identity"><view class="membership-symbol"><wd-icon name="star-fill" size="25px" /></view><view class="grow"><text class="membership-name">{{ session.user?.is_vip ? 'VIP 会员' : '普通用户' }}</text><text class="membership-expiry">{{ membershipExpiry(session.user) }}</text></view></view>
      <view class="membership-perks"><view><wd-icon name="book" size="17px" /><text>VIP 专享习题</text></view><view><wd-icon name="file-pdf" size="17px" /><text>完整原稿与 PDF</text></view></view>
      <text class="membership-contact">开通与续期请联系运营管理员</text>
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
