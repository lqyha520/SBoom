<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onHide, onLoad, onReachBottom, onUnload } from '@dcloudio/uni-app'
import ServicePage from '../components/ServicePage.vue'
import { useConsumerPage, type ConsumerTicket } from '../../services/consumer-page'
import { fetchRequests, fetchResourceRequest, submitRequest, requestStatus, type ResourceRequest } from '../../services/growth'
import { openCatalogPaper } from '../../services/navigation'
import { decodeParam } from '../../services/return-route'
import { formatDate } from '../../content'
import { fetchSiteHome } from '../../services/api'
import { session } from '../../services/session'
import { confirmAction } from '../../services/navigation'
import { readRequestDraft, writeRequestDraft } from '../../services/request-draft'
// Route query fields initialize the form without replacing ServicePage props.
defineOptions({ inheritAttrs: false })
const items = ref<ResourceRequest[]>([]), more = ref(false), title = ref(''), grade = ref(''), subject = ref(''), details = ref(''), highlight = ref('')
const focused = ref<ResourceRequest | null>(null)
const activeTab = ref<'new' | 'history'>('new'), fieldError = ref('')
const gradeValues = ref<string[]>([]), subjectValues = ref<string[]>([])
const customGrade = ref(false), customSubject = ref(false), optionsError = ref('')
const draftStatus = ref(''), draftSaved = ref(true)
let draftOwner = '', draftTimer: ReturnType<typeof setTimeout> | undefined
const gradeOptions = computed(() => ['请选择年级', ...new Set([...gradeValues.value, ...(grade.value ? [grade.value] : [])])])
const subjectOptions = computed(() => ['请选择学科', ...new Set([...subjectValues.value, ...(subject.value ? [subject.value] : [])])])
const displayed = computed(() => focused.value ? [focused.value, ...items.value.filter(item => item.id !== focused.value?.id)] : items.value)
let seed = { title: '', grade: '', subject: '' }
onLoad(options => { seed = { title: decodeParam(options?.title).slice(0, 120), grade: decodeParam(options?.grade).slice(0, 80), subject: decodeParam(options?.subject).slice(0, 80) }; restoreDraft(); highlight.value = decodeParam(options?.id); activeTab.value = highlight.value ? 'history' : 'new' })
function resetForm() { title.value = seed.title; grade.value = seed.grade; subject.value = seed.subject; details.value = ''; fieldError.value = '' }
function flushDraft() {
  clearTimeout(draftTimer); draftTimer = undefined
  if (!draftOwner) return
  draftSaved.value = writeRequestDraft(draftOwner, { title: title.value, grade: grade.value, subject: subject.value, details: details.value })
  draftStatus.value = draftSaved.value ? [title.value, grade.value, subject.value, details.value].some(value => value.trim()) ? '草稿已保存' : '' : '草稿保存失败，请稍后重试'
}
function restoreDraft() {
  clearTimeout(draftTimer); draftTimer = undefined; draftOwner = session.user?.id || ''
  const saved = readRequestDraft(draftOwner)
  resetForm()
  if (saved && !seed.title && !seed.grade && !seed.subject) {
    title.value = saved.title; grade.value = saved.grade; subject.value = saved.subject; details.value = saved.details
    draftStatus.value = '已恢复未提交草稿'
  } else draftStatus.value = ''
  customGrade.value = false; customSubject.value = false; draftSaved.value = true
}
async function clearDraft() {
  const owner = draftOwner, valid = page.ticket()
  if (busy.value || !await confirmAction('清空需求草稿', '清空当前填写内容，不影响已提交的需求。') || owner !== draftOwner || !valid()) return
  seed = { title: '', grade: '', subject: '' }; resetForm(); flushDraft()
}
async function loadOptions(valid: ConsumerTicket) {
  try {
    const home = await fetchSiteHome({ scope: valid, force: !!optionsError.value })
    if (valid()) { gradeValues.value = home.dictionaries.grades; subjectValues.value = home.dictionaries.subjects; optionsError.value = '' }
  } catch { if (valid()) optionsError.value = '年级与学科选项暂未加载' }
}
async function load(valid: ConsumerTicket, append = false) {
  if (!append) void loadOptions(valid)
  const result = await fetchRequests(append ? items.value.length : 0, { scope: valid })
  if (valid()) { items.value = append ? [...items.value, ...result.items.filter(item => !items.value.some(old => old.id === item.id))] : result.items; more.value = result.has_more }
  if (!append && highlight.value && valid()) { const selected = await fetchResourceRequest(highlight.value, { scope: valid }); if (valid()) focused.value = selected }
}
const page = useConsumerPage(load, () => { items.value = []; focused.value = null; more.value = false })
const { error, loading, busy } = page
watch(() => session.user?.id, () => { flushDraft(); restoreDraft() }, { flush: 'sync' })
watch([title, grade, subject, details], () => {
  clearTimeout(draftTimer)
  if (draftOwner) draftTimer = setTimeout(flushDraft, 400)
})
onHide(flushDraft); onUnload(flushDraft)
function submit() {
  if (title.value.trim().length < 2) { fieldError.value = '请填写至少 2 个字的资料名称'; return }
  fieldError.value = ''
  void page.act(async valid => { await submitRequest({ title: title.value.trim(), grade: grade.value.trim(), subject: subject.value.trim(), details: details.value.trim() }); if (!valid()) return; seed = { title: '', grade: '', subject: '' }; resetForm(); flushDraft(); activeTab.value = 'history'; await load(valid); if (valid()) uni.showToast({ title: '需求已提交', icon: 'none' }) })
}
function loadMore() { if (activeTab.value === 'history' && more.value) void page.act(valid => load(valid, true)) }
onReachBottom(loadMore)
</script>
<template>
  <ServicePage title="资料需求" description="没找到需要的资料？告诉我们，处理进度会同步到消息中心。每天可新增 5 条需求。" :error="error" :loading="loading" @retry="page.refresh">
    <view class="service-tabs" aria-role="group" role="group" aria-label="资料需求内容"><button role="button" hover-class="control-pressed" :class="{ selected: activeTab === 'new' }" :aria-pressed="activeTab === 'new'" :disabled="busy" @click="activeTab = 'new'">提交需求</button><button role="button" hover-class="control-pressed" :class="{ selected: activeTab === 'history' }" :aria-pressed="activeTab === 'history'" :disabled="busy" @click="activeTab = 'history'">我的需求记录</button></view>
    <view v-if="activeTab === 'new'" class="service-card service-fields request-form">
      <view class="request-form-heading"><text class="service-card-title">我需要的资料</text><button class="bare-icon" role="button" aria-label="清空需求草稿" title="清空草稿" :disabled="busy || !(title || grade || subject || details)" @click="clearDraft"><wd-icon name="delete" size="20px" /></button></view>
      <view v-if="draftStatus" class="draft-status" :class="{ failed: !draftSaved }" role="status"><text>{{ draftStatus }}</text><button v-if="!draftSaved" class="section-link" role="button" @click="flushDraft">重试保存</button></view>
      <view v-if="optionsError" class="draft-status" role="status"><text>{{ optionsError }}</text><button class="section-link" role="button" :disabled="loading" @click="loadOptions(page.ticket())">重试</button></view>
      <view aria-role="group" role="group" aria-label="资料名称"><text class="field-label">资料名称（必填）</text><wd-input custom-class="request-input" v-model="title" placeholder="例如：六年级分数应用题" :maxlength="120" :disabled="busy" @update:model-value="fieldError = ''" /><text v-if="fieldError" class="field-error" role="alert">{{ fieldError }}</text></view>
      <view aria-role="group" role="group" aria-label="年级"><view class="request-field-heading"><text class="field-label">年级（选填）</text><button class="section-link" :disabled="busy" @click="customGrade = !customGrade">{{ customGrade ? '选择年级' : '其他年级' }}</button></view><wd-input v-if="customGrade" custom-class="request-input" v-model="grade" placeholder="填写年级" :maxlength="80" :disabled="busy" /><picker v-else :range="gradeOptions" :value="Math.max(0, gradeOptions.indexOf(grade))" :disabled="busy" @change="grade = Number($event.detail.value) ? gradeOptions[Number($event.detail.value)]! : ''"><view class="request-choice"><text>{{ grade || '请选择年级' }}</text><wd-icon name="down" size="16px" /></view></picker></view>
      <view aria-role="group" role="group" aria-label="学科"><view class="request-field-heading"><text class="field-label">学科（选填）</text><button class="section-link" :disabled="busy" @click="customSubject = !customSubject">{{ customSubject ? '选择学科' : '其他学科' }}</button></view><wd-input v-if="customSubject" custom-class="request-input" v-model="subject" placeholder="填写学科" :maxlength="80" :disabled="busy" /><picker v-else :range="subjectOptions" :value="Math.max(0, subjectOptions.indexOf(subject))" :disabled="busy" @change="subject = Number($event.detail.value) ? subjectOptions[Number($event.detail.value)]! : ''"><view class="request-choice"><text>{{ subject || '请选择学科' }}</text><wd-icon name="down" size="16px" /></view></picker></view>
      <view aria-role="group" role="group" aria-label="补充说明"><text class="field-label">补充说明（选填）</text><wd-textarea custom-class="request-notes" v-model="details" auto-height placeholder="教材版本、单元、题型等补充说明" :maxlength="1000" show-word-limit :disabled="busy" /></view>
      <wd-button role="button" block :loading="busy" :disabled="busy || loading" @click="submit">提交资料需求</wd-button>
    </view>
    <template v-else>
      <view class="service-row history-title"><text class="service-card-title">处理进度</text><wd-button role="button" variant="text" size="small" :disabled="busy || loading" @click="page.refresh">刷新进度</wd-button></view>
      <view v-for="item in displayed" :key="item.id" class="service-card" :class="{ highlighted: item.id === highlight }"><view class="service-row"><text class="service-card-title">{{ item.title }}</text><wd-tag variant="light">{{ requestStatus[item.status] }}</wd-tag></view><text class="service-meta">{{ [item.grade, item.subject, formatDate(item.created_at)].filter(Boolean).join(' · ') }}</text><text v-if="item.details" class="service-copy">{{ item.details }}</text><view v-if="item.reply" class="service-reply">{{ item.reply }}</view><view v-if="item.catalog_id" class="service-actions"><wd-button role="button" size="small" variant="plain" @click="openCatalogPaper(item.catalog_id)">查看补齐资料</wd-button></view></view>
      <view v-if="!displayed.length && !loading && !error" class="service-empty"><wd-empty icon="no-content" tip="还没有提交过资料需求"><template #bottom><view class="empty-actions"><wd-button role="button" variant="plain" @click="activeTab = 'new'">提交第一条需求</wd-button></view></template></wd-empty></view><view v-if="more" class="loading-line"><wd-button role="button" variant="text" :loading="busy" :disabled="busy || loading" @click="loadMore">加载更多记录</wd-button></view>
    </template>
  </ServicePage>
</template>
<style scoped>.history-title { align-items:center;margin:0 0 14px; }.highlighted { border-color:var(--lc-primary); }.field-error { display:block;margin-top:6px;color:#a34040;font-size:12px;line-height:1.6; }.request-form { --wot-textarea-inner-min-height:108px;--wot-input-padding:10px 12px;--wot-input-bg:var(--lc-background);--wot-textarea-padding:10px 12px;--wot-textarea-bg:var(--lc-background); }.request-form :deep(.request-input),.request-form :deep(.request-notes) { border:1px solid var(--lc-card-line);border-radius:var(--lc-radius-control);overflow:hidden; }
.request-form-heading,.request-field-heading,.draft-status,.request-choice { display:flex;align-items:center;justify-content:space-between;gap:12px; }.request-field-heading .field-label { margin:0; }.request-choice { min-height:48px;padding:10px 12px;border:1px solid var(--lc-card-line);border-radius:8px;background:var(--lc-background);font-size:14px; }.request-choice text { min-width:0;overflow-wrap:anywhere; }.draft-status { font-size:12px;line-height:1.6;color:var(--lc-secondary); }.draft-status.failed { color:#a34040; }
</style>
