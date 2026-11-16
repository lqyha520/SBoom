<script setup lang="ts">
import { permissionDirective as vPermission } from '../permissions'
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref } from 'vue'
import type { UserInfo } from '../api'
import XhsDraftRecovery from './XhsDraftRecovery.vue'
import { useXhsDraftBackup } from '../xhs-draft-backup'
import { randomId } from '../../../shared/webcrypto'
import { adminRoute, useAdminLeaveGuard } from '../navigation'
import { emptyAccountProfile, addXhsAccount, closeXhsAccount, listXhsAccounts, openXhsAccount, updateXhsAccount, type XhsAccount } from '../xhs-accounts'
import { workflowError } from '../xhs-workflow'

const props = defineProps<{ user?: Pick<UserInfo, 'id'> }>()
const items = ref<XhsAccount[]>([]), loading = ref(false), busyId = ref(''), saving = ref(false), error = ref(''), notice = ref('')
const profile = ref(emptyAccountProfile()), profileSupport = ref(false)
const q = ref(''), archived = ref(false), editing = ref(false), selected = ref<XhsAccount | null>(null)
const name = ref(''), note = ref(''), requestId = ref(''), baseline = ref('')
let active = true, timer: ReturnType<typeof setTimeout> | undefined, sequence = 0
const filtered = computed(() => items.value.filter(item => item.archived === archived.value && `${item.name} ${item.note}`.toLocaleLowerCase().includes(q.value.trim().toLocaleLowerCase())))
const dirty = computed(() => editing.value && JSON.stringify([name.value, note.value, profile.value]) !== baseline.value)
const backup = useXhsDraftBackup({ adminId: props.user?.id || 0, scope: () => `accounts:${selected.value?.id || 'new'}`, enabled: () => !!props.user && editing.value,
  dirty: () => dirty.value, snapshot: () => ({ name: name.value, note: note.value, profile: profile.value, requestId: requestId.value }), revision: () => String(selected.value?.revision || 0),
  restore: value => { name.value = value.name; note.value = value.note; profile.value = value.profile; if (!selected.value) requestId.value = value.requestId } })
useAdminLeaveGuard(() => { backup.persist(); return adminRoute.tab !== 'xhsAccounts' || !dirty.value || window.confirm('账号资料尚未保存，确定离开？本机备份可在再次编辑时取回。') })
function stop() { if (timer) clearTimeout(timer); timer = undefined }
async function load(quiet = false) {
  const current = ++sequence
  if (!quiet) loading.value = true
  try { const result = await listXhsAccounts(); if (active && current === sequence) { items.value = result.items; profileSupport.value = result.profile_support === true; error.value = '' } }
  catch (cause) { if (active && current === sequence) error.value = workflowError(cause) }
  finally { if (current === sequence) { loading.value = false; stop(); if (active) timer = setTimeout(() => { void load(true) }, 5000) } }
}
function edit(item: XhsAccount | null) {
  selected.value = item ? { ...item } : null; name.value = item?.name || ''; note.value = item?.note || ''
  profile.value = { ...emptyAccountProfile(), ...item?.profile }
  requestId.value = randomId(); baseline.value = JSON.stringify([name.value, note.value, profile.value]); editing.value = true; error.value = ''; notice.value = ''
}
function cancel() { if (!saving.value && (!dirty.value || window.confirm('确定放弃尚未保存的账号资料？'))) editing.value = false }
async function save() {
  if (saving.value || !name.value.trim()) return
  saving.value = true; error.value = ''; stop(); ++sequence
  try {
    if (selected.value) await updateXhsAccount({ account_id: selected.value.id, revision: selected.value.revision, name: name.value, note: note.value, archived: selected.value.archived, ...(profileSupport.value ? { profile: profile.value } : {}) })
    else await addXhsAccount({ name: name.value, note: note.value, request_id: requestId.value, ...(profileSupport.value ? { profile: profile.value } : {}) })
    backup.clear(); editing.value = false; notice.value = selected.value ? '账号资料已保存，原登录状态保持不变。' : '账号已创建，点击“打开浏览器”完成首次登录。'
    await load()
  } catch (cause) { error.value = workflowError(cause) }
  finally { saving.value = false }
}
async function action(item: XhsAccount, kind: 'open' | 'close' | 'archive') {
  if (busyId.value || item.busy) return
  if (kind === 'close' && !window.confirm(`关闭“${item.name}”的全部浏览器窗口？请先保存尚未完成的编辑。登录状态会保留。`)) return
  busyId.value = item.id; error.value = ''; notice.value = ''; stop(); ++sequence
  try {
    if (kind === 'open') { await openXhsAccount(item.id); notice.value = `已打开“${item.name}”的浏览器，请在窗口核对实际登录账号。` }
    else if (kind === 'close') { await closeXhsAccount(item.id); notice.value = '浏览器已关闭，登录状态已保留。' }
    else { await updateXhsAccount({ account_id: item.id, revision: item.revision, name: item.name, note: item.note, archived: !item.archived }); notice.value = item.archived ? '账号已恢复。' : '账号已归档，登录状态与浏览器数据已保留。' }
    await load()
  } catch (cause) { error.value = workflowError(cause) }
  finally { busyId.value = '' }
}
onMounted(() => { void load() })
onActivated(() => { if (!active) { active = true; void load() } })
onDeactivated(() => { active = false; stop(); ++sequence })
onBeforeUnmount(() => { active = false; stop(); ++sequence })
</script>

<template>
  <section class="xhs-accounts" aria-label="小红书账号管理">
    <div class="accounts-intro"><UIcon name="i-lucide-contact-round" class="size-6" /><div><h2>一账号，一浏览器</h2><p>新增账号后点击“打开浏览器”，在弹出的窗口手动登录。不同账号可同时打开，登录状态、网站存储和缓存分别保存。</p><p>名称和备注用于本机区分；“窗口已打开”不代表已登录，请以小红书页面为准。账号列表按本机与当前后台访问地址保存。</p></div></div>
    <div class="accounts-toolbar">
      <UInput v-model="q" aria-label="搜索小红书账号" placeholder="搜索账号名称或备注" icon="i-lucide-search" />
      <UCheckbox v-model="archived" label="查看已归档账号" />
      <UButton label="刷新状态" variant="outline" :loading="loading" @click="load()" />
      <UButton v-permission="'xhsAccounts:create'" label="新增小红书账号" icon="i-lucide-plus" @click="edit(null)" />
    </div>
    <UAlert v-if="error" :title="error" color="error" class="mb-4" /><UAlert v-if="notice" :title="notice" color="success" class="mb-4" />
    <p v-if="!loading && !filtered.length" class="accounts-empty">{{ items.length ? '没有匹配的账号。可以调整搜索或切换归档列表。' : '还没有账号，点击“新增小红书账号”开始。需要本机服务运行，首次登录由你在浏览器完成。' }}</p>
    <div class="accounts-grid">
      <article v-for="item in filtered" :key="item.id" class="account-card" :aria-label="'账号 '+item.name">
        <div class="account-title"><span class="account-avatar">{{ item.name.slice(0,1) }}</span><div><h3>{{ item.name }}</h3><span class="account-status">{{ item.busy ? '正在操作，请稍候' : item.browser_open ? '窗口已打开' : '窗口未打开' }}</span></div></div>
        <p v-if="item.profile?.audience || item.profile?.direction" class="account-note"><strong>定位：</strong>{{ item.profile.audience }} · {{ item.profile.direction }}</p>
        <p class="account-note">{{ item.note || '暂无备注' }}</p>
        <div class="account-actions">
          <UButton v-permission="'xhsAccounts:run'" v-if="!item.archived" :label="item.browser_open ? '唤起浏览器' : '打开浏览器'" :disabled="!!busyId || item.busy" :loading="busyId===item.id" @click="action(item,'open')" />
          <UButton v-permission="'xhsAccounts:run'" v-if="item.browser_open" label="关闭浏览器" variant="outline" :disabled="!!busyId || item.busy" @click="action(item,'close')" />
          <UButton v-permission="'xhsAccounts:update'" label="编辑资料" variant="ghost" :disabled="!!busyId" @click="edit(item)" />
          <UButton v-permission="'xhsAccounts:update'" :label="item.archived?'恢复账号':'归档账号'" variant="ghost" :disabled="!!busyId || item.browser_open || item.busy" @click="action(item,'archive')" />
        </div>
      </article>
    </div>
    <UModal :open="editing" :title="selected?'编辑账号资料':'新增小红书账号'" @update:open="value=>{if(!value)cancel()}">
      <template #body><XhsDraftRecovery :backup="backup" /><div class="account-editor" :inert="saving || !!backup.recovery.value">
        <label><span>账号名称</span><UInput v-model="name" aria-label="小红书账号名称" maxlength="60" placeholder="例如：数学资料号、日常分享号" :disabled="saving" /></label>
        <label><span>备注</span><UTextarea v-model="note" aria-label="小红书账号备注" maxlength="500" :rows="3" placeholder="记录用途，方便区分。不要填写密码或验证码。" :disabled="saving" /></label>
        <fieldset v-if="profileSupport" class="account-editor" :disabled="saving"><legend>账号定位档案</legend>
          <label><span>目标人群</span><UInput v-model="profile.audience" aria-label="账号目标人群" maxlength="200" placeholder="例如：陪伴小学低年级孩子学习的家长" /></label>
          <label><span>内容方向</span><UTextarea v-model="profile.direction" aria-label="账号内容方向" maxlength="1000" :rows="3" placeholder="例如：分层数学练习、错题讲解、亲子学习方法" /></label>
          <label><span>文案风格</span><UTextarea v-model="profile.style" aria-label="账号文案风格" maxlength="1000" :rows="3" placeholder="例如：简洁温和，用具体例子，避免夸大效果" /></label>
          <label><span>常用话题</span><UInput v-model="profile.topics" aria-label="账号常用话题" maxlength="300" placeholder="#小学数学 #学习方法" /></label>
          <p>在笔记制作中选择此账号，可将这些定位带入文案生成。档案保存在本机，选用时随笔记保存一份快照。</p>
        </fieldset><p v-else>本机服务更新到版本 6 后，可以编辑账号定位档案。</p>
        <p>每个新增账号会使用全新的浏览器登录环境。归档与改名保留原登录状态。</p>
        <UAlert v-if="error" :title="error" color="error" />
      </div></template>
      <template #footer><UButton label="取消" variant="outline" :disabled="saving" @click="cancel" /><UButton v-permission="'xhsAccounts:' + (selected ? 'update' : 'create')" label="保存账号" :disabled="!name.trim() || !!backup.recovery.value" :loading="saving" @click="save" /></template>
    </UModal>
  </section>
</template>

<style scoped>
.accounts-intro { display:flex;gap:16px;padding:22px;border:1px solid var(--ui-border);border-radius:16px;background:var(--ui-bg); }
.accounts-intro h2 { font-size:18px;font-weight:700;margin-bottom:8px; }
.accounts-intro p,.account-editor p { color:var(--ui-text-muted);font-size:13px;line-height:1.8; }
.accounts-toolbar,.account-actions { display:flex;align-items:center;gap:12px;flex-wrap:wrap; }
.accounts-toolbar { margin:24px 0; }
.accounts-grid { display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr));gap:20px; }
.account-card { padding:22px;border:1px solid var(--ui-border);border-radius:16px;background:var(--ui-bg);min-width:0; }
.account-title { display:flex;align-items:center;gap:12px; }
.account-title h3 { font-weight:700;overflow-wrap:anywhere; }
.account-avatar { flex-shrink:0;display:grid;place-items:center;width:44px;height:44px;border-radius:12px;background:var(--ui-bg-accented);color:var(--ui-primary);font-size:22px; }
.account-status,.account-note,.accounts-empty { color:var(--ui-text-muted);font-size:13px; }
.account-note { margin:18px 0;min-height:24px;white-space:pre-wrap;overflow-wrap:anywhere; }
.accounts-empty { padding:32px 0; }
.account-editor { display:grid;gap:18px; }
.account-editor label { display:grid;gap:8px; }
</style>
