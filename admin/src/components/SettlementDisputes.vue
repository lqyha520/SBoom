<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import type { UserInfo } from '../api'
import { useAdminPage } from '../admin-page'
import { dateTime } from '../growth'
import { createDispute, disputes, getDispute, disputeStatuses, downloadDisputeFile, financeGrant, financeUser, replyDispute, uploadDisputeFile, type Dispute, type DisputeStatus } from '../promotion-finance'
import { canPermission } from '../permissions'
const props = defineProps<{ user: UserInfo; personal?: boolean; target?: { kind: 'reward' | 'statement'; id: string } | null; requested?: string }>()
const emit = defineEmits<{ updated: [] }>()
const items = ref<Dispute[]>([]), total = ref(0), number = ref(1), filter = ref(''), current = ref<Dispute | null>(null)
const kind = ref<'reward' | 'statement'>(props.target?.kind ?? 'statement'), target = ref(props.target?.id ?? ''), title = ref(''), text = ref(''), evidence = ref(''), reply = ref(''), replyEvidence = ref(''), status = ref<DisputeStatus>('processing')
const creator = ref<HTMLDetailsElement>(), createOpen = ref(!!props.target), panel = ref<HTMLElement>()
const drafts = new Map<string, { reply: string; evidence: string; status: DisputeStatus }>()
let requestKey = crypto.randomUUID()
const page = useAdminPage(async valid => {
  const result = await disputes(filter.value, number.value, props.personal)
  if (!valid()) return
  items.value = result.items; total.value = result.total
  const id = current.value?.id || props.requested
  if (id) { const item = result.items.find(item => item.id === id) ?? await getDispute(id, props.personal); if (valid()) { if (!current.value) inspect(item); else current.value = item } }
})
watch([filter, number], page.load)
async function focusDetail() { await nextTick(); panel.value?.focus({ preventScroll: true }); panel.value?.scrollIntoView({ block: 'start' }) }
function remember() { if (current.value) drafts.set(current.value.id, { reply: reply.value, evidence: replyEvidence.value, status: status.value }) }
function inspect(item: Dispute) {
  remember(); current.value = item
  const draft = drafts.get(item.id)
  reply.value = draft?.reply ?? ''; replyEvidence.value = draft?.evidence ?? ''
  status.value = draft?.status ?? (item.status === 'open' && financeGrant(props.user, 'Review') ? 'processing' : item.status)
  void focusDetail()
}
async function close() { remember(); current.value = null; await nextTick(); const list = document.getElementById('settlement-dispute-list'); list?.focus({ preventScroll: true }); list?.scrollIntoView({ block: 'nearest' }) }
function create() {
  void page.act(async valid => {
    const item = await createDispute(props.user.id, { target_kind: kind.value, target_id: target.value, title: title.value, content: text.value, evidence: evidence.value, request_key: requestKey })
    if (valid()) { text.value = ''; title.value = ''; evidence.value = ''; requestKey = crypto.randomUUID(); createOpen.value = false; filter.value = ''; number.value = 1; await page.load(); if (!valid()) return; inspect(item); page.notice.value = '异议已提交，可在下方补充说明与凭据'; emit('updated') }
  })
}
function send() {
  void page.act(async valid => {
    if (!current.value) return
    const item = await replyDispute(props.user.id, current.value, reply.value, replyEvidence.value, financeGrant(props.user, 'Review') ? status.value : current.value.status)
    if (valid()) { reply.value = ''; replyEvidence.value = ''; drafts.delete(item.id); await page.load(); if (!valid()) return; inspect(item); page.notice.value = '异议回复已保存'; emit('updated') }
  })
}
function upload(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  if (!file) return
  void page.act(async valid => { try { if (!current.value) return; const id = current.value.id; await uploadDisputeFile(props.user.id, id, file); if (valid()) { await page.load(); page.notice.value = '异议凭据已上传'; emit('updated') } } finally { input.value = '' } })
}
</script>
<template>
  <div class="field-stack promotion-finance-page">
    <div class="promotion-heading"><div><h2>结算异议</h2><p>查看问题进展、补充凭据，与审核人员核对结算依据。</p></div><UButton label="刷新异议记录" icon="i-lucide-refresh-cw" variant="outline" :disabled="page.busy.value" :loading="page.loading.value" @click="page.load" /></div>
    <UAlert v-if="page.error.value" :title="page.error.value" color="error" /><UAlert v-if="page.notice.value" :title="page.notice.value" color="success" />
    <details v-if="!financeUser(user) && canPermission('settlements:create')" ref="creator" :open="createOpen" class="promotion-disclosure" @toggle="createOpen = creator?.open ?? false">
      <summary><span>发起结算异议</span><small>仅针对本人收益</small></summary>
      <form class="field-stack promotion-form mt-4" @submit.prevent="create">
        <div class="promotion-form-grid"><UFormField label="异议记录类型"><USelect v-model="kind" :items="[{ value: 'statement', label: '结算单' }, { value: 'reward', label: '订单奖励' }]" :disabled="page.busy.value" /></UFormField><UFormField label="关联结算单或订单编号" required><UInput v-model="target" required maxlength="80" placeholder="从奖励或结算明细中复制编号" :disabled="page.busy.value" /></UFormField></div>
        <UFormField label="异议标题" required><UInput v-model="title" required minlength="2" maxlength="100" placeholder="简要说明需要核对的问题" :disabled="page.busy.value" /></UFormField>
        <UFormField label="问题说明" required><UTextarea v-model="text" :rows="3" required minlength="2" maxlength="2000" placeholder="说明有疑问的金额、扣费或订单，附件可在提交后补充" :disabled="page.busy.value" /></UFormField>
        <UFormField label="凭据编号或说明"><UInput v-model="evidence" maxlength="500" :disabled="page.busy.value" /></UFormField>
        <div class="promotion-form-footer"><p>未结束的异议会阻止相关结算审核和付款。</p><UButton label="提交结算异议" icon="i-lucide-send" type="submit" :loading="page.busy.value" :disabled="page.busy.value || page.loading.value || text.trim().length < 2 || title.trim().length < 2 || !target.trim()" /></div>
      </form>
    </details>
    <div class="promotion-finance-toolbar"><UFormField label="处理状态"><USelect v-model="filter" :items="[{ value: '', label: '全部异议' }, ...Object.entries(disputeStatuses).map(([value, label]) => ({ value, label }))]" aria-label="异议状态筛选" :disabled="page.busy.value" /></UFormField><span class="text-xs text-muted">共 {{ total }} 条异议</span></div>
    <div class="promotion-master-detail" :class="{ 'has-detail': current }">
      <section id="settlement-dispute-list" tabindex="-1" class="field-stack promotion-list-panel" aria-label="异议列表">
        <div v-if="!items.length" class="promotion-empty"><UIcon name="i-lucide-messages-square" class="promotion-empty-icon" aria-hidden="true" /><strong>{{ page.loading.value ? '正在读取异议…' : '暂无结算异议' }}</strong><p>{{ filter ? '当前状态下没有异议，可切换到全部异议查看。' : '对金额或扣费有疑问时，可从本人奖励和结算单发起。' }}</p></div>
        <button v-for="item in items" :key="item.id" type="button" class="promotion-list-card" :class="{ selected: current?.id === item.id }" :aria-label="'查看异议：' + item.title" :aria-pressed="current?.id === item.id" :disabled="page.busy.value" @click="inspect(item)">
          <span class="promotion-card-top"><strong>{{ item.title }}</strong><span class="promotion-status" :class="['resolved', 'rejected'].includes(item.status) ? 'text-muted' : 'text-warning'">{{ disputeStatuses[item.status] }}</span></span>
          <span class="promotion-card-excerpt">{{ item.messages[0]?.content }}</span><span class="promotion-card-bottom"><span>{{ dateTime(item.created_at) }}</span><span>{{ item.messages.length }} 条记录 · {{ item.files.length }} 份附件</span></span>
        </button>
        <UPagination v-if="total > 20" v-model:page="number" :total="total" :items-per-page="20" :disabled="page.busy.value || page.loading.value" />
      </section>
      <section v-if="current" ref="panel" tabindex="-1" class="field-stack promotion-detail-panel" aria-label="结算异议详情">
        <div class="promotion-detail-heading"><div><h3>{{ current.title }} · {{ disputeStatuses[current.status] }}</h3><p class="break-all">关联编号：{{ current.target_id }}</p></div><UButton label="关闭异议详情" icon="i-lucide-x" variant="ghost" color="neutral" :disabled="page.busy.value" @click="close" /></div>
        <div class="promotion-thread" aria-label="异议往来记录"><article v-for="message in current.messages" :key="message.id" class="promotion-message"><div class="promotion-message-meta"><strong>{{ message.actor_name || '历史账号' }}</strong><time>{{ dateTime(message.created_at) }}</time></div><p class="whitespace-pre-wrap promotion-wrap">{{ message.content }}</p><p v-if="message.evidence" class="promotion-message-evidence">凭据：{{ message.evidence }}</p></article></div>
        <div v-if="current.files.length" class="promotion-detail-actions"><UButton v-for="file in current.files" :key="file.id" :label="file.name" icon="i-lucide-paperclip" variant="outline" :disabled="page.busy.value" @click="page.act(() => downloadDisputeFile(file))" /></div>
        <template v-if="['open', 'processing'].includes(current.status) && (financeGrant(user, 'Review') || current.beneficiary === 'admin:' + user.id && canPermission('settlements:create'))">
          <UFormField label="补充异议凭据（PNG / JPEG / PDF，不超过 2MB，最多 5 份）"><label class="promotion-file-picker" :aria-disabled="page.busy.value || current.files.length >= 5"><span><UIcon name="i-lucide-paperclip" aria-hidden="true" />选择异议凭据</span><small>已上传 {{ current.files.length }} / 5 份</small><input type="file" accept="image/png,image/jpeg,application/pdf" class="sr-only" aria-label="补充异议凭据" :disabled="page.busy.value || current.files.length >= 5" @change="upload"></label></UFormField>
          <form class="field-stack promotion-reply-form" @submit.prevent="send">
            <UFormField label="异议回复或处理说明" required><UTextarea v-model="reply" :rows="3" required minlength="2" maxlength="2000" placeholder="填写核对结果或补充说明" :disabled="page.busy.value" /></UFormField>
            <UFormField label="回复凭据编号"><UInput v-model="replyEvidence" maxlength="500" :disabled="page.busy.value" /></UFormField>
            <UFormField v-if="financeGrant(user, 'Review')" label="异议处理结果"><USelect v-model="status" :items="Object.entries(disputeStatuses).filter(([value]) => value !== 'open').map(([value, label]) => ({ value, label }))" :disabled="page.busy.value" /></UFormField>
            <div class="promotion-form-footer"><p>{{ financeGrant(user, 'Review') ? '结束异议不会直接改金额；需要更正时先处理结算单或登记调整。' : '回复会保留在此记录中，供审核人员核对。' }}</p><UButton label="保存异议回复" type="submit" :loading="page.busy.value" :disabled="page.busy.value || page.loading.value || reply.trim().length < 2" /></div>
          </form>
        </template>
        <p v-else class="promotion-loading">此异议已结束，处理记录与凭据已保留。</p>
      </section>
    </div>
  </div>
</template>
