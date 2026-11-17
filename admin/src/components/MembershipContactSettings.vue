<script setup lang="ts">
import { canPermission } from '../permissions'
import { computed, onActivated, onBeforeUnmount, onDeactivated, ref } from 'vue'
import { ApiError, type UserInfo } from '../api'
import { getSupport, saveSupport, type SupportSettings } from '../experience'
import { useAdminLeaveGuard } from '../navigation'
import { useBeforeUnload } from '../unsaved'

const props = defineProps<{ user: UserInfo }>()
const settings = ref<SupportSettings | null>(null)
const baseline = ref<SupportSettings | null>(null)
const active = ref(false), loading = ref(false), busy = ref(false), conflict = ref(false)
const error = ref(''), notice = ref('')
const dirty = computed(() => JSON.stringify(settings.value) !== JSON.stringify(baseline.value))
const fields = ['benefits', 'wechat', 'phone', 'email', 'qr_url', 'hours'] as const
let sequence = 0
useBeforeUnload(computed(() => active.value && dirty.value))
useAdminLeaveGuard(() => !active.value || (!busy.value && (!dirty.value || window.confirm('有未保存的会员与联系设置，确认离开？'))))

function update(field: typeof fields[number], value: string | number | undefined) {
  if (settings.value) settings.value[field] = String(value ?? '')
}
async function load() {
  const current = ++sequence
  loading.value = true; error.value = ''
  try {
    const latest = await getSupport()
    if (!active.value || current !== sequence) return
    const next = { ...latest }
    // 冲突或切回页面后只保留修改过的字段，其他字段采用服务器最新值。
    const preserved = dirty.value
    for (const field of fields) {
      if (settings.value && baseline.value && settings.value[field] !== baseline.value[field]) next[field] = settings.value[field] ?? ''
    }
    settings.value = next; baseline.value = { ...latest }; conflict.value = false
    if (preserved) notice.value = '已载入最新版本，您的修改已保留，请核对后保存'
  } catch (cause) {
    if (active.value && current === sequence) error.value = cause instanceof Error ? cause.message : '服务信息加载失败，请重试'
  } finally {
    if (current === sequence) loading.value = false
  }
}
async function save() {
  if (busy.value || loading.value || !settings.value) return
  if (settings.value.phone && !/^[0-9+() -]{0,40}$/.test(settings.value.phone)) {
    error.value = '联系电话只能包含数字、空格和 + ( ) -，最多 40 位'; return
  }
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const saved = await saveSupport(props.user.id, { ...settings.value })
    settings.value = saved; baseline.value = { ...saved }; conflict.value = false
    notice.value = '会员权益和联系方式已更新'
  } catch (cause) {
    conflict.value = cause instanceof ApiError && cause.status === 409
    error.value = cause instanceof Error ? cause.message : '服务信息保存失败，请重试'
  } finally { busy.value = false }
}
onActivated(() => { active.value = true; void load() })
function deactivate() { active.value = false; sequence++; loading.value = false }
onDeactivated(deactivate)
onBeforeUnmount(deactivate)
</script>

<template>
  <section class="admin-section contact-settings">
    <UAlert v-if="error" :title="error" color="error" class="notice" />
    <UAlert v-if="notice" :title="notice" color="success" class="notice" />
    <UButton v-if="conflict" label="载入最新并保留我的修改" :loading="loading" :disabled="busy" class="mb-4" @click="load" />
    <p v-if="loading && !settings" role="status" class="text-sm text-muted">正在加载服务信息…</p>
    <UButton v-if="!settings && !loading" label="重新加载" variant="outline" @click="load" />
    <form v-if="settings" @submit.prevent="canPermission('membershipContact:update') && (save())">
      <fieldset class="field-stack" :disabled="busy || loading">
        <UFormField label="会员权益说明" hint="统一展示在小程序会员与客服页面。具体套餐的价格、天数和上架状态在“会员套餐”中管理。">
          <UTextarea :disabled="!canPermission('membershipContact:update')" :model-value="settings?.benefits" @update:model-value="update('benefits', $event)" :rows="5" :maxlength="2000" class="w-full" />
        </UFormField>
        <UFormField label="客服微信号"><UInput :disabled="!canPermission('membershipContact:update')" :model-value="settings?.wechat" @update:model-value="update('wechat', $event)" maxlength="80" class="w-full" /></UFormField>
        <UFormField label="联系电话"><UInput :disabled="!canPermission('membershipContact:update')" :model-value="settings?.phone" @update:model-value="update('phone', $event)" maxlength="40" class="w-full" /></UFormField>
        <UFormField label="联系邮箱"><UInput :disabled="!canPermission('membershipContact:update')" :model-value="settings?.email" @update:model-value="update('email', $event)" type="email" maxlength="120" class="w-full" /></UFormField>
        <UFormField label="客服二维码地址"><UInput :disabled="!canPermission('membershipContact:update')" :model-value="settings?.qr_url" @update:model-value="update('qr_url', $event)" maxlength="500" placeholder="https://... 或本地可访问地址" class="w-full" /></UFormField>
        <UFormField label="服务时间"><UInput :disabled="!canPermission('membershipContact:update')" :model-value="settings?.hours" @update:model-value="update('hours', $event)" maxlength="120" placeholder="例如：工作日 9:00–18:00" class="w-full" /></UFormField>
        <p class="text-sm text-muted">联系方式可以留空；配置二维码地址后，小程序会员与客服页面会展示二维码。</p>
        <UButton type="submit" label="保存服务信息" :loading="busy" :disabled="!dirty || loading" />
      </fieldset>
    </form>
  </section>
</template>

<style scoped>
.contact-settings { max-width:720px; }
.field-stack { min-width:0; }
</style>
