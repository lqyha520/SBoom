<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { billImports, billDetails, billTemplate, importBill, type BillImport, type BillRow } from '../settlement-operations'
import { dateTime, yuan } from '../growth'
const props = defineProps<{ actor: number; editable?: boolean }>()
const emit = defineEmits<{ updated: [] }>()
const items = ref<BillImport[]>([]), rows = ref<BillRow[]>([]), name = ref(''), content = ref(''), evidence = ref(''), busy = ref(false), error = ref(''), notice = ref('')
const limit = ref(50)
async function run(operation: () => Promise<unknown>) { if (busy.value) return; busy.value = true; error.value = ''; try { await operation() } catch (e) { error.value = e instanceof Error ? e.message : '读取或导入失败' } finally { busy.value = false } }
async function load() { items.value = (await billImports()).items }
function file(event: Event) { const value = (event.target as HTMLInputElement).files?.[0]; if (value) void run(async () => { if (value.size > 500000) throw new Error('CSV 文件最多 500KB'); name.value = value.name; content.value = await value.text() }) }
function submit() { void run(async () => { const result = await importBill(props.actor, { name: name.value, evidence: evidence.value, content: content.value }); notice.value = (result.duplicate ? '账单已导入过，已打开原记录' : '已导入 ' + result.orders + ' 笔账单'); await load(); rows.value = (await billDetails(result.id)).items; limit.value = 50; emit('updated') }) }
onMounted(() => { void run(load) })
</script>
<template>
  <details open class="rounded border border-default p-4 mb-4"><summary class="cursor-pointer font-medium">渠道账单辅助核对</summary>
    <div class="field-stack mt-3"><UAlert v-if="error" :title="error" color="error" /><UAlert v-if="notice" :title="notice" color="success" />
      <p class="text-sm">从渠道后台取得账单后，按模板整理导入。导入仅用于对账；费用采用仍需明确确认，订单和退款状态以支付系统为准。</p>
      <p class="text-xs text-muted">渠道填写 wechat / virtual_android / virtual_ios；实收填原订单实际收款总额，手续费填该笔实际金额，退款单独填列，交易日期填北京时间付款日期。UTF-8 CSV，最多 5000 行 / 500KB。</p>
      <UButton label="下载渠道账单模板" variant="outline" class="self-start" :disabled="busy" @click="run(billTemplate)" />
      <form v-if="editable !== false" class="field-stack" @submit.prevent="submit"><UFormField label="账单 CSV" required><input type="file" accept=".csv,text/csv" :disabled="busy" @change="file"></UFormField><UFormField label="账单来源 / 核对依据" required><UTextarea v-model="evidence" required minlength="2" maxlength="1000" :disabled="busy" /></UFormField><UButton label="导入并检查差异" type="submit" class="self-start" :loading="busy" :disabled="busy || !content || evidence.trim().length < 2" /></form>
      <details v-if="items.length"><summary class="cursor-pointer">最近导入的账单</summary><p v-for="item in items" :key="item.id" class="mt-2 text-sm"><UButton :label="item.name" variant="link" :disabled="busy" @click="run(async () => { rows = (await billDetails(item.id)).items; limit = 50 })" />{{ item.orders }} 笔 · {{ dateTime(item.created_at) }}</p></details>
      <div v-if="rows.length" class="data-scroll"><table class="data-table"><thead><tr><th>订单 / 渠道</th><th>实收 / 手续费 / 退款</th><th>核对结果</th></tr></thead><tbody><tr v-for="row in rows.slice(0, limit)" :key="row.id"><td class="break-all">{{ row.order_id }}<p>{{ row.channel_label }}</p></td><td>{{ yuan(row.amount_fen) }} / {{ yuan(row.channel_fee_fen) }} / {{ yuan(row.refunded_fen) }}</td><td>{{ !row.check ? '本地没有对应订单' : row.check.bill_row_id !== row.id ? '已有后续导入，请以最新账单核对' : row.check.differences.length ? row.check.differences.join('；') : row.check.fee_difference ? '已核定手续费与账单不同' : '关键字段一致，可在申请中采用手续费' }}</td></tr></tbody></table></div><UButton v-if="rows.length > limit" label="显示更多账单" variant="outline" @click="limit += 50" />
    </div>
  </details>
</template>
