<script setup lang="ts">
import PageChrome from '../../components/PageChrome.vue'
import AuthGate from '../../components/AuthGate.vue'
import { session } from '../../services/session'
withDefaults(defineProps<{ title: string; description?: string; gateTitle?: string; gateDescription?: string; error?: string; loading?: boolean }>(), { gateDescription: '登录后可以查看和管理自己的记录' })
defineEmits<{ retry: [] }>()
</script>
<template>
  <view class="service-page">
    <view class="page-navigation-sticky"><PageChrome back fallback="/pages/account/index" /></view>
    <view class="content-width service-heading"><text class="service-title">{{ title }}</text><text v-if="description" class="service-description">{{ description }}</text></view>
    <AuthGate v-if="!session.user" :title="gateTitle || ('登录查看' + title)" :description="gateDescription" browse @restored="$emit('retry')" />
    <view v-else class="content-width service-body">
      <view v-if="error" class="error-strip" role="alert"><text class="grow">{{ error }}</text><wd-button role="button" variant="text" icon="refresh" aria-label="重试加载" @click="$emit('retry')" /></view>
      <view v-if="loading" class="loading-line"><wd-loading /><text>正在加载</text></view>
      <slot />
    </view>
  </view>
</template>
