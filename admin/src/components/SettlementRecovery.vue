<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { recoveryPreview, recoverApplication, type RecoveryPreview } from '../settlement-operations'
import type { SettlementApplication } from '../settlements'
const props = defineProps<{ actor: number; item: SettlementApplication }>()
const emit = defineEmits<{ recovered: [id: string]; busy: [value: boolean] }>()
const preview = ref<RecoveryPreview | null>(null), reason = ref(''), confirmed = ref(false), busy = ref(false), error = ref('')
async function load() { error.value = ''; confirmed.value = false; try { preview.value = await recoveryPreview(props.item.id) } catch (e) { error.value = e instanceof Error ? e.message : '读取可恢复订单失败' } }
async function save() { if (!confirmed.value || busy.value || !preview.value?.order_ids.length) return; busy.value = true; emit('busy', true); error.value = ''; try { const value = await recoverApplication(props.actor, { ...props.item, revision: preview.value.revision }, reason.value); emit('busy', false); busy.value = false; emit('recovered', value.id) } catch (e) { confirmed.value = false; error.value = e instanceof Error ? e.message : '重新核算失败，请刷新'; } finally { busy.value = false; emit('busy', false) } }
onMounted(load)
</script>
<template>
  <form class="rounded border border-default p-3 field-stack" @submit.prevent="save"><p class="font-medium">剔除异常订单，重新核算申请</p><UAlert v-if="error" :title="error" color="error" /><UButton label="刷新可恢复订单" variant="outline" class="self-start" :disabled="busy" @click="load" />
    <template v-if="preview"><p>可保留 {{ preview.order_ids.length }} 笔，排除 {{ preview.excluded.length }} 笔。保留正常订单已核对的费用；原申请留档，生成关联的新申请。</p><p v-for="item in preview.excluded" :key="item.order_id" class="text-sm break-all">{{ item.order_id }}：{{ item.reason }}</p>
      <UFormField label="重新申请原因" required><UTextarea v-model="reason" required minlength="2" maxlength="500" :disabled="busy" /></UFormField><UCheckbox v-model="confirmed" label="已核对保留订单与排除原因，确认生成新的申请" :disabled="busy" /><UButton label="确认剔除异常并重新申请" type="submit" class="self-start" :loading="busy" :disabled="busy || !confirmed || !preview.order_ids.length || reason.trim().length < 2" />
    </template>
  </form>
</template>
