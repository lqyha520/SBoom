<script setup lang="ts">
import { ref } from 'vue'
import { onReachBottom } from '@dcloudio/uni-app'
import ServicePage from '../components/ServicePage.vue'
import { useConsumerPage, type ConsumerTicket } from '../../services/consumer-page'
import { errorMessage } from '../../services/api'
import { fetchMessages, inboxState, unreadTracker, messageDestination, messageHasDestination, subscriptionConfig, grantSubscription, requestKey, type Message } from '../../services/growth'
import { visitDestination } from '../../services/navigation'
import { session } from '../../services/session'
import { formatDate } from '../../content'
import { applyPendingReads, markAllMessagesRead, markMessageRead, readSync, syncMessageReads } from '../../services/message-reads'

const items = ref<Message[]>([]), more = ref(false), unreadOnly = ref(false)
const expanded = ref<Message | null>(null), expandedOpen = ref(false)
const nextOffset = ref(0)
let listVersion = ''
const subscribe = ref({ available: false, template_id: '' })
const subscriptionLoading = ref(false), subscriptionError = ref('')
let subscriptionRevision = 0
async function loadSubscription(valid: ConsumerTicket) {
  if (!valid()) return
  const revision = ++subscriptionRevision
  const current = () => valid() && revision === subscriptionRevision
  subscriptionLoading.value = true; subscriptionError.value = ''; subscribe.value = { available: false, template_id: '' }
  try {
    const config = await subscriptionConfig({ scope: valid })
    if (current()) subscribe.value = config
  } catch (cause) { if (current()) subscriptionError.value = errorMessage(cause) }
  finally { if (current()) subscriptionLoading.value = false }
}
async function load(valid: ConsumerTicket, append = false) {
  if (append && unreadOnly.value && readSync.busy) return
  void syncMessageReads()
  if (!valid()) return
  const version = unreadTracker.version()
  // 未读集合在回执完成后会缩短，重新读取首页，避免旧 offset 跳过消息。
  if (unreadOnly.value && version !== listVersion) append = false
  const apply = unreadTracker.read()
  const offset = append ? nextOffset.value : 0
  // 订阅配置独立加载，不阻塞消息筛选、分页或已读操作。
  if (!append) void loadSubscription(valid)
  const result = await fetchMessages(unreadOnly.value, offset, 20, { scope: valid })
  if (!valid()) return
  applyPendingReads(result.items, result.unread, apply)
  nextOffset.value = offset + result.items.length
  listVersion = version
  const visible = unreadOnly.value ? result.items.filter(item => !item.read_at) : result.items
  items.value = append ? [...items.value, ...visible.filter(item => !items.value.some(old => old.id === item.id))] : visible
  more.value = result.has_more
}
const page = useConsumerPage(load, () => { subscriptionRevision++; subscriptionLoading.value = false; subscriptionError.value = ''; items.value = []; nextOffset.value = 0; more.value = false; expanded.value = null; expandedOpen.value = false; subscribe.value = { available: false, template_id: '' } })
const { error, busy, loading } = page
function filter(value: boolean) { if (busy.value || loading.value || unreadOnly.value === value) return; unreadOnly.value = value; void page.refresh() }
function loadMore() { if (more.value && !(unreadOnly.value && readSync.busy)) void page.act(valid => load(valid, true)) }
function open(message: Message) {
  if (!page.ticket()()) return
  markMessageRead(message)
  // 没有可跳转目标的系统通知在站内展开全文，避免跳到消息页原地打转。
  if (!messageHasDestination(message)) { expanded.value = message; expandedOpen.value = true; return }
  visitDestination(messageDestination(message))
}
function closeExpanded() { expandedOpen.value = false; expanded.value = null }
function allRead() { void page.act(async valid => { await markAllMessagesRead(); if (valid()) await load(valid) }) }
function requestSubscription() {
  // #ifdef H5
  uni.showToast({ title: '请在微信小程序内订阅提醒', icon: 'none' })
  // #endif
  // #ifdef MP-WEIXIN
  void page.act(async valid => {
    const template = subscribe.value.template_id
    if (!subscribe.value.available || !session.user?.has_wechat) return
    const result = await new Promise<Record<string, unknown>>((resolve, reject) => uni.requestSubscribeMessage({ tmplIds: [template], success: value => resolve(value as unknown as Record<string, unknown>), fail: () => reject(new Error('未能打开微信订阅，请稍后重试')) }))
    if (!valid()) return
    if (result[template] !== 'accept') { uni.showToast({ title: '已保留站内消息提醒', icon: 'none' }); return }
    await grantSubscription(template, requestKey())
    if (valid()) uni.showToast({ title: '已订阅下一次服务提醒', icon: 'none' })
  })
  // #endif
}
onReachBottom(loadMore)
</script>
<template>
  <ServicePage title="消息中心" description="反馈回复、资料更新与会员服务进度。消息保留 180 天。" gate-description="登录后查看反馈回复、资料更新和服务提醒" :error="error" :loading="loading" @retry="page.refresh">
    <view v-if="readSync.error" class="error-strip" role="status"><text class="grow">{{ readSync.error }}</text><wd-button role="button" variant="text" :loading="readSync.busy" :disabled="readSync.busy" @click="syncMessageReads">重试同步</wd-button></view>
    <view class="service-tabs" aria-role="group" role="group" aria-label="消息筛选"><button role="button" hover-class="control-pressed" :class="{ selected: !unreadOnly }" :aria-pressed="!unreadOnly" :disabled="busy || loading" @click="filter(false)">全部消息</button><button role="button" hover-class="control-pressed" :class="{ selected: unreadOnly }" :aria-pressed="unreadOnly" :disabled="busy || loading" @click="filter(true)">未读{{ inboxState.unread ? ' · ' + (inboxState.unread > 99 ? '99+' : inboxState.unread) : '' }}</button></view>
    <view class="message-toolbar"><text>{{ inboxState.unread ? inboxState.unread + ' 条消息待查看' : '消息已读完' }}</text><wd-button role="button" size="small" variant="text" :disabled="busy || loading || !inboxState.unread" @click="allRead">全部已读</wd-button></view>
    <view v-if="subscriptionError" class="error-strip" role="status"><text class="grow">微信提醒配置暂时无法加载：{{ subscriptionError }}。站内消息仍可使用。</text><wd-button role="button" variant="text" :loading="subscriptionLoading" :disabled="subscriptionLoading" @click="loadSubscription(page.ticket())">重试提醒配置</wd-button></view>
    <view v-if="subscribe.available && session.user?.has_wechat" class="service-card"><text class="service-card-title">微信服务提醒</text><text class="service-copy">主动订阅后，下一次处理结果可通过微信提醒你。</text><view class="service-actions"><wd-button role="button" size="small" variant="plain" :disabled="busy || loading" @click="requestSubscription">订阅下一次提醒</wd-button></view></view>
    <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" v-for="message in items" :key="message.id" class="service-card message-card" :class="{ unread: !message.read_at }" @click="open(message)"><view class="service-row"><text class="service-card-title">{{ message.title }}</text><view v-if="!message.read_at" class="unread-dot" aria-label="未读" /></view><text class="service-copy message-body">{{ message.body }}</text><text class="service-meta">{{ formatDate(message.created_at) }} · {{ messageHasDestination(message) ? '点击查看' : '点击查看全文' }}</text></button>
    <view v-if="!items.length && !loading && !error" class="service-empty"><wd-empty icon="no-content" :tip="unreadOnly ? '暂无未读消息' : '暂无服务消息'" /></view>
    <view v-if="more" class="loading-line"><wd-button role="button" variant="text" :loading="busy" :disabled="busy || loading || unreadOnly && readSync.busy" @click="loadMore">加载更多</wd-button></view>
    <view v-else-if="items.length && !busy && !loading && !error" class="list-end">已显示全部消息</view>
    <wd-popup v-model="expandedOpen" position="bottom" :z-index="1200" root-portal safe-area-inset-bottom custom-style="border-radius:22px 22px 0 0" @close="closeExpanded">
      <view v-if="expanded" class="sheet message-sheet" aria-role="dialog" role="dialog" aria-modal="true" aria-label="消息全文">
        <view class="sheet-handle" />
        <view class="sheet-head"><text class="sheet-title">{{ expanded.title }}</text><button class="bare-icon" role="button" aria-label="关闭消息全文" @click="closeExpanded"><wd-icon name="close" size="20px" /></button></view>
        <text class="message-sheet-meta">{{ formatDate(expanded.created_at) }}</text>
        <scroll-view scroll-y class="message-sheet-body"><text selectable>{{ expanded.body }}</text></scroll-view>
        <wd-button block role="button" variant="plain" @click="closeExpanded">关闭</wd-button>
      </view>
    </wd-popup>
  </ServicePage>
</template>
<style scoped>
.message-toolbar { display:flex;align-items:center;justify-content:space-between;gap:8px;margin:-8px 0 12px;flex-wrap:wrap;color:var(--lc-secondary);font-size:12px; }.message-card { width:100%;text-align:left;line-height:1.6; }.message-card.unread { border-left:3px solid var(--lc-primary); }.unread-dot { width:8px;height:8px;margin-top:8px;border-radius:50%;background:var(--lc-coral);flex:none; }
.message-body { display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:4;overflow:hidden;white-space:pre-wrap;overflow-wrap:anywhere; }
.message-sheet { max-width:520px;margin:0 auto; }.message-sheet-meta { display:block;margin-bottom:12px;color:var(--lc-muted);font-size:12px; }.message-sheet-body { max-height:48vh;margin-bottom:16px; }.message-sheet-body text { display:block;color:var(--lc-text);font-size:15px;line-height:1.9;white-space:pre-wrap;overflow-wrap:anywhere; }
</style>
