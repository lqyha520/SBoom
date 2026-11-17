<script setup lang="ts">
import { computed } from 'vue'
import { dateTime } from '../growth'
import { settlementTarget, type ServiceTerms } from '../settlement-timing'
const props = defineProps<{ status: string; terms?: ServiceTerms; submittedAt: number; approvedAt?: number | null }>()
const target = computed(() => settlementTarget(props.status, props.terms, props.submittedAt, props.approvedAt))
</script>
<template>
  <p v-if="target" class="text-xs mt-1" :class="target.dueAt !== null && target.dueAt < Date.now()/1000 ? 'text-warning' : 'text-muted'">{{ target.label }}：{{ target.dueAt === null ? '提交时未设置，请与财务明确' : dateTime(target.dueAt) }}<span v-if="target.dueAt !== null && target.dueAt < Date.now()/1000"> · 已超过目标时间</span></p>
</template>
