<script setup lang="ts">
import { copyWithPrivacy } from '../../services/privacy'
import { computed, ref, watch } from 'vue'
import { onShow, onLoad, onHide, onUnload } from '@dcloudio/uni-app'
import PageChrome from '../../components/PageChrome.vue'
import AuthGate from '../../components/AuthGate.vue'
import { fetchSupport, fetchFeedback, fetchFeedbackItem, submitFeedback, feedbackKinds, feedbackStatus, type FeedbackKind, type Feedback, type SupportSettings } from '../../services/experience'
import { errorMessage } from '../../services/api'
import { ensureSession, session } from '../../services/session'
import { formatDate } from '../../content'
import { usePageLifecycle } from '../../services/page-lifecycle'
import { diagnosticSummary } from '../../services/runtime'
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
const activeTab = ref<'new' | 'history'>('new')
const kinds = computed(() => feedbackKinds.filter(item => paper.value || !['correction', 'download'].includes(item.value)))
const kindIndex = computed(() => Math.max(0, kinds.value.findIndex(item => item.value === kind.value)))
let sequence = 0
const requests = usePageLifecycle(() => session.user?.id)
requests.show()
let active = true
async function load(append = false) {
  if (append && (loading.value || !more.value)) return
  await ensureSession()
  if (!active) return
  const current = ++sequence
  const scope = requests.begin()
  loading.value = true; error.value = ''
  try {
    const [config, feedback] = await Promise.allSettled([
      append ? Promise.resolve(settings.value) : fetchSupport({ scope }),
      session.user ? fetchFeedback(append ? records.value.length : 0, { scope }) : Promise.resolve(null),
    ])
    if (!active || current !== sequence) return
    if (config.status === 'fulfilled') settings.value = config.value
    if (feedback.status === 'fulfilled' && feedback.value) {
      const result = feedback.value
      records.value = append ? [...records.value, ...result.items] : result.items; more.value = result.has_more
    }
    error.value = [config.status === 'rejected' ? '联系方式暂未加载成功' : '', feedback.status === 'rejected' ? '反馈记录暂未加载成功' : ''].filter(Boolean).join('；')
    if (session.user && !append && selectedId.value) { const result = await fetchFeedbackItem(selectedId.value, { scope }); if (active && current === sequence) focused.value = result }
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
    body.value = ''; activeTab.value = 'history'; notice.value = '已提交，可在我的反馈中查看处理结果'; await load()
  } catch (cause) { if (active && session.user?.id === owner) error.value = errorMessage(cause) }
  finally { busy.value = false }
}
function phone() { if (settings.value?.phone) uni.makePhoneCall({ phoneNumber: settings.value.phone }) }
function copy(value: string) { copyWithPrivacy({ data: value, fail: () => uni.showToast({ title: '复制失败，请稍后重试', icon: 'none' }) }) }
function previewQr() { if (settings.value?.qr_url) uni.previewImage({ urls: [settings.value.qr_url] }) }
watch(() => session.user?.id, () => { sequence++; requests.invalidate(); records.value = []; focused.value = null; body.value = ''; notice.value = ''; error.value = '' })
onLoad(options => { paper.value = typeof options?.paper === 'string' ? options.paper : ''; selectedId.value = typeof options?.id === 'string' ? options.id : ''; activeTab.value = selectedId.value ? 'history' : 'new'; const choice = feedbackKinds.find(item => item.value === options?.kind); if (choice) kind.value = choice.value })
onShow(() => { active = true; requests.show(); void load() })
function leave() { active = false; requests.leave(); sequence++; loading.value = false }
function reconnect() { if (active && !busy.value) void load() }
uni.$on?.('lc-network-restored', reconnect)
onHide(leave); onUnload(() => { leave(); uni.$off?.('lc-network-restored', reconnect) })
</script>
<template>
  <view class="support-page-shell"><view class="page-navigation-sticky"><PageChrome back fallback="/pages/account/index" /></view><view class="content-width support-page">
    <text class="page-title">服务与反馈</text>
    <text class="support-description">咨询使用问题，查看反馈处理进度</text>
    <view class="diagnostic-row"><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="quiet-action" role="button" aria-label="复制故障记录" @click="copy(diagnosticSummary())"><wd-icon name="copy" size="13px" /><text>复制故障记录</text></button><text class="diagnostic-hint">仅含错误统计、加载耗时与文件大小，不含账号或填写内容。由你决定是否发给客服。</text></view>
    <view v-if="session.user" class="service-tabs" aria-role="group" role="group" aria-label="服务与反馈内容"><button role="button" hover-class="control-pressed" :class="{ selected: activeTab === 'new' }" :aria-pressed="activeTab === 'new'" :disabled="busy" @click="activeTab = 'new'">联系与反馈</button><button role="button" hover-class="control-pressed" :class="{ selected: activeTab === 'history' }" :aria-pressed="activeTab === 'history'" :disabled="busy" @click="activeTab = 'history'">我的反馈</button></view>
    <view v-if="settings && activeTab === 'new'" class="support-card"><text class="card-heading">联系客服</text><text class="paragraph">{{ settings.benefits }}</text><text v-if="settings.hours" class="paragraph">服务时间：{{ settings.hours }}</text><view class="contact-actions"><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" v-if="settings.wechat" class="contact-chip" @click="copy(settings.wechat)"><wd-icon name="copy" size="13px" /><text>复制微信号</text></button><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" v-if="settings.phone" class="contact-chip" @click="phone"><wd-icon name="phone" size="13px" /><text>拨打电话</text></button><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" v-if="settings.email" class="contact-chip" @click="copy(settings.email)"><wd-icon name="email" size="13px" /><text>复制邮箱</text></button></view><view v-if="settings.qr_url" class="support-qr"><image :src="settings.qr_url" mode="aspectFit" show-menu-by-longpress @click="previewQr" /><text>点击放大客服二维码</text></view><text v-if="!settings.wechat && !settings.phone && !settings.email && !settings.qr_url" class="paragraph">可以提交问题，回复后会通过消息中心通知你。</text></view>
    <view v-if="error" class="error-strip" role="alert"><text class="grow">{{ error }}</text><button hover-class="control-pressed" role="button" class="section-link" :disabled="loading" @click="load()">重试</button></view><view v-if="notice" class="notice-strip" role="status">{{ notice }}</view>
    <view v-if="loading" class="loading-line" role="status"><wd-loading size="18px" /><text>正在加载{{ activeTab === 'history' ? '反馈记录' : '服务信息' }}</text></view>
    <AuthGate v-if="!session.user" title="登录后提交反馈" description="登录后可提交问题并查看回复" @restored="load()" />
    <template v-else>
      <view v-if="activeTab === 'new'" class="support-card"><text class="card-heading">提交问题</text><text v-if="paper" class="paragraph">已关联刚才查看的资料</text><picker :disabled="busy" :range="kinds.map(item => item.label)" :value="kindIndex" @change="kind = kinds[Number($event.detail.value)]!.value"><view class="kind-picker"><text>问题类型</text><text>{{ kinds[kindIndex]?.label }}</text><wd-icon name="arrow-down" size="14px" /></view></picker><textarea aria-label="问题描述" v-model="body" :disabled="busy" class="feedback-input" maxlength="2000" placeholder="请说明遇到的问题（至少 5 个字）" /><text class="feedback-hint">{{ body.length }}/2000 · 请勿填写密码等敏感信息</text><wd-button role="button" block :loading="busy" :disabled="busy || body.trim().length < 5" @click="submit">提交反馈</wd-button></view>
      <template v-else><view class="feedback-history-title"><text class="card-heading">处理记录</text><button class="section-link" hover-class="control-pressed" :disabled="loading || busy" @click="load()">刷新进度</button></view><view v-for="item in displayed" :key="item.id" class="support-card" :style="item.id === selectedId ? 'border-color:var(--lc-primary)' : ''"><view class="record-heading"><text>{{ feedbackKinds.find(value => value.value === item.kind)?.label }}</text><text class="status">{{ feedbackStatus[item.status] }}</text></view><text v-if="item.paper_title" class="paragraph">{{ item.paper_title }}</text><text class="paragraph">{{ item.body }}</text><view v-if="item.reply" class="reply"><text>管理员回复</text><text class="paragraph">{{ item.reply }}</text></view><text class="record-date">{{ formatDate(item.updated_at) }}</text></view>
      <view v-if="!displayed.length && !loading && !error" class="service-empty"><wd-empty icon="no-content" tip="还没有提交过反馈"><template #bottom><view class="empty-actions"><wd-button role="button" variant="plain" @click="activeTab = 'new'">提交问题</wd-button></view></template></wd-empty></view><wd-button role="button" v-if="more" variant="text" :loading="loading" @click="load(true)">加载更多</wd-button></template>
    </template>
  </view></view>
</template>
<style scoped>
.support-page { padding-top:12px;padding-bottom:calc(32px + env(safe-area-inset-bottom)); }.support-description { display:block;margin:6px 0 20px;font-size:13px;line-height:1.8;color:var(--lc-secondary); }.diagnostic-row { display:flex;flex-direction:column;align-items:flex-start;gap:7px;margin:-2px 0 18px; }.quiet-action { display:inline-flex;align-items:center;gap:5px;flex:none;min-height:30px;margin:0;padding:0 10px;border:1px solid var(--lc-card-line);border-radius:999px;background:var(--lc-surface);color:var(--lc-secondary);font-size:12px;line-height:1; }.diagnostic-hint { color:var(--lc-muted);font-size:12px;line-height:1.65; }.feedback-history-title { display:flex;align-items:center;justify-content:space-between;gap:12px; }.feedback-hint { display:block;margin:-4px 0 14px;color:var(--lc-muted);font-size:12px;line-height:1.7; }.kind-picker { display:flex;align-items:center;gap:8px;min-height:44px;margin:10px 0; }.kind-picker text:first-child { margin-right:auto;color:var(--lc-secondary); }.support-qr { display:flex;flex-direction:column;align-items:center;gap:8px;margin-top:16px;color:var(--lc-muted);font-size:12px; }.support-qr image { width:136px;height:136px; }
.support-card { margin:16px 0;padding:18px;border:1px solid var(--lc-card-line);border-radius:var(--lc-radius-card);background:var(--lc-card);box-shadow:var(--lc-card-shadow-soft); }.card-heading { display:block;font-weight:600;font-size:16px; }.paragraph { display:block;white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.8;margin:10px 0; }.contact-actions { display:flex;gap:8px;flex-wrap:wrap;margin-top:14px; }.contact-chip { display:inline-flex;align-items:center;gap:6px;flex:none;min-height:34px;margin:0;padding:0 13px;border:1px solid var(--lc-card-line);border-radius:999px;background:var(--lc-surface);color:var(--lc-primary);font-size:12.5px;line-height:1; }.record-heading { display:flex;gap:10px;justify-content:space-between;flex-wrap:wrap; }.kind-picker { padding:12px 0;font-size:14px;color:var(--lc-primary); }.feedback-input { width:100%;height:140px;box-sizing:border-box;min-height:140px;padding:12px;border-radius:8px;background:var(--lc-background);font-size:14px;margin-bottom:14px; }.status { color:var(--lc-primary);font-size:12px; }.reply { background:var(--lc-primary-soft);padding:12px;border-radius:8px;font-size:12px; }.record-date { font-size: 12px;color:var(--lc-muted); }
</style>
