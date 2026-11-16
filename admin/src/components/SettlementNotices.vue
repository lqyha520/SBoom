<script setup lang="ts">
import { ref, watch } from 'vue'
import { useAdminRefresh } from '../admin-page'
import { notices, readNotices, auditLabels, type Notices } from '../settlement-operations'
import { dateTime } from '../growth'
const props = defineProps<{ actor: number; refreshKey?: number; personal?: boolean }>()
const emit = defineEmits<{ select: [kind: 'requests' | 'statements', q: string]; dispute: [id: string]; unread: [count: number] }>()
const value = ref<Notices | null>(null), error = ref(''), busy = ref(false)
async function load() { try { value.value = await notices(props.personal); emit('unread', value.value.unread); error.value = '' } catch (e) { error.value = e instanceof Error ? e.message : '读取提醒失败' } }
async function mark() { if (!value.value?.items.length || busy.value) return; busy.value = true; try { await readNotices(props.actor, value.value.items[0]!.id, props.personal); await load() } catch (e) { error.value = e instanceof Error ? e.message : '更新失败' } finally { busy.value = false } }
watch(() => props.refreshKey, load); useAdminRefresh(load)
</script>
<template>
  <details class="mb-4 rounded border border-default p-3"><summary class="cursor-pointer font-medium">结算提醒{{ value ? ' · ' + value.unread + ' 条未读' : '' }}</summary><UAlert v-if="error" :title="error" color="error" class="mt-3" /><div class="actions-row mt-3"><UButton label="刷新提醒" variant="outline" @click="load" /><UButton label="标记以上消息已读" variant="outline" :disabled="busy || !value?.unread" @click="mark" /></div><p v-if="value && !value.items.length" class="text-sm mt-3">暂无结算消息</p><ul class="space-y-2 mt-3"><li v-for="item in value?.items" :key="item.id" class="text-sm"><UButton :label="auditLabels[item.kind] || item.kind" variant="link" @click="item.kind.startsWith('dispute_') ? emit('dispute', item.target) : emit('select', ['approve', 'record_payout'].includes(item.kind) ? 'statements' : 'requests', item.target)" /><span>{{ dateTime(item.created_at) }}{{ item.id > (value?.last_id ?? 0) ? ' · 未读' : '' }}</span></li></ul></details>
</template>
