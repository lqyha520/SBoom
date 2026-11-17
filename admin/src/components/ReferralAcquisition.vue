<script setup lang="ts">
import { ref, watch } from 'vue'
import { acquisition, type Acquisition } from '../referral-operations'
import type { ConversionFilters } from '../referral-conversion'
import { useAdminPage } from '../admin-page'
import { dateTime } from '../growth'
const props = defineProps<{ filters: ConversionFilters }>()
const value = ref<Acquisition | null>(null)
const page = useAdminPage(async valid => { const result = await acquisition(props.filters); if (valid()) value.value = result })
watch(() => JSON.stringify(props.filters), () => { value.value = null; void page.load() })
</script>
<template>
  <details class="promotion-panel mb-5"><summary class="cursor-pointer font-semibold">推广入口访问与注册</summary><div class="field-stack mt-4">
    <p class="text-sm text-muted">按入口访问日期追踪同一批访问。一次入口保留 7 天；重复打开不重复计数，不等于独立人数。仅统计支持追踪的新版本客户端。</p>
    <UAlert v-if="page.error.value" :title="page.error.value" color="error" /><UButton label="刷新入口数据" variant="ghost" :loading="page.loading.value" @click="page.load" />
    <template v-if="value && !page.error.value"><p class="text-xs text-muted">服务端开始记录时间：{{ dateTime(value.tracking_since) }}。旧版本访问和更早历史数据无法补齐。</p>
      <dl v-if="value.visits" class="promotion-metrics"><div><dt>入口访问</dt><dd>{{ value.visits }}</dd></div><div><dt>开始注册 / 登录</dt><dd>{{ value.started }}</dd></div><div><dt>新用户注册成功</dt><dd>{{ value.registered }}</dd></div><div><dt>后续曾付费</dt><dd>{{ value.paid }}</dd></div></dl>
      <p v-else class="text-sm text-muted">当前范围暂无可追踪的入口访问。请确认新版小程序已发布并从推广入口进入；此处不代表历史访问量为零。</p>
    </template>
  </div></details>
</template>
