<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onShow, onLoad, onHide, onUnload } from '@dcloudio/uni-app'
import PageChrome from '../../components/PageChrome.vue'
import AuthGate from '../../components/AuthGate.vue'
import { fetchSupport, fetchFeedback, fetchFeedbackItem, submitFeedback, feedbackKinds, feedbackStatus, type FeedbackKind, type Feedback, type SupportSettings } from '../../services/experience'
import { errorMessage } from '../../services/api'
import { ensureSession, session } from '../../services/session'
import { formatDate } from '../../content'
const settings = ref<SupportSettings | null>(null)
const records = ref<Feedback[]>([])
const selectedId = ref(''), focused = ref<Feedback | null>(null)
const displayed = computed(() => focused.value ? [focused.value, ...records.value.filter(item => item.id !== focused.value?.id)] : records.value)
const more = ref(false)
const body = ref('')
const paper = ref('')
const kind = ref<FeedbackKind>('other')
const busy = ref(false)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const kinds = computed(() => feedbackKinds.filter(item => paper.value || !['correction', 'download'].includes(item.value)))
const kindIndex = computed(() => Math.max(0, kinds.value.findIndex(item => item.value === kind.value)))
let sequence = 0
let active = true
async function load(append = false) {
  if (append && (loading.value || !more.value)) return
  await ensureSession()
  if (!active) return
  const current = ++sequence
  loading.value = true; error.value = ''
  try {
    const config = await fetchSupport()
    if (!active || current !== sequence) return
    settings.value = config
    if (session.user) {
      const result = await fetchFeedback(append ? records.value.length : 0)
      if (active && current === sequence) { records.value = append ? [...records.value, ...result.items] : result.items; more.value = result.has_more }
      if (!append && selectedId.value && active && current === sequence) { const result = await fetchFeedbackItem(selectedId.value); if (active && current === sequence) focused.value = result }
    }
  } catch (cause) { if (current === sequence) error.value = errorMessage(cause) }
  finally { if (current === sequence) loading.value = false }
}
async function submit() {
  if (busy.value || !session.user || body.value.trim().length < 5) return
  const owner = session.user.id
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await submitFeedback({ kind: kind.value, body: body.value.trim(), ...(paper.value ? { catalog_id: paper.value } : {}) })
    if (!active || session.user?.id !== owner) return
    body.value = ''; notice.value = '已提交，可在下方查看处理结果'; await load()
  } catch (cause) { if (active && session.user?.id === owner) error.value = errorMessage(cause) }
  finally { busy.value = false }
}
function phone() { if (settings.value?.phone) uni.makePhoneCall({ phoneNumber: settings.value.phone }) }
function copy(value: string) { uni.setClipboardData({ data: value }) }
watch(() => session.user?.id, () => { sequence++; records.value = []; focused.value = null; body.value = ''; notice.value = ''; error.value = '' })
onLoad(options => { paper.value = typeof options?.paper === 'string' ? options.paper : ''; selectedId.value = typeof options?.id === 'string' ? options.id : ''; const choice = feedbackKinds.find(item => item.value === options?.kind); if (choice) kind.value = choice.value })
onShow(() => { active = true; void load() })
function leave() { active = false; sequence++; loading.value = false }
onHide(leave); onUnload(leave)
</script>
<template>
  <view><PageChrome back fallback="/pages/account/index" /><view class="page-shell support-page">
    <text class="page-title">服务与反馈</text>
    <view v-if="settings" class="support-card"><text class="card-heading">会员与联系</text><text class="paragraph">{{ settings.benefits }}</text><text v-if="settings.hours" class="paragraph">服务时间：{{ settings.hours }}</text><view class="contact-actions"><wd-button role="button" v-if="settings.wechat" variant="plain" @click="copy(settings.wechat)">复制微信号</wd-button><wd-button role="button" v-if="settings.phone" variant="plain" @click="phone">拨打电话</wd-button><wd-button role="button" v-if="settings.email" variant="plain" @click="copy(settings.email)">复制邮箱</wd-button></view><text v-if="!settings.wechat && !settings.phone && !settings.email" class="paragraph">可在下方提交会员咨询，管理员处理后将在这里回复。</text></view>
    <view v-if="error" class="error-strip">{{ error }}<button role="button" class="section-link" @click="load()">重试</button></view><view v-if="notice" class="notice-strip">{{ notice }}</view>
    <AuthGate v-if="!session.user" />
    <template v-else>
      <view class="support-card"><text class="card-heading">提交问题</text><text v-if="paper" class="paragraph">已关联刚才查看的资料</text><picker :range="kinds.map(item => item.label)" :value="kindIndex" @change="kind = kinds[Number($event.detail.value)]!.value"><view class="kind-picker">{{ kinds[kindIndex]?.label }} ›</view></picker><textarea aria-label="问题描述" v-model="body" class="feedback-input" maxlength="2000" placeholder="请说明遇到的问题（至少 5 个字），勿填写密码等敏感信息" /><wd-button role="button" block :loading="busy" :disabled="busy || body.trim().length < 5" @click="submit">提交反馈</wd-button></view>
      <text class="card-heading">我的反馈</text><view v-for="item in displayed" :key="item.id" class="support-card" :style="item.id === selectedId ? 'border-color:var(--lc-primary)' : ''"><view class="record-heading"><text>{{ feedbackKinds.find(value => value.value === item.kind)?.label }}</text><text class="status">{{ feedbackStatus[item.status] }}</text></view><text v-if="item.paper_title" class="paragraph">{{ item.paper_title }}</text><text class="paragraph">{{ item.body }}</text><view v-if="item.reply" class="reply"><text>管理员回复</text><text class="paragraph">{{ item.reply }}</text></view><text class="record-date">{{ formatDate(item.updated_at) }}</text></view>
      <text v-if="!records.length && !loading" class="paragraph">还没有提交过反馈</text><wd-button role="button" v-if="more" variant="text" :loading="loading" @click="load(true)">加载更多</wd-button>
    </template>
  </view></view>
</template>
<style scoped>
.support-page { padding-bottom:40px; }.support-card { margin:16px 0;padding:18px;border:1px solid var(--lc-card-line);border-radius:14px;background:var(--lc-card); }.card-heading { display:block;font-weight:600;font-size:16px; }.paragraph { display:block;white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:1.8;margin:10px 0; }.contact-actions,.record-heading { display:flex;gap:10px;justify-content:space-between;flex-wrap:wrap; }.kind-picker { padding:12px 0;font-size:14px;color:var(--lc-primary); }.feedback-input { width:100%;box-sizing:border-box;min-height:140px;padding:12px;border-radius:8px;background:var(--lc-background);font-size:14px;margin-bottom:14px; }.status { color:var(--lc-primary);font-size:12px; }.reply { background:var(--lc-primary-soft);padding:12px;border-radius:8px;font-size:12px; }.record-date { font-size:11px;color:var(--lc-muted); }
</style>
