<script setup lang="ts">
import { useDialogDraft } from "../dialog-draft"
import { computed, ref, watch } from 'vue'
import { memberEvents, renewMember, type MemberEvent } from '../experience'
import type { MiniUser } from '../mini'
const props = defineProps<{ open: boolean; target: MiniUser | null; adminId: number; initial: string }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const tab = ref('renew')
const days = ref(30)
const note = ref('')
const events = ref<MemberEvent[]>([])
const more = ref(false)
const error = ref('')
const busy = ref(false)
const loading = ref(false)
let sequence = 0
const lifetime = computed(() => props.target?.membership === 'vip' && props.target.vip_expires_at === null)
const date = (stamp: unknown) => typeof stamp === 'number' ? new Date(stamp * 1000).toLocaleString() : '长期有效'
const message = (cause: unknown) => cause instanceof Error ? cause.message : '操作失败'
async function load(append = false) {
  if (!props.target || loading.value) return
  const current = ++sequence
  loading.value = true
  try { const data = await memberEvents(props.target.id, append ? events.value.length : 0); if (current === sequence) { events.value = append ? [...events.value, ...data.items] : data.items; more.value = data.has_more } }
  catch (cause) { if (current === sequence) error.value = message(cause) }
  finally { if (current === sequence) loading.value = false }
}
watch(() => props.open, value => { sequence++; loading.value = false; error.value = ''; events.value = []; note.value = ''; days.value = 30; tab.value = props.initial; draft.markSaved(); if (value) void load() })
async function save() {
  if (!props.target || busy.value || lifetime.value) return
  busy.value = true; error.value = ''
  try { await renewMember(props.adminId, props.target, Number(days.value), note.value); emit('saved'); emit('close') }
  catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}
function changes(item: MemberEvent) {
  const labels: Record<string, string> = { nickname: '昵称', avatar: '头像', membership: '会员身份', vip_expires_at: '会员到期', is_active: '账号状态', has_password: '密码设置' }
  const render = (key: string, snapshot: Record<string, unknown>) => {
    const value = snapshot[key]
    if (key === 'vip_expires_at') return snapshot.membership === 'vip' ? date(value) : '未开通'
    if (key === 'is_active') return value ? '启用' : '禁用'
    if (key === 'membership') return value === 'vip' ? 'VIP' : '普通用户'
    if (key === 'has_password') return value ? '已设置' : '未设置'
    return String(value ?? '—')
  }
  const details = Object.entries(labels).filter(([key]) => item.before[key] !== item.after[key])
    .map(([key, label]) => `${label}：${render(key, item.before)} → ${render(key, item.after)}`)
  if (item.after.password_reset) details.push('重置登录密码')
  return details.join('；') || '资料更新'
}
const draft = useDialogDraft(computed({ get: () => props.open, set: value => { if (!value) emit('close') } }), () => [days.value, note.value], busy, '续期备注')
</script>
<template>
  <UModal :open="open" :title="(target?.nickname || target?.username || '') + ' · 会员服务'" :dismissible="!busy" :close="!busy" @update:open="draft.setOpen($event)"><template #body><UTabs v-model="tab" :items="[{ label: '快捷续期', value: 'renew' }, { label: '操作记录', value: 'history' }]" :content="false" /><UAlert v-if="error" :title="error" color="error" class="my-3" /><form v-if="tab === 'renew' && target" id="renew-member" class="field-stack mt-5" @submit.prevent="save"><p>当前会员：{{ target.membership === 'vip' ? date(target.vip_expires_at) : '未开通' }}</p><UAlert v-if="lifetime" title="当前为长期会员，无需续期" color="info" /><UAlert v-if="!target.is_active" title="账号当前已禁用，续期不会自动解除禁用" color="warning" /><UFormField label="增加会员天数"><USelect v-model="days" :items="[{ label: '30 天', value: 30 }, { label: '90 天', value: 90 }, { label: '365 天', value: 365 }]" :disabled="lifetime || busy" /></UFormField><p class="text-sm text-muted">有效会员从原到期时间继续增加；已过期或普通用户从现在开始计算。</p><UFormField label="续期备注"><UTextarea v-model="note" :maxlength="300" class="w-full" placeholder="例如：线下续期已确认" /></UFormField></form><div v-else class="member-events"><p v-if="!events.length">{{ loading ? '正在加载' : '暂无后台操作记录' }}</p><article v-for="item in events" :key="item.id"><strong>{{ item.admin_name || '历史管理员' }} · {{ date(item.created_at) }}</strong><p>{{ changes(item) }}</p><p v-if="item.after.note">备注：{{ item.after.note }}</p></article><UButton v-if="more" label="加载更多" :loading="loading" @click="load(true)" /></div></template><template #footer><UButton label="关闭" color="neutral" variant="outline" :disabled="busy" @click="draft.setOpen(false)" /><UButton v-if="tab === 'renew'" type="submit" form="renew-member" label="确认续期" :disabled="lifetime" :loading="busy" /></template></UModal>
</template>
<style scoped>
.member-events { margin-top:20px; }.member-events article { padding:14px 0;border-bottom:1px solid var(--ui-border); }.member-events strong { font-size:12px; }.member-events p { margin-top:8px;font-size:13px;line-height:1.7;overflow-wrap:anywhere; }
</style>
