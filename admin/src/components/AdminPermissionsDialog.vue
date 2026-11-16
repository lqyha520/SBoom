<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { request, type AdminUser } from '../api'
import { useDialogDraft } from '../dialog-draft'

interface Menu { id: string; label: string; group: string; actions: string[]; super_only: boolean }
interface Assignment { admin_permissions: Record<string, string[]>; permissions_revision: number }
const props = defineProps<{ user: AdminUser }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const open = ref(true)
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const conflict = ref(false)
const menus = ref<Menu[]>([])
const labels = ref<Record<string, string>>({})
const permissions = ref<Record<string, string[]>>({})
const revision = ref(0)
const groups = computed(() => [...new Set(menus.value.map(menu => menu.group))])
const selected = computed(() => Object.values(permissions.value).filter(actions => actions.includes('view')).length)
const draft = useDialogDraft(open, () => permissions.value, busy, '菜单与按钮权限')

async function load() {
  loading.value = true; error.value = ''; conflict.value = false
  try {
    const [catalog, current] = await Promise.all([
      request<{ menus: Menu[]; actions: Record<string, string> }>('/api/v1/admin/access/catalog'),
      request<Assignment>(`/api/v1/admin/access/users/${props.user.id}`),
    ])
    menus.value = catalog.menus.filter(menu => !menu.super_only)
    labels.value = catalog.actions
    permissions.value = Object.fromEntries(menus.value.map(menu => [menu.id,
      (current.admin_permissions[menu.id] || []).filter(action => menu.actions.includes(action))]))
    revision.value = current.permissions_revision
    draft.markSaved()
  } catch (e) { error.value = e instanceof Error ? e.message : '读取权限失败' }
  finally { loading.value = false }
}
function toggle(menu: Menu, action: string, checked: boolean) {
  const current = new Set(permissions.value[menu.id] || [])
  if (checked) { current.add('view'); current.add(action) }
  else if (action === 'view') current.clear()
  else current.delete(action)
  permissions.value = { ...permissions.value, [menu.id]: menu.actions.filter(value => current.has(value)) }
}
function selectGroup(group: string | null, checked: boolean) {
  const next = { ...permissions.value }
  for (const menu of menus.value) if (!group || menu.group === group) next[menu.id] = checked ? [...menu.actions] : []
  permissions.value = next
}
async function save() {
  if (busy.value || !revision.value || conflict.value) return
  busy.value = true; error.value = ''
  try {
    await request(`/api/v1/admin/access/users/${props.user.id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ revision: revision.value, permissions: permissions.value }),
    })
    emit('saved'); emit('close')
  } catch (e) {
    error.value = e instanceof Error ? e.message : '保存权限失败'
    conflict.value = typeof e === 'object' && e !== null && 'status' in e && e.status === 409
  } finally { busy.value = false }
}
onMounted(load)
</script>

<template>
  <UModal v-model:open="draft.model.value" :title="'分配权限 · ' + user.username" :ui="{ content: 'max-w-5xl' }" :dismissible="!busy" :close="!busy" @after:leave="emit('close')">
    <template #body>
      <p class="text-sm text-muted mb-4">勾选可查看的菜单，再选择允许使用的操作。取消“查看”会同时取消该菜单的全部操作；保存后接口权限立即生效。</p>
      <UAlert v-if="error" :title="error" color="error" class="mb-4" role="alert" />
      <UButton v-if="conflict || (error && !revision)" label="重新加载权限" color="neutral" variant="outline" @click="load" />
      <p v-if="loading" role="status">正在读取权限…</p>
      <template v-else-if="revision">
        <div class="flex gap-3 items-center mb-4"><UButton label="全选" variant="outline" size="sm" :disabled="busy" @click="selectGroup(null, true)" /><UButton label="清空" color="neutral" variant="outline" size="sm" :disabled="busy" @click="selectGroup(null, false)" /><span class="text-sm">已授权 {{ selected }} 个菜单</span></div>
        <fieldset v-for="group in groups" :key="group" :disabled="busy" class="permission-group">
          <legend>{{ group }}</legend>
          <div class="flex gap-3 mb-2"><UButton label="全选本组" size="xs" variant="link" @click="selectGroup(group, true)" /><UButton label="清空本组" size="xs" color="neutral" variant="link" @click="selectGroup(group, false)" /></div>
          <div v-for="menu in menus.filter(item => item.group === group)" :key="menu.id" class="permission-row">
            <strong>{{ menu.label }}</strong>
            <label v-for="action in menu.actions" :key="action"><input type="checkbox" :aria-label="menu.label + '：' + (menu.id === 'settlements' && action === 'create' ? '申请结算' : labels[action])" :checked="permissions[menu.id]?.includes(action)" @change="toggle(menu, action, ($event.target as HTMLInputElement).checked)">{{ menu.id === 'settlements' && action === 'create' ? '申请结算' : labels[action] }}</label>
          </div>
        </fieldset>
        <p class="text-xs text-muted mt-3">管理员账号和授权管理仅限超级管理员，不能分配给普通管理员。</p>
      </template>
    </template>
    <template #footer><div class="flex justify-end gap-3 w-full"><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="draft.model.value = false" /><UButton label="保存权限" :loading="busy" :disabled="loading || !revision || conflict" @click="save" /></div></template>
  </UModal>
</template>

<style scoped>
.permission-group { border:1px solid var(--ui-border);border-radius:10px;padding:12px 16px;margin-bottom:16px; }
legend { padding:0 6px;font-weight:600; }
.permission-row { display:flex;align-items:center;gap:12px;flex-wrap:wrap;border-top:1px solid var(--ui-border-muted);padding:12px 0;font-size:13px; }
.permission-row strong { width:140px;font-weight:500; }
.permission-row label { display:flex;align-items:center;gap:5px;cursor:pointer;min-height:30px; }
input { accent-color:var(--ui-primary);width:16px;height:16px; }
@media(max-width:650px) { .permission-row strong { width:100%; } }
</style>
