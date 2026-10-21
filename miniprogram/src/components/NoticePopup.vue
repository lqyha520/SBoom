<script setup lang="ts">
import { computed, ref } from 'vue'
import { useTabBarOverlay } from '../services/tabbar-overlay'
import type { SiteNotice } from '../types'

const props = defineProps<{ notices: SiteNotice[] }>()
const SEEN_KEY = 'lc-seen-notices'

function readSeen(): string[] {
  try {
    const stored = uni.getStorageSync(SEEN_KEY)
    return Array.isArray(stored) ? stored.filter(value => typeof value === 'string') : []
  } catch { return [] }
}

const seen = ref<string[]>(readSeen())
// 逐条展示：确认一条后才轮到下一条，避免多条公告叠成一个弹窗
const queue = computed(() => props.notices.filter(notice => !seen.value.includes(notice.id)))
const current = computed(() => queue.value[0] || null)
useTabBarOverlay(() => !!current.value)

function dismiss() {
  if (!current.value) return
  const next = [...seen.value, current.value.id].slice(-50)
  seen.value = next
  try { uni.setStorageSync(SEEN_KEY, next) } catch { /* 存储不可用时本次会话内仍然生效 */ }
}
</script>

<template>
  <wd-popup :model-value="!!current" position="center" :z-index="1300" root-portal custom-style="background: transparent; box-shadow: none;" @update:model-value="!$event && dismiss()">
    <view v-if="current" class="notice-card" aria-role="dialog" role="dialog" aria-modal="true" :aria-label="current.title">
      <view class="notice-head">
        <view class="notice-level" :class="current.level"><wd-icon :name="current.level === 'warning' ? 'exclamation-polygon-fill' : 'info-circle-fill'" size="16px" /></view>
        <text class="notice-title">{{ current.title }}</text>
        <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="bare-icon" role="button" aria-label="关闭公告" title="关闭" @click="dismiss"><wd-icon name="close" size="17px" /></button>
      </view>
      <scroll-view v-if="current.body" scroll-y class="notice-body"><text class="notice-text">{{ current.body }}</text></scroll-view>
      <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="notice-confirm" role="button" @click="dismiss"><text>我知道了</text></button>
    </view>
  </wd-popup>
</template>

<style scoped>
.notice-card { width: 78vw; max-width: 420px; padding: 22px 22px 18px; border-radius: 14px; background: #fff; }
.notice-head { display: flex; align-items: center; gap: 9px; }
.notice-level { display: flex; align-items: center; justify-content: center; width: 30px; height: 30px; flex: none; border-radius: 50%; color: var(--lc-primary); background: var(--lc-primary-soft); }
.notice-level.warning { color: var(--lc-warning); background: var(--lc-warning-bg); }
.notice-title { flex: 1; min-width: 0; font-size: 16px; font-weight: 650; color: var(--lc-text); overflow-wrap: anywhere; }
.notice-body { max-height: 42vh; margin-top: 14px; }
.notice-text { display: block; font-size: 14px; line-height: 1.9; color: var(--lc-secondary); white-space: pre-wrap; overflow-wrap: anywhere; }
.notice-confirm { width: 100%; min-height: 46px; margin: 20px 0 0; border-radius: 999px; background: var(--lc-primary); color: #fff; font-size: 14px; line-height: 46px; }
</style>
