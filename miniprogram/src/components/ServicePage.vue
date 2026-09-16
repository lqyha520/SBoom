<script setup lang="ts">
import PageChrome from './PageChrome.vue'
import AuthGate from './AuthGate.vue'
import { session } from '../services/session'
defineProps<{ title: string; description?: string; error?: string; loading?: boolean }>()
defineEmits<{ retry: [] }>()
</script>
<template>
  <view class="service-page">
    <PageChrome back fallback="/pages/account/index" />
    <view class="content-width service-heading"><text class="service-title">{{ title }}</text><text v-if="description" class="service-description">{{ description }}</text></view>
    <AuthGate v-if="!session.user" />
    <view v-else class="content-width service-body">
      <view v-if="error" class="error-strip" role="alert"><text class="grow">{{ error }}</text><wd-button role="button" variant="text" icon="refresh" aria-label="重试加载" @click="$emit('retry')" /></view>
      <view v-if="loading" class="loading-line"><wd-loading /><text>正在加载</text></view>
      <slot />
    </view>
  </view>
</template>
<style>
.service-heading { padding-top:18px;padding-bottom:20px; }.service-title { display:block;font-size:24px;font-weight:650;line-height:1.4; }.service-description { display:block;font-size:13px;color:var(--lc-muted);line-height:1.8;margin-top:8px; }.service-body { padding-bottom:calc(28px + env(safe-area-inset-bottom)); }
.service-card { margin-bottom:14px;padding:18px;border:1px solid var(--lc-card-line);border-radius:14px;background:var(--lc-card);box-shadow:var(--lc-card-shadow-soft);overflow-wrap:anywhere; }.service-card-title { display:block;font-size:16px;font-weight:600;line-height:1.6; }.service-copy { display:block;margin-top:8px;font-size:13px;color:var(--lc-secondary);white-space:pre-wrap;line-height:1.8; }.service-meta { display:block;margin-top:8px;font-size:12px;color:var(--lc-muted);line-height:1.7; }.service-actions { display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-top:16px; }.service-reply { margin-top:14px;padding:12px;border-radius:8px;background:var(--lc-primary-soft);font-size:13px;line-height:1.8;white-space:pre-wrap; }.service-fields { display:flex;flex-direction:column;gap:14px; }.service-fields .field-label { margin-top:8px; }.service-row { display:flex;justify-content:space-between;align-items:center;gap:12px; }.service-empty { padding:28px 0; }
</style>
