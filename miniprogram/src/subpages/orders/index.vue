<script setup lang="ts">
import { navigatePage } from '../../services/page-navigation'

import { copyWithPrivacy } from '../../services/privacy'
import { devicePlatform } from '../../services/platform'
import { computed, ref, watch } from 'vue'
import { onHide, onLoad, onReachBottom, onShow, onUnload } from '@dcloudio/uni-app'
import ServicePage from '../components/ServicePage.vue'
import { useConsumerPage, type ConsumerTicket } from '../../services/consumer-page'
import { errorMessage } from '../../services/api'
import { fetchPlans, fetchOrders, fetchOrder, cancelOrder, syncOrder, requestRefund, syncRefund, orderStatus, refundStatus, yuan, openOrder, type Order, type Refund } from '../../services/growth'
import { checkout, checkoutSupport, checkoutState, settleCheckout } from '../../services/checkout'
import { confirmAction } from '../../services/navigation'
import { refreshMembership, session } from '../../services/session'
import { openSupport } from '../../services/experience'
import { formatDate } from '../../content'
const id = ref(''), items = ref<Order[]>([]), selected = ref<Order | null>(null), more = ref(false), reason = ref(''), refundOpen = ref(false), canPay = ref(false), online = ref(false), notice = ref(''), refundError = ref('')
onLoad(options => { id.value = String(options?.id || '') })
const plansLoading = ref(false), plansError = ref('')
let plansRevision = 0
async function loadPlans(valid: ConsumerTicket) {
  if (!valid()) return
  const revision = ++plansRevision
  const current = () => valid() && revision === plansRevision
  plansLoading.value = true; plansError.value = ''; online.value = false; canPay.value = false
  try {
    const plans = await fetchPlans({ scope: valid })
    if (current()) { online.value = plans.checkout_enabled; canPay.value = plans.checkout_enabled && checkoutSupport(plans.ios_enabled) && !!session.user?.has_wechat }
  } catch (cause) { if (current()) plansError.value = errorMessage(cause) }
  finally { if (current()) plansLoading.value = false }
}
async function load(valid: ConsumerTicket, append = false) {
  // 配置独立加载，不占用订单列表和取消、退款操作的等待状态。
  if (!append) void loadPlans(valid)
  if (id.value) { const result = await fetchOrder(id.value, { scope: valid }); if (valid()) { selected.value = result; settleCheckout(result) } }
  else { const result = await fetchOrders(append ? items.value.length : 0, { scope: valid }); if (valid()) { items.value = append ? [...items.value, ...result.items.filter(item => !items.value.some(old => old.id === item.id))] : result.items; more.value = result.has_more } }
}
const page = useConsumerPage(load, () => { plansRevision++; plansLoading.value = false; plansError.value = ''; items.value = []; selected.value = null; more.value = false; refundOpen.value = false; reason.value = ''; notice.value = ''; refundError.value = ''; canPay.value = false; online.value = false })
const { error, busy, loading } = page
const now = ref(Date.now())
let countdown: ReturnType<typeof setInterval> | undefined
function payable(order: Order) { return ['created', 'pending'].includes(order.status) && order.expires_at > now.value / 1000 }
// 价格与道具按下单平台固化，换设备续付会被服务端拒绝；提前禁用并说明原因。
function platformConflict(order: Order) {
  const platform = devicePlatform()
  return !!platform && !!order.device_platform && platform !== order.device_platform && ['created', 'pending'].includes(order.status)
}
function platformName(platform?: string) { return platform === 'ios' ? 'iPhone' : platform === 'android' ? '安卓' : '其他设备' }
// 列表与详情共用一套状态色：绿=已完成，橙=待处理，红=异常，灰=已结束。
const orderTone: Record<Order['status'], string> = { created: 'wait', pending: 'wait', paid: 'ok', closed: 'muted', refunded: 'muted' }
const refundTone: Record<Refund['status'], string> = { requested: 'wait', processing: 'wait', success: 'ok', closed: 'muted', rejected: 'muted', abnormal: 'danger' }
// 虚拟支付要等客户端拉起收银台后微信侧才有单；created 表示还没发起过支付，查单只会得到“数据不存在”。
function syncable(order: Order) { return order.status !== 'closed' && !(order.payment_channel === 'virtual' && order.status === 'created') }
const payRemaining = computed(() => {
  const seconds = selected.value ? Math.max(0, Math.ceil(selected.value.expires_at - now.value / 1000)) : 0
  return String(Math.floor(seconds / 60)).padStart(2, '0') + ':' + String(seconds % 60).padStart(2, '0')
})
function stopCountdown() { if (countdown !== undefined) { clearInterval(countdown); countdown = undefined } }
function startCountdown() {
  stopCountdown(); now.value = Date.now()
  const order = selected.value
  if (!order || !['created', 'pending'].includes(order.status) || order.expires_at <= now.value / 1000) return
  // 到期后自动停下，页面隐藏时也不占用定时器。
  countdown = setInterval(() => { now.value = Date.now(); if (!selected.value || selected.value.expires_at <= now.value / 1000) stopCountdown() }, 1000)
}
watch([selected, () => selected.value?.status], startCountdown)
onShow(() => { now.value = Date.now(); if (selected.value) startCountdown() })
onHide(stopCountdown)
onUnload(stopCountdown)
function pay() { if (!selected.value || !canPay.value || platformConflict(selected.value)) return; void page.act(async valid => { const result = await checkout(selected.value!.id, valid, { scope: valid }); if (valid() && result) { selected.value = result; notice.value = result.status === 'paid' ? '付款已确认，会员权益已更新' : '付款结果仍在确认中，请稍后查询订单状态' } }) }
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
    gate-description="登录后查看会员订单、支付状态和退款进度"
    :error="error"
    :loading="loading"
    @retry="page.refresh"
  >
    <view v-if="notice" class="notice-strip" role="status">{{ notice }}</view>
    <view v-if="plansError" class="error-strip" role="status"><text class="grow">付款配置暂时无法加载：{{ plansError }}。订单记录和退款申请仍可使用。</text><wd-button role="button" variant="text" :loading="plansLoading" :disabled="plansLoading" @click="loadPlans(page.ticket())">重试付款配置</wd-button></view>
    <template v-if="selected">
      <view class="service-card">
        <view class="service-row">
          <text class="service-card-title">{{ selected.plan_name }}</text>
          <text class="order-status" :class="orderTone[selected.status]">{{ orderStatus[selected.status] }}</text>
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
        <text class="service-meta">支付方式：{{ selected.payment_channel === 'virtual' ? '微信小程序内支付' : '微信支付' }}</text>
        <text v-if="selected.paid_at" class="service-meta">付款：{{ formatDate(selected.paid_at) }}</text>
        <text v-if="['created', 'pending'].includes(selected.status)" class="service-meta">
          {{ payable(selected) ? '剩余支付时间 ' + payRemaining : '订单已超时，请取消或查询状态' }}
        </text>
        <text v-if="checkoutState.has(selected.id)" class="service-meta">{{ checkoutState.get(selected.id)?.phase === 'waiting' ? '尚未收到付款结果，可查询最新订单状态' : '正在确认付款结果' }}</text>
        <text v-if="platformConflict(selected)" class="service-meta">该订单在{{ platformName(selected.device_platform) }}创建，请取消后在本设备重新下单。</text>
        <view class="service-actions">
          <wd-button
            role="button"
            v-if="payable(selected) && !checkoutState.has(selected.id)"
            :disabled="busy || loading || !canPay || platformConflict(selected)"
            :loading="busy"
            @click="pay"
          >
            立即支付
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
            v-if="syncable(selected)"
            variant="text"
            :disabled="busy || loading"
            @click="sync"
          >
            查询订单状态
          </wd-button>
        </view>
        <text v-if="payable(selected) && plansLoading" class="service-meta" role="status">正在确认付款配置，仍可取消订单。</text>
        <text v-else-if="payable(selected) && !plansError && !canPay && !platformConflict(selected)" class="service-meta">{{ online ? '当前设备暂不支持在线付款，可联系客服协助开通。' : '在线付款暂未开放，可联系客服协助开通。' }}</text>
      </view>
      <view v-if="selected.refund" class="service-card">
        <text class="service-card-title" :class="'tone-' + refundTone[selected.refund.status]">{{ refundStatus[selected.refund.status] }}</text>
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
        <view class="order-status-row">
          <text class="order-status" :class="orderTone[order.status]">{{ orderStatus[order.status] }}</text>
          <text v-if="order.refund" class="order-status" :class="refundTone[order.refund.status]">{{ refundStatus[order.refund.status] }}</text>
        </view>
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
      <view v-else-if="items.length && !busy && !loading && !error" class="list-end">已显示全部订单</view>
    </template>
  </ServicePage>
</template>

<style scoped>.order-reference { display:flex;align-items:center;gap:12px;margin-top:8px; }.order-reference .service-meta { flex:1;min-width:0;margin-top:0; }.order-reference .section-link { flex:none;color:var(--lc-primary); }.order-price { padding-top:2px;font-size:17px;font-weight:650;white-space:nowrap; }.order-bottom { display:flex;align-items:center;justify-content:space-between;gap:10px;color:var(--lc-muted); }.refund-form { margin-top:14px; }.refund-error { color:#a34040;font-size:13px; }.order-amount { display:block;font-size:32px;color:var(--lc-primary);font-weight:650;margin-top:18px; }.order-card { display:block;width:100%;text-align:left;color:var(--lc-text);line-height:1.6; }
.order-status-row { display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-top:8px; }
.order-status { display:inline-flex;align-items:center;padding:2px 7px;border-radius:6px;background:#f0f3f1;color:var(--lc-secondary);font-size:12px;line-height:1.5; }
.service-row .order-status { flex:none;margin-top:3px; }
.order-status.ok { background:var(--lc-success-bg);color:var(--lc-success-text); }
.order-status.wait { background:var(--lc-warning-bg);color:var(--lc-warning); }
.order-status.danger { background:#f8e9e6;color:#a34040; }
.order-status.muted { background:#f1f3f2;color:var(--lc-muted); }
.service-card-title.tone-ok { color:var(--lc-success-text); }
.service-card-title.tone-wait { color:var(--lc-warning); }
.service-card-title.tone-danger { color:#a34040; }
.service-card-title.tone-muted { color:var(--lc-muted); }
</style>
