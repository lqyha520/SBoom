<script setup lang="ts">
import { useAdminListRoute } from '../navigation'
import { computed, onActivated, onDeactivated, ref, watch } from 'vue'
import MemberTools from './MemberTools.vue'
import type { UserInfo } from '../api'
import { nicknameError, registrationAccountError } from '../../../shared/mini-profile'
import {
  AVATAR_CHOICES, avatarGlyph, createMiniUser, deleteMiniUser, miniUsers,
  updateMembership, updateMiniProfile, type MiniProfileEdit, type MiniUser,
} from '../mini'

const props = defineProps<{ user: UserInfo }>()
const items = ref<MiniUser[]>([])
const total = ref(0)
const page = ref(1)
const q = ref('')
const membership = ref('all')
const loading = ref(false)
const error = ref('')
const notice = ref('')
const toolsTarget = ref<MiniUser | null>(null)
const toolsOpen = ref(false)
const toolsInitial = ref('renew')
function memberTool(item: MiniUser, mode: string) { toolsTarget.value = item; toolsInitial.value = mode; toolsOpen.value = true }
const busy = ref(false)
const dialog = ref(false)
const target = ref<MiniUser | null>(null)
const username = ref('')
const password = ref('')
const level = ref<'regular' | 'vip'>('regular')
const active = ref(true)
const lifetime = ref(false)
const expires = ref('')
const formError = ref('')
/** 编辑资料弹层用：昵称与头像键（空串 = 恢复默认形象） */
const profileName = ref('')
const profileAvatarKey = ref('')
/** 删除是不可恢复的操作，要求先勾选确认 */
const deleteConfirmed = ref(false)
let sequence = 0
const levels = [{ label: '普通用户', value: 'regular' }, { label: 'VIP 会员', value: 'vip' }]
const filters = [{ label: '全部用户', value: 'all' }, ...levels, { label: '7 天内到期', value: 'expiring' }, { label: '已到期', value: 'expired' }]

type Action = 'create' | 'profile' | 'password' | 'membership' | 'delete'
const action = ref<Action>('create')
const title = computed(() => ({
  create: '创建小程序账号', profile: '编辑用户资料',
  password: target.value?.has_password ? '重置登录密码' : '设置登录密码',
  membership: '管理会员与账号', delete: '删除小程序账号',
})[action.value])
const submitLabel = computed(() => ({
  create: '创建普通账号', profile: '保存资料',
  password: target.value?.has_password ? '重置密码' : '设置密码',
  membership: '保存更改', delete: '确认删除',
})[action.value])
/** 昵称或头像真的改了才允许提交，避免后端回「没有需要更新的内容」 */
const profileDirty = computed(() => !!target.value
  && (profileName.value.trim() !== (target.value.nickname || target.value.username) || profileAvatarKey.value !== target.value.avatar))
const initial = computed(() => (Array.from(profileName.value.trim())[0] || '?').toUpperCase())
const valid = computed(() => {
  if (action.value === 'create') return !registrationAccountError(username.value) && password.value.length >= 6
  if (action.value === 'profile') return !nicknameError(profileName.value) && profileDirty.value
  if (action.value === 'password') return password.value.length >= 6
  if (action.value === 'delete') return deleteConfirmed.value
  return !!target.value && (level.value === 'regular' || lifetime.value || Number.isFinite(Date.parse(expires.value)))
})
const message = (cause: unknown) => cause instanceof Error ? cause.message : '操作失败，请重试'
const date = (stamp: number) => new Date(stamp * 1000).toLocaleString('zh-CN', { hour12: false })
function localInput(stamp: number) {
  const value = new Date(stamp * 1000)
  return new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
async function load() {
  const current = ++sequence
  loading.value = true; error.value = ''
  try {
    const result = await miniUsers(q.value.trim(), membership.value === 'all' ? '' : membership.value, (page.value - 1) * 20)
    if (current !== sequence) return
    items.value = result.items; total.value = result.total
    if (!items.value.length && page.value > 1) page.value--
  } catch (cause) { if (current === sequence) error.value = message(cause) }
  finally { if (current === sequence) loading.value = false }
}
function search() { if (routeState.restoring) return; if (page.value !== 1) page.value = 1; else void load() }
watch(page, load)
watch(membership, search)
onActivated(load)
onDeactivated(() => { sequence++; loading.value = false; dialog.value = false; password.value = '' })

function show(next: Action, item: MiniUser | null = null) {
  action.value = next
  target.value = item
  username.value = ''; password.value = ''; formError.value = ''; deleteConfirmed.value = false
  if (item) {
    level.value = item.membership; active.value = item.is_active
    lifetime.value = item.membership === 'vip' && item.vip_expires_at === null
    expires.value = localInput(item.vip_expires_at || Math.floor(Date.now() / 1000) + 30 * 86400)
    profileName.value = item.nickname || item.username; profileAvatarKey.value = item.avatar
  } else {
    profileName.value = ''; profileAvatarKey.value = ''
  }
  dialog.value = true
}
function actions(item: MiniUser) {
  return [[
    { label: '编辑资料', icon: 'i-lucide-pencil', onSelect: () => show('profile', item) },
    { label: '重置密码', icon: 'i-lucide-key-round', onSelect: () => show('password', item) },
    { label: '快捷续期', icon: 'i-lucide-calendar-plus', onSelect: () => memberTool(item, 'renew') },
    { label: '操作记录', icon: 'i-lucide-history', onSelect: () => memberTool(item, 'history') },
    { label: '会员与账号状态', icon: 'i-lucide-user-cog', onSelect: () => show('membership', item) },
  ], [
    { label: '删除账号', icon: 'i-lucide-trash-2', color: 'error' as const, onSelect: () => show('delete', item) },
  ]]
}
async function save() {
  if (busy.value || !valid.value) return
  busy.value = true; formError.value = ''
  try {
    if (action.value === 'create') {
      await createMiniUser(props.user.id, username.value.trim(), password.value)
      notice.value = '小程序账号已创建'
    } else if (target.value) {
      const user = target.value
      if (action.value === 'membership') {
        await updateMembership(props.user.id, user.id, {
          revision: user.revision, membership: level.value, is_active: active.value,
          vip_expires_at: level.value === 'regular' || lifetime.value ? null : Math.floor(Date.parse(expires.value) / 1000),
        })
        notice.value = '会员与账号状态已更新'
      } else if (action.value === 'profile') {
        const patch: MiniProfileEdit = { revision: user.revision }
        const nextName = profileName.value.trim()
        if (nextName !== (user.nickname || user.username)) patch.nickname = nextName
        if (profileAvatarKey.value !== user.avatar) patch.avatar = profileAvatarKey.value
        await updateMiniProfile(props.user.id, user.id, patch)
        notice.value = `已更新「${nextName}」的昵称与头像`
      } else if (action.value === 'password') {
        await updateMiniProfile(props.user.id, user.id, { revision: user.revision, new_password: password.value })
        notice.value = `已重置「${user.username}」的密码，该用户需重新登录`
      } else {
        const removed = await deleteMiniUser(props.user.id, user.id)
        const cleaned = (removed.removed?.mini_user_sessions || 0) + (removed.removed?.mini_catalog_favorites || 0)
          + (removed.removed?.mini_catalog_downloads || 0)
        notice.value = `已删除账号「${removed.username}」${cleaned ? `，同时清理 ${cleaned} 条关联数据` : ''}`
      }
    }
    password.value = ''; dialog.value = false; await load()
  } catch (cause) { formError.value = message(cause) }
  finally { busy.value = false }
}
watch(dialog, open => { if (!open) deleteConfirmed.value = false })
const routeState = useAdminListRoute('miniUsers', { q, membership, page }, () => { void load() })
</script>

<template>
  <section class="admin-section" aria-label="小程序用户管理">
    <div class="section-toolbar mini-toolbar"><form class="table-search" @submit.prevent="search"><UInput v-model="q" icon="i-lucide-search" placeholder="搜索小程序账号" aria-label="搜索小程序账号" /><UButton type="submit" icon="i-lucide-arrow-right" aria-label="搜索用户" variant="outline" color="neutral" :loading="loading" /></form><div class="actions-row"><USelect v-model="membership" :items="filters" aria-label="会员筛选" /><UTooltip text="刷新"><UButton icon="i-lucide-refresh-cw" aria-label="刷新小程序用户" color="neutral" variant="ghost" :loading="loading" @click="load" /></UTooltip><UButton icon="i-lucide-user-plus" label="创建账号" @click="show('create')" /></div></div>
    <UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" />
    <UAlert v-if="notice" :title="notice" color="success" variant="soft" close class="notice" @update:open="notice = ''" />
    <div class="data-scroll" :aria-busy="loading"><table class="data-table mini-users-table"><thead><tr><th>小程序账号</th><th>登录方式</th><th>会员身份</th><th>会员有效期</th><th>账号状态</th><th>注册时间</th><th><span class="sr-only">操作</span></th></tr></thead><tbody>
      <tr v-for="item in items" :key="item.id"><td class="mini-username"><span class="mini-avatar"><img v-if="item.avatar_url" :src="item.avatar_url" alt="头像" class="avatar-photo" /><span v-else-if="avatarGlyph(item.avatar)" class="mini-avatar-glyph">{{ avatarGlyph(item.avatar) }}</span><span v-else>{{ (item.username || '?').slice(0, 1).toUpperCase() }}</span></span><span>{{ item.nickname || item.username }}<small class="block text-muted">账号：{{ item.username }}</small></span></td><td>{{ item.login_method === 'wechat' ? '微信' : '账号密码' }}</td><td><UBadge :color="item.is_vip ? 'success' : 'neutral'" variant="soft">{{ item.is_vip ? 'VIP 会员' : '普通用户' }}</UBadge></td><td><span :class="{ 'text-warning': item.membership_status === 'expired' }">{{ item.membership === 'regular' ? '未开通' : item.vip_expires_at ? date(item.vip_expires_at) : '长期有效' }}</span><span v-if="item.membership_status === 'expired'" class="expiry-tag">已到期</span></td><td><UBadge :color="item.is_active ? 'neutral' : 'error'" variant="soft">{{ item.is_active ? '正常' : '已禁用' }}</UBadge></td><td class="date-cell">{{ date(item.created_at) }}</td><td><UDropdownMenu :items="actions(item)"><UButton icon="i-lucide-ellipsis" color="neutral" variant="ghost" size="sm" :aria-label="item.username + ' 的账号操作'" /></UDropdownMenu></td></tr>
      <tr v-if="!items.length"><td colspan="7"><div class="empty-state"><UIcon :name="loading ? 'i-lucide-loader-circle' : 'i-lucide-users-round'" class="size-7" :class="{ 'animate-spin': loading }" /><h3>{{ loading ? '正在加载' : error ? '用户列表暂不可用' : '暂无小程序用户' }}</h3></div></td></tr>
    </tbody></table></div>
    <div class="table-footer"><span>共 {{ total }} 位小程序用户</span><UPagination v-if="total > 20" v-model:page="page" :total="total" :items-per-page="20" :sibling-count="1" size="sm" /></div>
    <UModal v-model:open="dialog" :title="title" :dismissible="!busy" :close="!busy"><template #body><form id="mini-user-form" class="field-stack" @submit.prevent="save">
      <template v-if="action === 'create'"><UFormField label="登录账号" hint="2-32 位英文字母、数字、下划线或短横线，不能使用中文" required><UInput v-model="username" minlength="2" maxlength="32" autocomplete="off" :disabled="busy" required class="w-full" /></UFormField><UFormField label="初始密码" required><UInput v-model="password" type="password" minlength="6" maxlength="128" autocomplete="new-password" :disabled="busy" required class="w-full" /></UFormField></template>

      <template v-else-if="target">
        <div class="member-account"><span class="mini-avatar"><img v-if="target.avatar_url" :src="target.avatar_url" alt="头像" class="avatar-photo" /><span v-else-if="avatarGlyph(target.avatar)" class="mini-avatar-glyph">{{ avatarGlyph(target.avatar) }}</span><span v-else>{{ (target.username || '?').slice(0, 1).toUpperCase() }}</span></span><strong>{{ target.username }}</strong><UBadge size="xs" color="neutral" variant="soft">{{ target.has_password ? '可账号密码登录' : '仅微信登录' }}</UBadge></div>

        <template v-if="action === 'profile'">
          <UFormField label="头像"><div class="avatar-grid">
            <button v-for="choice in AVATAR_CHOICES" :key="choice.key" type="button" class="avatar-option" :class="{ 'avatar-option-active': profileAvatarKey === choice.key }" :title="choice.label" :aria-label="choice.label" :aria-pressed="profileAvatarKey === choice.key" :disabled="busy" @click="profileAvatarKey = choice.key">{{ choice.glyph }}</button>
          </div></UFormField>
          <p class="avatar-hint"><span class="avatar-preview"><img v-if="profileAvatarKey === target.avatar && target.avatar_url" :src="target.avatar_url" alt="头像" class="avatar-photo" /><span v-else-if="avatarGlyph(profileAvatarKey)">{{ avatarGlyph(profileAvatarKey) }}</span><span v-else>{{ initial }}</span></span>当前：{{ profileAvatarKey ? (AVATAR_CHOICES.find(c => c.key === profileAvatarKey)?.label || '用户自选头像') : '未选择，小程序里显示昵称首字' }}<UButton v-if="profileAvatarKey" label="恢复默认" icon="i-lucide-rotate-ccw" color="neutral" variant="link" size="xs" :disabled="busy" @click="profileAvatarKey = ''" /></p>
          <UFormField label="展示昵称" required><UInput v-model="profileName" minlength="1" maxlength="64" :disabled="busy" required class="w-full" /><template #hint>1 至 32 个字符，支持微信昵称和表情。登录账号 {{ target.username }} 保持不变，昵称可以重复。</template></UFormField>
          <UAlert v-if="!profileDirty" color="info" variant="soft" title="昵称和头像都没改动，换一个再保存。" />
        </template>

        <template v-else-if="action === 'password'"><UFormField label="新密码" required><UInput v-model="password" type="password" minlength="6" maxlength="128" autocomplete="new-password" placeholder="至少 6 位" :disabled="busy" required class="w-full" /></UFormField><UAlert :color="target.has_password ? 'warning' : 'info'" variant="soft" :title="target.has_password ? '重置后该账号的全部登录会话立即失效，用户需用新密码重新登录。' : '该账号目前只能用微信登录，设置密码后即可用固定登录账号和密码在 H5 登录。'" /></template>

        <template v-else-if="action === 'membership'"><UFormField label="会员身份"><USelect v-model="level" :items="levels" :disabled="busy" class="w-full" /></UFormField><template v-if="level === 'vip'"><USwitch v-model="lifetime" label="长期有效" :disabled="busy" /><UFormField v-if="!lifetime" label="会员到期时间" required><UInput v-model="expires" type="datetime-local" :disabled="busy" required class="w-full" /></UFormField></template><USwitch v-model="active" label="账号启用" :disabled="busy" /><UAlert v-if="!active" title="禁用后，该用户的全部小程序会话将失效。" color="warning" variant="soft" /></template>

        <template v-else>
          <UAlert color="error" variant="soft" icon="i-lucide-triangle-alert" :title="'确认删除「' + target.username + '」？此操作不可恢复。'" description="该账号的登录态、收藏与下载记录会一并删除。如果只是想临时停用，请改用「会员与账号状态」里的「账号启用」开关。" />
          <UCheckbox v-model="deleteConfirmed" label="我已确认，删除后无法找回该账号" :disabled="busy" />
        </template>
      </template>

      <UAlert v-if="formError" :title="formError" color="error" variant="soft" />
    </form></template><template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="dialog = false" /><UButton type="submit" form="mini-user-form" :label="submitLabel" :color="action === 'delete' ? 'error' : 'primary'" icon="i-lucide-check" :loading="busy" :disabled="busy || !valid" /></template></UModal>
    <MemberTools :open="toolsOpen" :target="toolsTarget" :admin-id="user.id" :initial="toolsInitial" @close="toolsOpen = false" @saved="load" />
  </section>
</template>

<style scoped>
.mini-toolbar { flex-wrap: wrap; gap: 12px; }
.mini-users-table { min-width: 940px; }
.mini-username { font-weight: 600; max-width: 220px; overflow-wrap: anywhere; white-space: normal; }
.mini-avatar { display: inline-flex; align-items: center; justify-content: center; flex: none; width: 24px; height: 24px; margin-right: 8px; border: 1px solid var(--ui-border); border-radius: 50%; background: var(--ui-bg-muted); font-size: 13px; font-weight: 600; vertical-align: middle; }
.avatar-photo { width:100%;height:100%;object-fit:cover;border-radius:50%; }
.mini-avatar-glyph { font-size: 14px; line-height: 1; }
.expiry-tag { display: block; font-size: 11px; color: var(--ui-warning); margin-top: 4px; }
.member-account { display: flex; align-items: center; gap: 9px; overflow-wrap: anywhere; }
.avatar-grid { display: grid; grid-template-columns: repeat(8, minmax(0, 1fr)); gap: 8px; }
.avatar-option { display: inline-flex; align-items: center; justify-content: center; height: 38px; border: 1px solid var(--ui-border); border-radius: 10px; background: var(--ui-bg); font-size: 19px; line-height: 1; cursor: pointer; transition: border-color .15s, background .15s, transform .15s; }
.avatar-option:hover { transform: translateY(-1px); border-color: var(--ui-primary); }
.avatar-option-active { border-color: var(--ui-primary); background: var(--ui-bg-muted); box-shadow: 0 0 0 2px color-mix(in srgb, var(--ui-primary) 30%, transparent); }
.avatar-hint { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 12px; color: var(--ui-text-muted); }
.avatar-preview { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border: 1px solid var(--ui-border); border-radius: 50%; background: var(--ui-bg-muted); font-size: 14px; font-weight: 600; }
</style>
