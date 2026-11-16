<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { loadPayee, savePayee, payeeMethods, type Payee } from '../settlement-operations'
const props = defineProps<{ actor: number }>()
const saved = ref<Payee | null>(null), busy = ref(false), error = ref(''), notice = ref('')
const name = ref(''), method = ref<Payee['method']>('bank'), account = ref(''), bank = ref('')
onMounted(async () => { try { saved.value = await loadPayee(); if (saved.value) { name.value = saved.value.name; method.value = saved.value.method; bank.value = saved.value.bank } } catch (e) { error.value = e instanceof Error ? e.message : '读取收款资料失败' } })
async function save() {
  busy.value = true; error.value = ''; notice.value = ''
  try { saved.value = await savePayee(props.actor, { revision: saved.value?.revision ?? 0, name: name.value, method: method.value, account: account.value, bank: bank.value }); account.value = ''; notice.value = '收款资料已保存；已有结算单的收款快照保持原值' }
  catch (e) { error.value = e instanceof Error ? e.message : '保存失败' } finally { busy.value = false }
}
</script>
<template>
  <details open class="rounded border border-default p-4 mb-4"><summary class="cursor-pointer font-medium">我的收款资料 · {{ saved ? saved.name + ' / ' + saved.account : '尚未设置' }}</summary>
    <form class="field-stack mt-4" @submit.prevent="save">
      <UAlert v-if="error" :title="error" color="error" /><UAlert v-if="notice" :title="notice" color="success" />
      <p class="text-xs text-muted">用于超级管理员线下转账核对。账号加密保存，列表仅显示尾号；结算单留存独立快照。</p>
      <div class="actions-row"><UFormField label="收款人" required><UInput v-model="name" required minlength="2" maxlength="80" :disabled="busy" /></UFormField><UFormField label="收款方式"><USelect v-model="method" :items="Object.entries(payeeMethods).map(([value, label]) => ({ value, label }))" :disabled="busy" /></UFormField><UFormField label="完整收款账号（修改时重新填写）" required><UInput v-model="account" required minlength="4" maxlength="120" autocomplete="off" :disabled="busy" /></UFormField><UFormField v-if="method === 'bank'" label="开户行" required><UInput v-model="bank" required maxlength="120" :disabled="busy" /></UFormField></div>
      <UButton label="保存收款资料" type="submit" class="self-start" :loading="busy" />
    </form>
  </details>
</template>
