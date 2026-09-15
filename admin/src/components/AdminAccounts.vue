<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import * as api from '../api'

const props = defineProps<{ user: api.UserInfo }>()
const accounts = ref<api.AdminUser[]>([])
const query = ref('')
const loading = ref(false)
const error = ref('')
const notice = ref('')
const page = ref(1)
const pageSize = 20
const rows = computed(() => accounts.value.slice((page.value - 1) * pageSize, page.value * pageSize))
type Action = 'create' | 'password' | 'revoke' | 'active' | 'delete'
const action = ref<Action>('create')
const target = ref<api.AdminUser | null>(null)
const dialogOpen = ref(false)
const dialogError = ref('')
const busy = ref(false)
const form = ref({ username: '', password: '' })
const dialogTitle = computed(() => ({
  create: '新建管理员', password: '重置密码', revoke: '取消管理员权限',
  active: target.value?.is_active ? '停用账号' : '启用账号', delete: '删除账号',
})[action.value])
const destructive = computed(() => action.value === 'delete' || (action.value === 'active' && !!target.value?.is_active))
const valid = computed(() => action.value === 'create'
  ? form.value.username.trim().length >= 2 && form.value.password.length >= 6
  : action.value !== 'password' || form.value.password.length >= 6)
let request = 0
async function load(resetPage = false) {
  const id = ++request
  loading.value = true
  error.value = ''
  try {
    const result = await api.fetchAdminUsers(query.value.trim(), 'admin')
    if (id !== request) return
    accounts.value = result
    page.value = resetPage ? 1 : Math.min(page.value, Math.max(1, Math.ceil(result.length / pageSize)))
  } catch (e: unknown) {
    if (id === request) error.value = e instanceof Error ? e.message : '管理员列表加载失败'
  } finally { if (id === request) loading.value = false }
}
function show(next: Action, user: api.AdminUser | null = null) {
  // 自己的账号只允许改密码，降级/停用/删除一律交给后端护栏兜底
  if (user?.id === props.user.id && next !== 'password') return
  action.value = next
  target.value = user
  form.value = { username: '', password: '' }
  dialogError.value = ''
  dialogOpen.value = true
}
function actions(user: api.AdminUser) {
  const self = user.id === props.user.id
  return [[
    { label: '重置密码', icon: 'i-lucide-key-round', onSelect: () => show('password', user) },
    { label: '取消管理员权限', icon: 'i-lucide-shield-off', disabled: self, onSelect: () => show('revoke', user) },
    { label: user.is_active ? '停用账号' : '启用账号', icon: user.is_active ? 'i-lucide-user-round-x' : 'i-lucide-user-round-check', disabled: self, onSelect: () => show('active', user) },
  ], [{ label: '删除账号', icon: 'i-lucide-trash-2', color: 'error' as const, disabled: self, onSelect: () => show('delete', user) }]]
}
async function submit() {
  if (busy.value || !valid.value) return
  if (target.value?.id === props.user.id && action.value !== 'password') return
  busy.value = true
  dialogError.value = ''
  try {
    if (action.value === 'create') await api.adminCreateUser({ username: form.value.username.trim(), password: form.value.password, role: 'admin' })
    else if (target.value) {
      const user = target.value
      if (action.value === 'delete') await api.adminDeleteUser(user.id)
      else await api.adminUpdateUser(user.id, action.value === 'password' ? { password: form.value.password }
        : action.value === 'revoke' ? { role: 'user' } : { is_active: !user.is_active })
    }
    notice.value = dialogTitle.value + '成功' + (action.value === 'revoke' ? '，该账号已移回「出题用户」' : '')
    dialogOpen.value = false
    form.value.password = ''
    await load()
  } catch (e: unknown) { dialogError.value = e instanceof Error ? e.message : '操作失败，请重试' }
  finally { busy.value = false }
}
watch(dialogOpen, open => { if (!open) form.value.password = '' })
onMounted(() => load())
</script>

<template>
  <section class="admin-section" aria-label="管理员账号">
    <UAlert color="warning" variant="soft" icon="i-lucide-shield-alert" class="notice" title="管理员可访问整个后台，包括用户数据、系统配置与日志。请只为确实需要的人开通，并优先使用独立的个人账号而非共享账号。" />
    <div class="section-toolbar">
      <form class="table-search" @submit.prevent="load(true)"><UInput v-model="query" icon="i-lucide-search" placeholder="搜索管理员用户名" aria-label="搜索管理员用户名"><template v-if="query" #trailing><UButton icon="i-lucide-x" color="neutral" variant="link" size="xs" aria-label="清空搜索" @click="query = ''; load(true)" /></template></UInput><UButton type="submit" icon="i-lucide-arrow-right" color="neutral" variant="outline" aria-label="搜索管理员" :loading="loading" /></form>
      <div class="actions-row"><UTooltip text="刷新列表"><UButton icon="i-lucide-refresh-cw" color="neutral" variant="ghost" aria-label="刷新管理员列表" :loading="loading" @click="load()" /></UTooltip><UButton icon="i-lucide-shield-plus" label="新建管理员" @click="show('create')" /></div>
    </div>
    <UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" role="alert" />
    <UAlert v-if="notice" :title="notice" color="success" variant="soft" class="notice" close @update:open="notice = ''" />
    <div class="data-scroll" :aria-busy="loading"><table class="data-table"><thead><tr><th scope="col">账号</th><th scope="col">状态</th><th scope="col">创建时间</th><th scope="col"><span class="sr-only">操作</span></th></tr></thead><tbody>
      <tr v-for="item in rows" :key="item.id" :class="{ 'disabled-row': !item.is_active }">
        <td class="name-cell">{{ item.username }}<UBadge v-if="item.id === user.id" size="xs" color="neutral" variant="soft" class="ml-2">我</UBadge><div class="text-dimmed text-[10px] font-normal mt-1">ID {{ item.id }}</div></td>
        <td><UBadge :color="item.is_active ? 'success' : 'neutral'" variant="soft" size="sm">{{ item.is_active ? '启用' : '停用' }}</UBadge></td>
        <td class="date-cell">{{ item.created_at }}</td>
        <td><UDropdownMenu :items="actions(item)"><UButton icon="i-lucide-ellipsis" color="neutral" variant="ghost" size="sm" :aria-label="item.username + ' 的账号操作'" /></UDropdownMenu></td>
      </tr>
      <tr v-if="!rows.length"><td colspan="4"><div class="empty-state"><UIcon :name="loading ? 'i-lucide-loader-circle' : 'i-lucide-shield-check'" class="size-7" :class="{ 'animate-spin': loading }" /><h3>{{ loading ? '正在加载管理员' : error ? '管理员列表暂不可用' : query ? '没有匹配的管理员' : '暂无管理员账号' }}</h3></div></td></tr>
    </tbody></table></div>
    <div class="table-footer"><span>共 {{ accounts.length }} 个管理员账号</span><UPagination v-if="accounts.length > pageSize" v-model:page="page" :total="accounts.length" :items-per-page="pageSize" :sibling-count="1" size="sm" /></div>
    <UModal v-model:open="dialogOpen" :title="dialogTitle" :dismissible="!busy" :close="!busy">
      <template #body>
        <form id="admin-account-form" class="field-stack" @submit.prevent="submit">
          <template v-if="action === 'create'"><UFormField label="用户名" required><UInput v-model="form.username" minlength="2" maxlength="32" placeholder="2 至 32 位用户名" autocomplete="off" :disabled="busy" required autofocus /></UFormField><UFormField label="初始密码" required><UInput v-model="form.password" type="password" minlength="6" autocomplete="new-password" placeholder="至少 6 位" :disabled="busy" required /></UFormField><UAlert color="info" variant="soft" title="该账号将以管理员身份创建，可访问整个后台。" /></template>
          <template v-else-if="action === 'password'"><p class="text-sm text-toned">{{ target?.username }}</p><UFormField label="新密码" required><UInput v-model="form.password" type="password" minlength="6" autocomplete="new-password" placeholder="至少 6 位" :disabled="busy" required autofocus /></UFormField><UAlert color="warning" variant="soft" title="修改密码后，该账号的已有登录会话将失效。" /></template>
          <UAlert v-else-if="action === 'revoke'" color="warning" variant="soft" :title="'确认取消「' + target?.username + '」的管理员权限？该账号将失去后台访问权限，并移回「出题用户」列表。'" icon="i-lucide-shield-off" />
          <UAlert v-else-if="action === 'delete'" color="error" variant="soft" :title="'确认删除账号「' + target?.username + '」？其模板与配置将一并删除，此操作不可恢复。'" icon="i-lucide-triangle-alert" />
          <UAlert v-else-if="action === 'active'" :color="target?.is_active ? 'warning' : 'info'" variant="soft" :title="target?.is_active ? '停用「' + target?.username + '」后，其现有会话将立即失效，且无法登录后台。' : '确认重新启用「' + target?.username + '」？'" />
          <UAlert v-if="dialogError" :title="dialogError" color="error" variant="soft" role="alert" />
        </form>
      </template>
      <template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="dialogOpen = false" /><UButton type="submit" form="admin-account-form" :label="action === 'create' ? '创建管理员' : '确认'" :color="destructive ? 'error' : 'primary'" :loading="busy" :disabled="busy || !valid" /></template>
    </UModal>
  </section>
</template>
