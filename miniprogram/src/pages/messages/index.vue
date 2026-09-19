<script setup lang="ts">
import { ref } from 'vue'
import { onReachBottom } from '@dcloudio/uni-app'
import ServicePage from '../../components/ServicePage.vue'
import { useConsumerPage } from '../../services/consumer-page'
import { fetchMessages, inboxState, messageDestination, subscriptionConfig, grantSubscription, requestKey, type Message } from '../../services/growth'
import { visitDestination } from '../../services/navigation'
import { session } from '../../services/session'
import { formatDate } from '../../content'
import { applyPendingReads, markAllMessagesRead, markMessageRead, readSync, syncMessageReads } from '../../services/message-reads'

const items = ref<Message[]>([]), more = ref(false), unreadOnly = ref(false)
const subscribe = ref({ available: false, template_id: '' })
async function load(valid: () => boolean, append = false) {
  await syncMessageReads()
  if (!valid()) return
  const result = await fetchMessages(unreadOnly.value, append ? items.value.length : 0)
  if (!valid()) return
  applyPendingReads(result.items, result.unread)
  items.value = append ? [...items.value, ...result.items.filter(item => !items.value.some(old => old.id === item.id))] : result.items
  more.value = result.has_more
  if (!append) { const config = await subscriptionConfig(); if (valid()) subscribe.value = config }
}
const page = useConsumerPage(load, () => { items.value = []; more.value = false; subscribe.value = { available: false, template_id: '' } })
const { error, busy, loading } = page
function filter(value: boolean) { if (busy.value || loading.value || unreadOnly.value === value) return; unreadOnly.value = value; void page.refresh() }
function loadMore() { if (more.value) void page.act(valid => load(valid, true)) }
function open(message: Message) {
  if (!page.ticket()()) return
  markMessageRead(message)
  visitDestination(messageDestination(message))
}
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
  <ServicePage title="消息中心" description="反馈回复、资料更新与会员服务进度。消息保留 180 天。" :error="error" :loading="loading" @retry="page.refresh">
    <view v-if="readSync.error" class="error-strip" role="status"><text class="grow">{{ readSync.error }}</text><wd-button role="button" variant="text" :loading="readSync.busy" :disabled="readSync.busy" @click="syncMessageReads">重试同步</wd-button></view>
    <view class="service-tabs" role="group" aria-label="消息筛选"><button role="button" hover-class="control-pressed" :class="{ selected: !unreadOnly }" :aria-pressed="!unreadOnly" :disabled="busy || loading" @click="filter(false)">全部消息</button><button role="button" hover-class="control-pressed" :class="{ selected: unreadOnly }" :aria-pressed="unreadOnly" :disabled="busy || loading" @click="filter(true)">未读{{ inboxState.unread ? ' · ' + (inboxState.unread > 99 ? '99+' : inboxState.unread) : '' }}</button></view>
    <view class="message-toolbar"><text>{{ inboxState.unread ? inboxState.unread + ' 条消息待查看' : '消息已读完' }}</text><wd-button role="button" size="small" variant="text" :disabled="busy || loading || !inboxState.unread" @click="allRead">全部已读</wd-button></view>
    <view v-if="subscribe.available && session.user?.has_wechat" class="service-card"><text class="service-card-title">微信服务提醒</text><text class="service-copy">主动订阅后，下一次处理结果可通过微信提醒你。</text><view class="service-actions"><wd-button role="button" size="small" variant="plain" :disabled="busy || loading" @click="requestSubscription">订阅下一次提醒</wd-button></view></view>
    <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" v-for="message in items" :key="message.id" class="service-card message-card" :class="{ unread: !message.read_at }" @click="open(message)"><view class="service-row"><text class="service-card-title">{{ message.title }}</text><view v-if="!message.read_at" class="unread-dot" aria-label="未读" /></view><text class="service-copy">{{ message.body }}</text><text class="service-meta">{{ formatDate(message.created_at) }} · 点击查看</text></button>
    <view v-if="!items.length && !loading && !error" class="service-empty"><wd-empty icon="no-content" :tip="unreadOnly ? '暂无未读消息' : '暂无服务消息'" /></view>
    <view v-if="more" class="loading-line"><wd-button role="button" variant="text" :loading="busy" :disabled="busy || loading" @click="loadMore">加载更多</wd-button></view>
  </ServicePage>
</template>
<style scoped>
.message-toolbar { display:flex;align-items:center;justify-content:space-between;gap:8px;margin:-8px 0 12px;flex-wrap:wrap;color:var(--lc-secondary);font-size:12px; }.message-card { width:100%;text-align:left;line-height:1.6; }.message-card.unread { border-left:3px solid var(--lc-primary); }.unread-dot { width:8px;height:8px;margin-top:8px;border-radius:50%;background:var(--lc-coral);flex:none; }
</style>
