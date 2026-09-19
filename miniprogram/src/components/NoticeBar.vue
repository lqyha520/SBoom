<script setup lang="ts">
import { computed, ref } from 'vue'
import type { SiteNotice } from '../types'

const props = defineProps<{ notices: SiteNotice[] }>()
// 关闭只作用于本次会话：首页每次冷启动仍会看到，避免管理员发了公告用户却再也看不到
const closed = ref<string[]>([])
const expandedId = ref('')
const visible = computed(() => props.notices.filter(notice => !closed.value.includes(notice.id)))
const current = computed(() => visible.value[0] || null)
function close() { if (current.value) closed.value = [...closed.value, current.value.id] }
</script>

<template>
  <view v-if="current" class="notice-bar" :class="current.level" role="status">
    <view class="notice-symbol"><wd-icon :name="current.level === 'warning' ? 'exclamation-polygon-fill' : 'notification'" size="15px" /></view>
    <button role="button" class="notice-content" :class="{ expanded: expandedId === current.id }" :aria-expanded="expandedId === current.id" :aria-label="current.title + (current.body ? '，点击展开或收起公告' : '')" hover-class="control-pressed" @click="expandedId = expandedId === current.id ? '' : current.id">
      <text class="notice-title">{{ current.title }}</text>
      <text v-if="current.body && expandedId === current.id" class="notice-body">{{ current.body }}</text>
    </button>
    <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="bare-icon notice-close" role="button" aria-label="关闭公告" title="关闭" @click="close"><wd-icon name="close" size="15px" /></button>
  </view>
</template>

<style scoped>
.notice-bar { display: flex; align-items: center; gap: 8px; margin: 0 var(--lc-page-gutter) 12px; padding: 0 8px 0 12px; border-radius: var(--lc-radius-control); background: var(--lc-primary-soft); }
.notice-bar.warning { background: var(--lc-warning-bg); }
.notice-symbol { display: flex; align-items: center; justify-content: center; width: 21px; height: 21px; flex: none; margin-top: 1px; color: var(--lc-primary); }
.notice-bar.warning .notice-symbol { color: var(--lc-warning); }
.notice-content { flex:1;min-width:0;min-height:44px;padding:10px 0;margin:0;background:transparent;text-align:left;line-height:1.6; }
.notice-title { display: block; font-size: 12px; font-weight: 600; line-height: 1.6; color: var(--lc-text); overflow:hidden;white-space:nowrap;text-overflow:ellipsis; }
.notice-content.expanded .notice-title { white-space:normal;overflow-wrap:anywhere; }
.notice-body { display: block; margin-top: 3px; font-size: 12px; line-height: 1.6; color: var(--lc-secondary); overflow-wrap: anywhere; }
.notice-close { flex: none; width: 44px; min-height: 44px; color: var(--lc-muted); }
</style>
