<script setup lang="ts">
import { ref } from 'vue'
import { onLoad, onReachBottom } from '@dcloudio/uni-app'
import ServicePage from '../../components/ServicePage.vue'
import { useConsumerPage } from '../../services/consumer-page'
import { fetchPlans, fetchOrders, fetchOrder, cancelOrder, syncOrder, requestRefund, syncRefund, orderStatus, refundStatus, yuan, openOrder, type Order } from '../../services/growth'
import { checkout, checkoutSupport } from '../../services/checkout'
import { confirmAction } from '../../services/navigation'
import { refreshMembership, session } from '../../services/session'
import { openSupport } from '../../services/experience'
import { formatDate } from '../../content'
const id = ref(''), items = ref<Order[]>([]), selected = ref<Order | null>(null), more = ref(false), reason = ref(''), refundOpen = ref(false), canPay = ref(false), online = ref(false), notice = ref('')
onLoad(options => { id.value = String(options?.id || '') })
async function load(valid: () => boolean, append = false) {
  if (id.value) { const result = await fetchOrder(id.value); if (valid()) selected.value = result }
  else { const result = await fetchOrders(append ? items.value.length : 0); if (valid()) { items.value = append ? [...items.value, ...result.items.filter(item => !items.value.some(old => old.id === item.id))] : result.items; more.value = result.has_more } }
  if (!append) { const plans = await fetchPlans(); if (valid()) { online.value = plans.checkout_enabled; canPay.value = plans.checkout_enabled && checkoutSupport(plans.ios_enabled) && !!session.user?.has_wechat } }
}
const page = useConsumerPage(load, () => { items.value = []; selected.value = null; more.value = false; refundOpen.value = false; reason.value = ''; notice.value = ''; canPay.value = false; online.value = false })
const { error, busy, loading } = page
function payable(order: Order) { return ['created', 'pending'].includes(order.status) && order.expires_at > Date.now() / 1000 }
function pay() { if (!selected.value || !canPay.value) return; void page.act(async valid => { const result = await checkout(selected.value!.id, valid); if (valid() && result) { selected.value = result; notice.value = result.status === 'paid' ? '付款已确认，会员权益已更新' : '付款结果仍在确认中，请稍后查询订单状态' } }) }
function sync() { if (!selected.value) return; void page.act(async valid => { const item = selected.value!; const result = item.refund && ['processing', 'abnormal'].includes(item.refund.status) ? await syncRefund(item.refund.id) : await syncOrder(item.id); if (!valid()) return; selected.value = result; await refreshMembership(); if (valid()) notice.value = '已查询最新订单状态' }) }
function cancel() { if (!selected.value) return; void page.act(async valid => { if (!await confirmAction('取消订单', '确认关闭这笔未付款订单？') || !valid()) return; const result = await cancelOrder(selected.value!.id); if (valid()) selected.value = result }) }
function refund() {
  if (reason.value.trim().length < 5) { error.value = '请填写至少 5 个字的退款原因'; return }
  void page.act(async valid => { const result = await requestRefund(selected.value!.id, reason.value.trim()); if (valid()) { selected.value = result; refundOpen.value = false; reason.value = '' } })
}
function loadMore() { if (more.value && !id.value) void page.act(valid => load(valid, true)) }
function allOrders() { uni.redirectTo({ url: '/pages/orders/index' }) }
onReachBottom(loadMore)
</script>
<template>
  <ServicePage :title="id ? '订单详情' : '我的订单'" description="付款、会员权益和退款状态以订单记录为准。" :error="error" :loading="loading" @retry="page.refresh">
    <view v-if="notice" class="notice-strip" role="status">{{ notice }}</view>
    <template v-if="selected"><view class="service-card"><view class="service-row"><text class="service-card-title">{{ selected.plan_name }}</text><wd-tag>{{ orderStatus[selected.status] }}</wd-tag></view><text class="order-amount">{{ yuan(selected.amount_fen) }}</text><text class="service-copy">{{ selected.plan_days }} 天会员</text><text class="service-meta">订单号：{{ selected.id }}</text><text class="service-meta">创建：{{ formatDate(selected.created_at) }}</text><text v-if="selected.paid_at" class="service-meta">付款：{{ formatDate(selected.paid_at) }}</text><text v-if="['created', 'pending'].includes(selected.status)" class="service-meta">{{ payable(selected) ? '订单创建后 15 分钟内可付款' : '订单已超时，请取消或查询状态' }}</text>
      <view class="service-actions"><wd-button role="button" v-if="payable(selected)" :disabled="busy || loading || !canPay" :loading="busy" @click="pay">微信支付</wd-button><wd-button role="button" v-if="['created', 'pending'].includes(selected.status)" variant="plain" :disabled="busy || loading" @click="cancel">取消订单</wd-button><wd-button role="button" v-if="online && selected.status !== 'closed'" variant="text" :disabled="busy || loading" @click="sync">查询支付 / 退款状态</wd-button></view><text v-if="payable(selected) && !canPay" class="service-meta">当前暂不支持付款，可稍后在微信小程序查看。</text></view>
      <view v-if="selected.refund" class="service-card"><text class="service-card-title">{{ refundStatus[selected.refund.status] }}</text><text class="service-copy">退款原因：{{ selected.refund.reason }}</text><view v-if="selected.refund.reply" class="service-reply">{{ selected.refund.reply }}</view><text class="service-meta">{{ formatDate(selected.refund.updated_at) }}</text><text v-if="['closed', 'abnormal', 'rejected'].includes(selected.refund.status)" class="service-meta">需要进一步处理时，请联系客服并提供订单号。</text></view>
      <view v-else-if="selected.status === 'paid'" class="service-card"><text class="service-card-title">申请退款</text><text class="service-copy">支持申请整单原路退款，由管理员审核。退款成功后撤回本订单对应的未使用会员时长；其他购买和人工续期的时长会保留。</text><view v-if="!refundOpen" class="service-actions"><wd-button role="button" variant="plain" :disabled="busy || loading" @click="refundOpen = true">填写退款申请</wd-button></view><view v-else class="service-fields"><wd-textarea v-model="reason" :disabled="busy" :maxlength="500" placeholder="请说明退款原因（至少 5 个字）" show-word-limit /><wd-button role="button" :disabled="busy || loading" :loading="busy" @click="refund">提交退款申请</wd-button><wd-button role="button" variant="text" :disabled="busy" @click="refundOpen = false">暂不申请</wd-button></view></view>
      <view class="service-actions"><wd-button role="button" variant="text" @click="allOrders">全部订单</wd-button><wd-button role="button" variant="text" @click="openSupport('membership')">联系客服</wd-button></view>
    </template>
    <template v-else-if="!id"><button role="button" v-for="order in items" :key="order.id" class="service-card order-card" @click="openOrder(order.id)"><view class="service-row"><text class="service-card-title">{{ order.plan_name }}</text><text>{{ yuan(order.amount_fen) }}</text></view><text class="service-meta">{{ orderStatus[order.status] }}{{ order.refund ? ' · ' + refundStatus[order.refund.status] : '' }}</text><text class="service-meta">{{ formatDate(order.created_at) }} · {{ order.plan_days }} 天</text></button><view v-if="!items.length && !loading && !error" class="service-empty"><wd-empty icon="no-content" tip="暂无会员订单" /></view><view v-if="more" class="loading-line"><wd-button role="button" variant="text" :disabled="busy || loading" @click="loadMore">加载更多订单</wd-button></view></template>
  </ServicePage>
</template>
<style scoped>.order-amount { display:block;font-size:32px;color:var(--lc-primary);font-weight:650;margin-top:18px; }.order-card { display:block;width:100%;text-align:left;color:var(--lc-text);line-height:1.6; }</style>
