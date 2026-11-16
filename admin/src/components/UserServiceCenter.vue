<script setup lang="ts">
import { canAdmin } from '../permissions'
import { computed } from 'vue'
import { lazyComponent } from '../../../shared/async-component'
import type { UserInfo } from '../api'
import { userServiceTabs, type UserServiceTab } from '../admin-navigation'
import { navigateAdmin } from '../navigation'

const props = defineProps<{ user: UserInfo; active: UserServiceTab }>()
const views = {
  resourceRequests: lazyComponent(() => import('./ResourceRequests.vue')),
  supportCenter: lazyComponent(() => import('./SupportCenter.vue')),
  feedback: lazyComponent(() => import('./FeedbackPage.vue')),
}
const current = computed(() => userServiceTabs.find(item => item.id === props.active)!)
function select(tab: UserServiceTab) { if (tab !== props.active) navigateAdmin(tab) }
</script>

<template>
  <section class="user-service-center" aria-label="用户服务中心">
    <header class="admin-page-heading">
      <div><div class="page-eyebrow"><span></span>用户服务</div><h1>用户服务中心</h1><p>在这里跟进资料需求、处理小程序问题，并查看出题质量反馈。</p></div>
      <span class="page-heading-icon" aria-hidden="true"><UIcon name="i-lucide-messages-square" class="size-7" /></span>
    </header>
    <nav class="service-navigation" aria-label="用户服务功能">
      <button v-for="item in userServiceTabs.filter(item => canAdmin(item.id))" :key="item.id" type="button" :aria-label="item.label"
        :aria-current="active === item.id ? 'page' : undefined" @click="select(item.id)">
        <span class="service-icon" aria-hidden="true"><UIcon :name="item.icon" class="size-5" /></span>
        <span class="service-label"><strong>{{ item.label }}</strong><span>{{ item.description }}</span></span>
        <UIcon v-if="active === item.id" name="i-lucide-check" class="service-selected size-4" aria-hidden="true" />
      </button>
    </nav>
    <div class="service-context"><div><h2>{{ current.label }}</h2><span>{{ current.source }}</span></div><p>{{ current.hint }}</p></div>
    <div role="region" :aria-label="current.label">
      <KeepAlive :max="3"><component v-if="canAdmin(active)" :is="views[active]" :key="active" :user="user" /></KeepAlive>
    </div>
  </section>
</template>

<style scoped>
.user-service-center { max-width:1440px;min-width:0;margin:0 auto; }
.service-navigation { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:26px; }
.service-navigation button { display:flex;align-items:center;gap:12px;min-width:0;min-height:84px;padding:16px;text-align:left;border:1px solid var(--ui-border);border-radius:12px;background:var(--ui-bg);cursor:pointer; }
.service-navigation button:hover { border-color:#a4c7b8;background:#f7fbf9; }
.service-navigation button[aria-current="page"] { border-color:#79b599;background:#ecf7f0;box-shadow:0 0 0 1px #79b599; }
.service-navigation button:focus-visible { outline:2px solid var(--ui-primary);outline-offset:3px; }
.service-icon { display:grid;place-items:center;flex:none;width:38px;height:38px;border-radius:10px;background:#f0f4f2;color:#58786a; }
[aria-current="page"] .service-icon { background:#d9efdf;color:#087955; }
.service-label { display:grid;gap:5px;min-width:0; }
.service-label strong { color:var(--ui-text-highlighted);font-size:14px;font-weight:600; }
.service-label > span { color:var(--ui-text-muted);font-size:12px;line-height:1.6; }
.service-selected { flex:none;margin-left:auto;color:#087955; }
.service-context { margin-bottom:16px; }
.service-context > div { display:flex;align-items:center;gap:10px;flex-wrap:wrap; }
.service-context h2 { color:var(--ui-text-highlighted);font-size:16px;font-weight:600; }
.service-context span { padding:3px 8px;border-radius:5px;background:#e8efeb;color:#557565;font-size:11px; }
.service-context p { margin:7px 0 0;color:var(--ui-text-muted);font-size:12px;line-height:1.8; }
@media(max-width:1100px) { .service-navigation button { padding:14px 12px;gap:8px; }.service-icon { width:30px;height:30px; }.service-selected { display:none; } }
@media(max-width:650px) { .service-navigation { gap:8px;margin-bottom:20px; }.service-navigation button { flex-direction:column;justify-content:center;gap:8px;min-height:82px;padding:10px 6px;text-align:center; }.service-label strong { font-size:12px; }.service-label > span { display:none; }.service-icon { width:28px;height:28px; }.service-context { margin-bottom:12px; } }
</style>
