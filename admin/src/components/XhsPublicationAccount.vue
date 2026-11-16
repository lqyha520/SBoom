<script setup lang="ts">
import { permissionDirective as vPermission, canAdmin } from '../permissions'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { listXhsAccounts, type XhsAccount } from '../xhs-accounts'
import { navigateAdmin } from '../navigation'
import { workflowError } from '../xhs-workflow'

const props = defineProps<{ current: { id: string; name: string }; disabled?: boolean }>()
const emit = defineEmits<{ apply: [value: { id: string; name: string }] }>()
const accounts = ref<XhsAccount[]>([]), loading = ref(false), error = ref('')
let active = true, sequence = 0
const selection = computed({
  get: () => props.current.id || (props.current.name ? '__manual__' : ''),
  set: value => {
    if (value === '__manual__' || !value) { emit('apply', { id: '', name: props.current.name }); return }
    const account = accounts.value.find(item => item.id === value)
    if (account) emit('apply', { id: account.id, name: account.name })
  },
})
const retained = computed(() => props.current.id && !accounts.value.some(item => item.id === props.current.id))
async function load() {
  if (!canAdmin('xhsAccounts')) return
  if (loading.value) return
  const seq = ++sequence
  loading.value = true; error.value = ''
  try {
    const result = await listXhsAccounts()
    if (active && seq === sequence) accounts.value = result.items.filter(item => !item.archived)
  } catch (cause) { if (active && seq === sequence) error.value = workflowError(cause) }
  finally { if (active && seq === sequence) loading.value = false }
}
onMounted(() => { void load() })
onBeforeUnmount(() => { active = false; ++sequence })
</script>

<template>
  <div class="workflow-field workflow-wide publication-account">
    <label for="publication-account-select">发布账号</label>
    <div class="workflow-actions">
      <select id="publication-account-select" v-model="selection" class="workflow-native" aria-label="选择发布账号" :disabled="disabled">
        <option value="" disabled>{{ loading ? '正在加载账号…（也可在下方填写昵称）' : '请选择已保存的小红书账号' }}</option>
        <option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.name }}</option>
        <option v-if="retained" :value="current.id">{{ current.name || '已关联账号' }}</option>
        <option value="__manual__">手动填写账号昵称</option>
      </select>
      <UButton label="刷新账号列表" variant="outline" :loading="loading" :disabled="disabled" @click="load" />
      <UButton v-permission="'xhsAccounts:view'" label="管理小红书账号" variant="link" :disabled="disabled" @click="navigateAdmin('xhsAccounts')" />
    </div>
    <p v-if="current.id" class="workflow-hint">已选择：{{ current.name }}。辅助填入会使用这个账号的浏览器。</p>
    <label v-else class="workflow-field"><span>或先填写发布账号昵称</span><UInput :model-value="current.name" aria-label="发布账号" maxlength="120" :disabled="disabled" placeholder="没有配置账号时，也可以先填昵称准备文案" @update:model-value="emit('apply',{id:'',name:String($event)})" /></label>
    <p v-if="!loading && !error && !accounts.length" class="workflow-hint">还没有可选账号。到“管理小红书账号”添加后，回来点击刷新即可选择。</p>
    <UAlert v-if="error" title="账号列表暂时无法加载，可先填写昵称准备图文，稍后再刷新账号列表。" color="warning" />
  </div>
</template>

<style scoped>
.publication-account select { flex:1;min-width:180px;max-width:100%; }
.publication-account > label:first-child { color:#526c5d; }
</style>
