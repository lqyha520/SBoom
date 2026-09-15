<script setup lang="ts">
import { computed, ref } from 'vue'
import type { SiteNotice } from '../types'

const props = defineProps<{ notices: SiteNotice[] }>()
// 关闭只作用于本次会话：首页每次冷启动仍会看到，避免管理员发了公告用户却再也看不到
const closed = ref<string[]>([])
const visible = computed(() => props.notices.filter(notice => !closed.value.includes(notice.id)))
const current = computed(() => visible.value[0] || null)
function close() { if (current.value) closed.value = [...closed.value, current.value.id] }
</script>

<template>
  <view v-if="current" class="notice-bar" :class="current.level" role="status">
    <view class="notice-symbol"><wd-icon :name="current.level === 'warning' ? 'exclamation-polygon-fill' : 'notification'" size="15px" /></view>
    <view class="notice-content">
      <text class="notice-title">{{ current.title }}</text>
      <text v-if="current.body" class="notice-body">{{ current.body }}</text>
    </view>
    <button class="bare-icon notice-close" role="button" aria-label="关闭公告" title="关闭" @click="close"><wd-icon name="close" size="15px" /></button>
  </view>
</template>

<style scoped>
.notice-bar { display: flex; align-items: flex-start; gap: 9px; margin: 0 18px 12px; padding: 11px 12px; border-radius: 9px; background: var(--lc-primary-soft); }
.notice-bar.warning { background: var(--lc-warning-bg); }
.notice-symbol { display: flex; align-items: center; justify-content: center; width: 21px; height: 21px; flex: none; margin-top: 1px; color: var(--lc-primary); }
.notice-bar.warning .notice-symbol { color: var(--lc-warning); }
.notice-content { flex: 1; min-width: 0; }
.notice-title { display: block; font-size: 12px; font-weight: 600; line-height: 1.6; color: var(--lc-text); overflow-wrap: anywhere; }
.notice-body { display: block; margin-top: 3px; font-size: 11px; line-height: 1.6; color: var(--lc-secondary); overflow-wrap: anywhere; }
.notice-close { flex: none; width: 28px; min-height: 28px; color: var(--lc-muted); }
@media (max-width: 359px) { .notice-bar { margin-left: 14px; margin-right: 14px; } }
</style>
