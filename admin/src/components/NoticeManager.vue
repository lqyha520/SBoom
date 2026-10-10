<script setup lang="ts">
import { useDialogDraft } from '../dialog-draft'
import { useRevisionConflict } from '../revision-conflict'
import { computed, onActivated, onDeactivated, ref } from 'vue'
import type { UserInfo } from '../api'
import { createNotice, deleteNotice, siteNotices, updateNotice, type Notice, type NoticeState } from '../site'

const props = defineProps<{ user: UserInfo }>()
const items = ref<Notice[]>([])
const loading = ref(false)
const error = ref('')
const notice = ref('')
const busy = ref(false)
const dialog = ref(false)
const target = ref<Notice | null>(null)
const formError = ref('')
const recovery = useRevisionConflict(target, async id => { const value = (await siteNotices()).items.find(item => item.id === id); if (!value) throw new Error('该条目已删除，请复制修改后新建'); return value }, formError)
const removing = ref<Notice | null>(null)
const removeOpen = ref(false)
let sequence = 0

const placementOptions = [
  { label: '启动弹窗（进小程序弹一次）', value: 'popup' },
  { label: '首页公告条（顶部常驻）', value: 'banner' },
]
const levelOptions = [{ label: '普通提示', value: 'info' }, { label: '重要提醒', value: 'warning' }]
const stateLabels: Record<NoticeState, string> = { active: '生效中', scheduled: '待生效', expired: '已过期', hidden: '已关闭' }
const stateColors: Record<NoticeState, 'success' | 'info' | 'neutral' | 'warning'> = { active: 'success', scheduled: 'info', expired: 'neutral', hidden: 'warning' }
const form = ref({
  title: '', body: '', placement: 'popup' as 'popup' | 'banner', level: 'info' as 'info' | 'warning',
  starts_at: '', ends_at: '', is_visible: true,
})
const message = (cause: unknown) => (cause instanceof Error ? cause.message : '操作失败，请重试')

function localInput(stamp: number) {
  const value = new Date(stamp * 1000)
  return new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
function stampOf(value: string) { return value ? Math.floor(Date.parse(value) / 1000) : 0 }
function windowText(item: Notice) {
  if (!item.starts_at && !item.ends_at) return '长期有效'
  const from = item.starts_at ? new Date(item.starts_at * 1000).toLocaleString('zh-CN', { hour12: false }) : '立即'
  const to = item.ends_at ? new Date(item.ends_at * 1000).toLocaleString('zh-CN', { hour12: false }) : '不限'
  return from + ' → ' + to
}
const windowValid = computed(() => {
  const start = stampOf(form.value.starts_at)
  const end = stampOf(form.value.ends_at)
  return !start || !end || end > start
})
const canSave = computed(() => !!form.value.title.trim() && windowValid.value)

async function load() {
  const current = ++sequence
  loading.value = true; error.value = ''
  try {
    const result = await siteNotices()
    if (current === sequence) items.value = result.items
  } catch (cause) { if (current === sequence) error.value = message(cause) }
  finally { if (current === sequence) loading.value = false }
}

function create() {
  target.value = null
  form.value = { title: '', body: '', placement: 'popup', level: 'info', starts_at: '', ends_at: '', is_visible: true }
  formError.value = ''; dialog.value = true
}
function edit(item: Notice) {
  target.value = item
  form.value = {
    title: item.title, body: item.body, placement: item.placement, level: item.level,
    starts_at: item.starts_at ? localInput(item.starts_at) : '', ends_at: item.ends_at ? localInput(item.ends_at) : '',
    is_visible: item.is_visible,
  }
  formError.value = ''; dialog.value = true
}
function payload() {
  return {
    title: form.value.title.trim(), body: form.value.body, placement: form.value.placement, level: form.value.level,
    starts_at: stampOf(form.value.starts_at), ends_at: stampOf(form.value.ends_at), is_visible: form.value.is_visible,
  }
}
async function save() {
  if (busy.value || !canSave.value) return
  busy.value = true; formError.value = ''
  try {
    if (target.value) await updateNotice(props.user.id, target.value.id, { revision: target.value.revision, ...payload() })
    else await createNotice(props.user.id, payload())
    notice.value = target.value ? '公告已更新' : '公告已创建'
    dialog.value = false; await load()
  } catch (cause) { recovery.capture(cause); formError.value = message(cause) }
  finally { busy.value = false }
}
async function toggleVisible(item: Notice) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    await updateNotice(props.user.id, item.id, {
      revision: item.revision, title: item.title, body: item.body, placement: item.placement, level: item.level,
      starts_at: item.starts_at, ends_at: item.ends_at, is_visible: !item.is_visible,
    })
    await load()
  } catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}
function askRemove(item: Notice) { removing.value = item; removeOpen.value = true }
async function confirmRemove() {
  if (!removing.value || busy.value) return
  busy.value = true
  try {
    await deleteNotice(props.user.id, removing.value.id, removing.value.revision)
    removeOpen.value = false; notice.value = '公告已删除'; await load()
  } catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}

onActivated(load)
onDeactivated(() => { sequence++; loading.value = false; dialog.value = false; removeOpen.value = false })
const draft = useDialogDraft(dialog, () => form.value, busy, '公告')
</script>

<template>
  <section class="admin-section" aria-label="公告与弹窗管理">
    <div class="section-toolbar">
      <p class="section-hint">「启动弹窗」在用户打开小程序时弹一次；「首页公告条」常驻在首页顶部。留空时间即长期有效。</p>
      <div class="actions-row"><UTooltip text="刷新"><UButton icon="i-lucide-refresh-cw" color="neutral" variant="ghost" aria-label="刷新公告" :loading="loading" @click="load" /></UTooltip><UButton icon="i-lucide-plus" label="新建公告" @click="create" /></div>
    </div>
    <UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" />
    <UAlert v-if="notice" :title="notice" color="success" variant="soft" close class="notice" @update:open="notice = ''" />
    <div class="data-scroll" :aria-busy="loading"><table class="data-table notice-table"><thead><tr><th>标题</th><th>展示位置</th><th>级别</th><th>生效时间</th><th>状态</th><th><span class="sr-only">操作</span></th></tr></thead><tbody>
      <tr v-for="item in items" :key="item.id">
        <td class="name-cell"><strong>{{ item.title }}</strong><div v-if="item.body" class="notice-body">{{ item.body }}</div></td>
        <td>{{ item.placement === 'popup' ? '启动弹窗' : '首页公告条' }}</td>
        <td><UBadge :color="item.level === 'warning' ? 'warning' : 'neutral'" variant="soft">{{ item.level === 'warning' ? '重要' : '普通' }}</UBadge></td>
        <td class="date-cell">{{ windowText(item) }}</td>
        <td><UBadge :color="stateColors[item.state]" variant="soft">{{ stateLabels[item.state] }}</UBadge></td>
        <td><div class="row-actions"><UTooltip text="编辑"><UButton icon="i-lucide-pencil" color="neutral" variant="ghost" :aria-label="'编辑 ' + item.title" @click="edit(item)" /></UTooltip><UTooltip :text="item.is_visible ? '关闭' : '启用'"><UButton :icon="item.is_visible ? 'i-lucide-eye-off' : 'i-lucide-eye'" color="neutral" variant="ghost" :aria-label="(item.is_visible ? '关闭 ' : '启用 ') + item.title" @click="toggleVisible(item)" /></UTooltip><UTooltip text="删除"><UButton icon="i-lucide-trash-2" color="error" variant="ghost" :aria-label="'删除 ' + item.title" @click="askRemove(item)" /></UTooltip></div></td>
      </tr>
      <tr v-if="!items.length"><td colspan="6"><div class="empty-state"><UIcon :name="loading ? 'i-lucide-loader-circle' : 'i-lucide-megaphone'" class="size-7" :class="{ 'animate-spin': loading }" /><h3>{{ loading ? '正在加载' : '还没有公告' }}</h3></div></td></tr>
    </tbody></table></div>
    <div class="table-footer"><span>共 {{ items.length }} 条公告</span></div>

    <UModal v-model:open="draft.model.value" :title="target ? '编辑公告' : '新建公告'" :dismissible="!busy" :close="!busy"><template #body><form id="notice-form" class="field-stack" @submit.prevent="save">
      <UFormField label="标题" required><UInput v-model="form.title" maxlength="60" :disabled="busy" required class="w-full" /></UFormField>
      <UFormField label="正文" hint="换行会原样保留，弹窗内可滚动查看"><UTextarea v-model="form.body" :rows="5" maxlength="2000" :disabled="busy" class="w-full" /></UFormField>
      <div class="grid-two"><UFormField label="展示位置"><USelect v-model="form.placement" :items="placementOptions" :disabled="busy" class="w-full" /></UFormField><UFormField label="级别"><USelect v-model="form.level" :items="levelOptions" :disabled="busy" class="w-full" /></UFormField></div>
      <div class="grid-two"><UFormField label="开始时间" hint="留空立即生效"><UInput v-model="form.starts_at" type="datetime-local" :disabled="busy" class="w-full" /></UFormField><UFormField label="结束时间" hint="留空长期有效"><UInput v-model="form.ends_at" type="datetime-local" :disabled="busy" class="w-full" /></UFormField></div>
      <UAlert v-if="!windowValid" title="结束时间必须晚于开始时间。" color="warning" variant="soft" />
      <USwitch v-model="form.is_visible" label="启用该公告" :disabled="busy" />
      <UButton v-if="recovery.conflict.value" label="载入最新并保留我的修改" :loading="recovery.recovering.value" @click="recovery.reload" /><UAlert v-if="formError" :title="formError" color="error" variant="soft" />
    </form></template><template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="draft.setOpen(false)" /><UButton type="submit" form="notice-form" :label="target ? '保存' : '创建'" icon="i-lucide-check" :loading="busy" :disabled="busy || !canSave" /></template></UModal>

    <UModal v-model:open="removeOpen" title="删除公告" :dismissible="!busy" :close="!busy"><template #body><div class="field-stack"><p>确认删除「{{ removing?.title }}」？</p></div></template><template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="removeOpen = false" /><UButton label="确认删除" color="error" icon="i-lucide-trash-2" :loading="busy" :disabled="busy" @click="confirmRemove" /></template></UModal>
  </section>
</template>

<style scoped>
.section-hint { margin: 0; max-width: 640px; color: var(--ui-text-muted); font-size: 12px; line-height: 1.7; }
.notice-table { min-width: 880px; }
.notice-body { margin-top: 5px; color: var(--ui-text-muted); font-size: 11px; max-width: 420px; white-space: normal; overflow-wrap: anywhere; }
.row-actions { display: flex; gap: 2px; }
.grid-two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
@media (max-width: 767px) { .grid-two { grid-template-columns: minmax(0, 1fr); } }
</style>
