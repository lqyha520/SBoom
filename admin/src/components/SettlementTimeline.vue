<script setup lang="ts">
import { auditLabels, type AuditEntry } from '../settlement-operations'
import { dateTime } from '../growth'
defineProps<{ items: AuditEntry[] }>()
</script>
<template>
  <details v-if="items.length" class="rounded border border-default p-3"><summary class="cursor-pointer font-medium">操作时间线（最近 {{ items.length }} 条）</summary>
    <ol class="space-y-3 mt-3"><li v-for="item in items" :key="item.id" class="text-sm border-l-2 border-primary pl-3"><p>{{ dateTime(item.created_at) }} · {{ item.actor_name || '系统' }} · {{ auditLabels[item.kind] || item.kind }}</p><p class="text-xs text-muted break-all">{{ item.target }}</p><p class="whitespace-pre-wrap">{{ item.value.reason || item.value.difference_reason || item.value.evidence || item.value.name }}</p><p v-if="item.value.new_request_id" class="break-all">新申请：{{ item.value.new_request_id }}</p><p v-if="item.value.source_request_id" class="break-all">原申请：{{ item.value.source_request_id }}</p></li></ol>
  </details>
</template>
