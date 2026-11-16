<script setup lang="ts">
import { canAdmin } from '../permissions'
import { onMounted, ref, watch } from 'vue'
import { emptyAccountProfile, listXhsAccounts, type AccountSnapshot, type XhsAccount } from '../xhs-accounts'
import { workflowError } from '../xhs-workflow'
const props = withDefaults(defineProps<{ current?: Pick<AccountSnapshot, 'id' | 'name'>; label?: string; disabled?: boolean }>(), { label: '应用账号定位' })
const emit = defineEmits<{ apply: [value: AccountSnapshot] }>()
const items = ref<XhsAccount[]>([]), selected = ref(props.current?.id || ''), error = ref(''), loading = ref(false)
watch(() => props.current?.id, id => { selected.value = id || '' })
async function load() { if (!canAdmin('xhsAccounts')) return; loading.value = true; error.value = ''; try { items.value = (await listXhsAccounts()).items.filter(item => !item.archived) } catch (cause) { error.value = workflowError(cause) } finally { loading.value = false } }
function apply() { const item = items.value.find(item => item.id === selected.value); if (item) emit('apply', { ...emptyAccountProfile(), ...item.profile, id: item.id, name: item.name }) }
onMounted(load)
</script>
<template><div v-if="canAdmin('xhsAccounts')" class="workflow-step workflow-wide"><div class="workflow-actions"><USelect v-model="selected" :items="items.map(item=>({value:item.id,label:item.name}))" aria-label="选择定位账号" placeholder="选择本机账号" :disabled="disabled || loading" /><UButton :label="label" variant="outline" :disabled="disabled || !items.some(item=>item.id===selected)" @click="apply" /><UButton label="刷新账号档案" variant="ghost" :loading="loading" @click="load" /><a href="#xhsAccounts">管理账号定位</a></div><p v-if="current?.id" class="workflow-hint">已保存账号：{{ current.name }}。账号档案后续修改不会覆盖这里保存的内容，可重新应用。</p><p v-if="error" role="alert" class="workflow-hint">{{ error }}</p></div></template>
