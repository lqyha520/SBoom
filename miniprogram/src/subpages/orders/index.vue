<script setup lang="ts">
import { navigatePage } from '../../services/page-navigation'

import { copyWithPrivacy } from '../../services/privacy'
import { ref } from 'vue'
import { onLoad, onReachBottom } from '@dcloudio/uni-app'
import ServicePage from '../components/ServicePage.vue'
import { useConsumerPage, type ConsumerTicket } from '../../services/consumer-page'
import { fetchPlans, fetchOrders, fetchOrder, cancelOrder, syncOrder, requestRefund, syncRefund, orderStatus, refundStatus, yuan, openOrder, type Order } from '../../services/growth'
import { checkout, checkoutSupport, checkoutState, settleCheckout } from '../../services/checkout'
import { confirmAction } from '../../services/navigation'
import { refreshMembership, session } from '../../services/session'
import { openSupport } from '../../services/experience'
import { formatDate } from '../../content'
const id = ref(''), items = ref<Order[]>([]), selected = ref<Order | null>(null), more = ref(false), reason = ref(''), refundOpen = ref(false), canPay = ref(false), online = ref(false), notice = ref(''), refundError = ref('')
onLoad(options => { id.value = String(options?.id || '') })
async function load(valid: ConsumerTicket, append = false) {
  if (id.value) { const result = await fetchOrder(id.value, { scope: valid }); if (valid()) { selected.value = result; settleCheckout(result) } }
  else { const result = await fetchOrders(append ? items.value.length : 0, { scope: valid }); if (valid()) { items.value = append ? [...items.value, ...result.items.filter(item => !items.value.some(old => old.id === item.id))] : result.items; more.value = result.has_more } }
  if (!append && valid()) { const plans = await fetchPlans({ scope: valid }); if (valid()) { online.value = plans.checkout_enabled; canPay.value = plans.checkout_enabled && checkoutSupport(plans.ios_enabled) && !!session.user?.has_wechat } }
}
const page = useConsumerPage(load, () => { items.value = []; selected.value = null; more.value = false; refundOpen.value = false; reason.value = ''; notice.value = ''; refundError.value = '';  canPay.value = false; online.value = false })
const { error, busy, loading } = page
function payable(order: Order) { return ['created', 'pending'].includes(order.status) && order.expires_at > Date.now() / 1000 }
function pay() { if (!selected.value || !canPay.value) return; void page.act(async valid => { const result = await checkout(selected.value!.id, valid, { scope: valid }); if (valid() && result) { selected.value = result; notice.value = result.status === 'paid' ? '付款已确认，会员权益已更新' : '付款结果仍在确认中，请稍后查询订单状态' } }) }
function sync() { if (!selected.value) return; void page.act(async valid => { const item = selected.value!; const result = item.refund && ['processing', 'abnormal'].includes(item.refund.status) ? await syncRefund(item.refund.id) : await syncOrder(item.id); if (!valid()) return; selected.value = result; settleCheckout(result); await refreshMembership({ scope: valid }); if (valid()) notice.value = '已查询最新订单状态' }) }
function cancel() { if (!selected.value) return; void page.act(async valid => { if (!await confirmAction('取消订单', '确认关闭这笔未付款订单？') || !valid()) return; const result = await cancelOrder(selected.value!.id); if (valid()) { selected.value = result; settleCheckout(result) } }) }
function refund() {
  if (reason.value.trim().length < 5) { refundError.value = '请填写至少 5 个字的退款原因'; return }
  refundError.value = ''
  void page.act(async valid => { const result = await requestRefund(selected.value!.id, reason.value.trim()); if (valid()) { selected.value = result; refundOpen.value = false; reason.value = '' } })
}
function loadMore() { if (more.value && !id.value) void page.act(valid => load(valid, true)) }
function copyOrder() { if (selected.value) copyWithPrivacy({ data: selected.value.id, fail: () => uni.showToast({ title: '复制失败，可长按订单号复制', icon: 'none' }) }) }
function allOrders() { uni.redirectTo({ url: '/subpages/orders/index' }) }
function membership() { navigatePage({ url: '/subpages/membership/index' }) }
onReachBottom(loadMore)
</script>
<template>
  <ServicePage
    :title="id ? '订单详情' : '我的订单'"
    description="付款、会员权益和退款状态以订单记录为准。"
    :error="error"
    :loading="loading"
    @retry="page.refresh"
  >
    <view v-if="notice" class="notice-strip" role="status">{{ notice }}</view>
    <template v-if="selected">
      <view class="service-card">
        <view class="service-row">
          <text class="service-card-title">{{ selected.plan_name }}</text>
          <wd-tag>{{ orderStatus[selected.status] }}</wd-tag>
        </view>
        <text class="order-amount">{{ yuan(selected.amount_fen) }}</text>
        <text class="service-copy">{{ selected.plan_days }} 天会员</text>
        <view class="order-reference">
          <text class="service-meta" selectable>订单号：{{ selected.id }}</text>
          <button
            class="section-link"
            hover-class="control-pressed"
            role="button"
            aria-label="复制订单号"
            @click="copyOrder"
          >
            <wd-icon name="copy" size="16px" />
            <text>复制</text>
          </button>
        </view>
        <text class="service-meta">创建：{{ formatDate(selected.created_at) }}</text>
        <text v-if="selected.paid_at" class="service-meta">付款：{{ formatDate(selected.paid_at) }}</text>
        <text v-if="['created', 'pending'].includes(selected.status)" class="service-meta">
          {{ payable(selected) ? '订单创建后 15 分钟内可付款' : '订单已超时，请取消或查询状态' }}
        </text>
        <text v-if="checkoutState.has(selected.id)" class="service-meta">{{ checkoutState.get(selected.id)?.phase === 'waiting' ? '尚未收到付款结果，可查询最新订单状态' : '正在确认付款结果' }}</text>
        <view class="service-actions">
          <wd-button
            role="button"
            v-if="payable(selected) && !checkoutState.has(selected.id)"
            :disabled="busy || loading || !canPay"
            :loading="busy"
            @click="pay"
          >
            微信支付
          </wd-button>
          <wd-button
            role="button"
            v-if="['created', 'pending'].includes(selected.status)"
            variant="plain"
            :disabled="busy || loading"
            @click="cancel"
          >
            取消订单
          </wd-button>
          <wd-button
            role="button"
            v-if="online && selected.status !== 'closed'"
            variant="text"
            :disabled="busy || loading"
            @click="sync"
          >
            查询支付 / 退款状态
          </wd-button>
        </view>
        <text v-if="payable(selected) && !canPay" class="service-meta">当前暂不支持付款，可稍后在微信小程序查看。</text>
      </view>
      <view v-if="selected.refund" class="service-card">
        <text class="service-card-title">{{ refundStatus[selected.refund.status] }}</text>
        <text class="service-copy">退款原因：{{ selected.refund.reason }}</text>
        <view v-if="selected.refund.reply" class="service-reply">{{ selected.refund.reply }}</view>
        <text class="service-meta">{{ formatDate(selected.refund.updated_at) }}</text>
        <text v-if="['closed', 'abnormal', 'rejected'].includes(selected.refund.status)" class="service-meta">
          需要进一步处理时，请联系客服并提供订单号。
        </text>
      </view>
      <view v-else-if="selected.status === 'paid'" class="service-card">
        <text class="service-card-title">申请退款</text>
        <text class="service-copy">
          支持申请整单原路退款，由管理员审核。退款成功后撤回本订单对应的未使用会员时长；其他购买和人工续期的时长会保留。
        </text>
        <view v-if="!refundOpen" class="service-actions">
          <wd-button role="button" variant="plain" :disabled="busy || loading" @click="refundOpen = true">
            填写退款申请
          </wd-button>
        </view>
        <view v-else class="service-fields refund-form">
          <wd-textarea
            v-model="reason"
            :disabled="busy"
            :maxlength="500"
            placeholder="请说明退款原因（至少 5 个字）"
            show-word-limit
            @update:model-value="refundError = ''"
          />
          <text v-if="refundError" class="refund-error" role="alert">{{ refundError }}</text>
          <wd-button role="button" :disabled="busy || loading" :loading="busy" @click="refund">提交退款申请</wd-button>
          <wd-button role="button" variant="text" :disabled="busy" @click="refundOpen = false">暂不申请</wd-button>
        </view>
      </view>
      <view class="service-actions">
        <wd-button role="button" variant="text" @click="allOrders">全部订单</wd-button>
        <wd-button role="button" variant="text" @click="openSupport('membership')">联系客服</wd-button>
      </view>
    </template>
    <template v-else-if="!id">
      <button
        hover-class="control-pressed"
        :hover-start-time="0"
        :hover-stay-time="80"
        role="button"
        v-for="order in items"
        :key="order.id"
        class="service-card order-card"
        @click="openOrder(order.id)"
      >
        <view class="service-row">
          <text class="service-card-title">{{ order.plan_name }}</text>
          <text class="order-price">{{ yuan(order.amount_fen) }}</text>
        </view>
        <text class="service-meta">
          {{ orderStatus[order.status] }}{{ order.refund ? ' · ' + refundStatus[order.refund.status] : '' }}
        </text>
        <view class="order-bottom">
          <text class="service-meta">{{ formatDate(order.created_at) }} · {{ order.plan_days }} 天</text>
          <wd-icon name="arrow-right" size="15px" />
        </view>
      </button>
      <view v-if="!items.length && !loading && !error" class="service-empty">
        <wd-empty icon="no-content" tip="暂无会员订单">
          <template #bottom>
            <view class="empty-actions">
              <wd-button role="button" variant="plain" @click="membership">了解会员服务</wd-button>
            </view>
          </template>
        </wd-empty>
      </view>
      <view v-if="more" class="loading-line">
        <wd-button role="button" variant="text" :disabled="busy || loading" @click="loadMore">加载更多订单</wd-button>
      </view>
    </template>
  </ServicePage>
</template>

<style scoped>.order-reference { display:flex;align-items:center;gap:12px;margin-top:8px; }.order-reference .service-meta { flex:1;min-width:0;margin-top:0; }.order-reference .section-link { flex:none;color:var(--lc-primary); }.order-price { padding-top:2px;font-size:17px;font-weight:650;white-space:nowrap; }.order-bottom { display:flex;align-items:center;justify-content:space-between;gap:10px;color:var(--lc-muted); }.refund-form { margin-top:14px; }.refund-error { color:#a34040;font-size:13px; }.order-amount { display:block;font-size:32px;color:var(--lc-primary);font-weight:650;margin-top:18px; }.order-card { display:block;width:100%;text-align:left;color:var(--lc-text);line-height:1.6; }</style>
