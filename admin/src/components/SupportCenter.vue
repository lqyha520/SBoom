<script setup lang="ts">
import { onActivated, onDeactivated, ref, watch } from 'vue'
import type { UserInfo } from '../api'
import { getSupport, saveSupport, getFeedback, saveFeedback, statusOptions, kindLabels, type Feedback, type SupportSettings } from '../experience'
import { catalogDetail, type CatalogDetail } from '../catalog'
const props = defineProps<{ user: UserInfo }>()
const tab = ref('feedback')
const status = ref('pending')
const page = ref(1)
const total = ref(0)
const items = ref<Feedback[]>([])
const settings = ref<SupportSettings | null>(null)
const selected = ref<Feedback | null>(null)
const dialog = ref(false)
const preview = ref<CatalogDetail | null>(null)
const previewOpen = ref(false)
const busy = ref(false)
const loading = ref(false)
const error = ref('')
const formError = ref('')
const notice = ref('')
let sequence = 0
const message = (cause: unknown) => cause instanceof Error ? cause.message : '操作失败，请重试'
async function load() {
  const current = ++sequence
  loading.value = true; error.value = ''
  try { const data = await getFeedback(status.value === 'all' ? '' : status.value, (page.value - 1) * 20); if (current === sequence) { items.value = data.items; total.value = data.total } }
  catch (cause) { if (current === sequence) error.value = message(cause) }
  finally { if (current === sequence) loading.value = false }
}
onActivated(async () => { void load(); try { settings.value = await getSupport() } catch (cause) { error.value = message(cause) } })
onDeactivated(() => { sequence++; dialog.value = false; previewOpen.value = false })
watch(page, load)
watch(status, () => { if (page.value === 1) void load(); else page.value = 1 })
function edit(item: Feedback) { selected.value = { ...item }; formError.value = ''; dialog.value = true }
async function save() {
  if (busy.value || !selected.value) return
  busy.value = true; formError.value = ''
  try { await saveFeedback(props.user.id, selected.value); dialog.value = false; notice.value = '处理结果已保存，用户可在小程序查看回复'; await load() }
  catch (cause) { formError.value = message(cause) }
  finally { busy.value = false }
}
async function saveContact() {
  if (busy.value || !settings.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { settings.value = await saveSupport(props.user.id, settings.value); notice.value = '会员权益和联系方式已更新' }
  catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}
async function inspect() {
  if (!selected.value?.catalog_id) return
  formError.value = ''
  try { preview.value = await catalogDetail(selected.value.catalog_id); previewOpen.value = true }
  catch (cause) { formError.value = message(cause) }
}
</script>
<template>
  <section class="admin-section">
    <UTabs v-model="tab" :items="[{ label: '小程序反馈', value: 'feedback' }, { label: '会员与联系设置', value: 'support' }]" :content="false" />
    <UAlert v-if="error" :title="error" color="error" class="notice" /><UAlert v-if="notice" :title="notice" color="success" class="notice" />
    <template v-if="tab === 'feedback'"><div class="section-toolbar"><USelect v-model="status" :items="[{ label: '全部状态', value: 'all' }, ...statusOptions]" aria-label="反馈状态" /><UButton label="刷新" color="neutral" variant="outline" :loading="loading" @click="load" /></div><div class="data-scroll"><table class="data-table"><thead><tr><th>用户</th><th>问题</th><th>资料</th><th>状态</th><th>更新时间</th><th>操作</th></tr></thead><tbody><tr v-for="item in items" :key="item.id"><td>{{ item.nickname || item.username }}</td><td><strong>{{ kindLabels[item.kind] }}</strong><div class="feedback-excerpt">{{ item.body }}</div></td><td>{{ item.paper_title || '—' }}</td><td>{{ statusOptions.find(value => value.value === item.status)?.label }}</td><td>{{ new Date(item.updated_at * 1000).toLocaleString() }}</td><td><UButton label="处理与回复" variant="soft" @click="edit(item)" /></td></tr><tr v-if="!items.length"><td colspan="6">{{ loading ? '正在加载' : '暂无符合条件的反馈' }}</td></tr></tbody></table></div><UPagination v-if="total > 20" v-model:page="page" :total="total" :items-per-page="20" class="mt-4" /></template>
    <form v-else-if="settings" class="field-stack support-settings" @submit.prevent="saveContact"><UFormField label="会员权益说明"><UTextarea v-model="settings.benefits" :rows="5" :maxlength="2000" class="w-full" /></UFormField><UFormField label="客服微信号"><UInput v-model="settings.wechat" maxlength="80" class="w-full" /></UFormField><UFormField label="联系电话"><UInput v-model="settings.phone" maxlength="40" class="w-full" /></UFormField><UFormField label="联系邮箱"><UInput v-model="settings.email" type="email" maxlength="120" class="w-full" /></UFormField><UFormField label="客服二维码地址"><UInput v-model="settings.qr_url" maxlength="500" placeholder="https://... 或本地可访问地址" class="w-full" /></UFormField><UFormField label="服务时间"><UInput v-model="settings.hours" maxlength="120" placeholder="例如：工作日 9:00-18:00" class="w-full" /></UFormField><p class="text-sm text-muted">联系方式可以留空；配置二维码地址后，小程序会员页会直接展示二维码。</p><UButton type="submit" label="保存服务信息" :loading="busy" /></form>
    <UModal v-model:open="dialog" title="处理小程序反馈" :dismissible="!busy" :close="!busy"><template #body><form v-if="selected" id="feedback-reply" class="field-stack" @submit.prevent="save"><div class="feedback-original"><strong>{{ selected.nickname || selected.username }} · {{ kindLabels[selected.kind] }}</strong><p>{{ selected.body }}</p><p v-if="selected.paper_title">关联资料：{{ selected.paper_title }}</p><UButton v-if="selected.catalog_id" label="查看关联资料" variant="outline" @click="inspect" /></div><UFormField label="处理状态"><USelect v-model="selected.status" :items="statusOptions" /></UFormField><UFormField label="回复用户"><UTextarea v-model="selected.reply" :maxlength="2000" :rows="4" class="w-full" placeholder="这段回复会显示在用户的小程序中" /></UFormField><UFormField label="内部处理备注"><UTextarea v-model="selected.internal_note" :maxlength="2000" :rows="3" class="w-full" placeholder="仅后台可见" /></UFormField><UAlert v-if="formError" :title="formError" color="error" /></form></template><template #footer><UButton label="取消" color="neutral" :disabled="busy" @click="dialog = false" /><UButton type="submit" form="feedback-reply" label="保存处理结果" :loading="busy" /></template></UModal>
    <UModal v-model:open="previewOpen" :title="preview?.title || '关联资料'"><template #body><template v-if="preview"><p>{{ preview.grade }} · {{ preview.subject }}</p><img v-for="asset in preview.assets.filter(item => item.kind === 'page').slice(0, 6)" :key="asset.id" :src="asset.url" alt="资料原稿" class="w-full my-3" loading="lazy" /></template></template></UModal>
  </section>
</template>
<style scoped>
.support-settings { max-width:640px;margin-top:24px; }.feedback-excerpt { max-width:300px;white-space:normal;overflow-wrap:anywhere;margin-top:6px; }.feedback-original p { white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7;margin:12px 0; }
</style>
