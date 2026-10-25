<script setup lang="ts">
import { navigatePage } from '../../services/page-navigation'

import { copyWithPrivacy } from '../../services/privacy'
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import PageChrome from '../../components/PageChrome.vue'
import AuthGate from '../../components/AuthGate.vue'
import { useConsumerPage, type ConsumerTicket } from '../../services/consumer-page'
import { fetchPlans, createOrder, requestKey, yuan, openOrder, redeemMembershipCard, type Plan } from '../../services/growth'
import { fetchSupport, openSupport, type SupportSettings } from '../../services/experience'
import { refreshMembership, session } from '../../services/session'
import { membershipExpiry } from '../../presentation'
import { checkoutSupport, iosRestricted, onIOS } from '../../services/checkout'
import { confirmAction } from '../../services/navigation'

const plans = ref<Plan[]>([])
const contact = ref<SupportSettings | null>(null)
const enabled = ref(false), iosEnabled = ref(false)
const contactOpen = ref(false), contactError = ref(false), detailsOpen = ref(false)
onLoad(options => { contactOpen.value = options?.contact === '1' })
const selectedId = ref(''), cardCode = ref('')
const action = ref<'redeem' | 'purchase' | ''>('')
const redeemedDays = ref(0)
let attempt = { plan: '', revision: 0, key: '' }
const restricted = computed(() => iosRestricted(iosEnabled.value))
const supported = computed(() => checkoutSupport(iosEnabled.value))
const ios = computed(() => onIOS())
// iPhone 只能走苹果 IAP，价格与道具都和服务端不同，未配 iOS 价的套餐不展示。
const listed = computed(() => ios.value ? plans.value.filter(plan => plan.ios_available) : plans.value)
const priceOf = (plan: Plan) => ios.value ? (plan.price_fen_ios || plan.price_fen) : plan.price_fen
const lifetime = computed(() => session.user?.is_vip && session.user.vip_expires_at === null)
const hasContact = computed(() => !!(contact.value?.wechat || contact.value?.phone || contact.value?.email || contact.value?.qr_url))
const canPurchase = computed(() => enabled.value && supported.value && !!session.user?.has_wechat && !lifetime.value)
const selectedPlan = computed(() => listed.value.find(plan => plan.id === selectedId.value))
const limitReached = (plan: Plan) => !!plan.purchase_limit && (plan.purchased || 0) >= plan.purchase_limit
// 任何套餐只要还有未付款订单就先去处理它，避免重复点击生成多笔待付款订单。
const awaitingOrder = (plan: Plan) => !limitReached(plan) && (plan.pending || 0) > 0
const pendingExpired = (plan: Plan) => awaitingOrder(plan) && !!plan.pending_expires_at && plan.pending_expires_at * 1000 <= Date.now()
function planLimitLabel(plan: Plan) {
  if (limitReached(plan)) return '已达限购'
  if (awaitingOrder(plan)) return pendingExpired(plan) ? '订单已超时' : '有待付款订单'
  if (!plan.purchase_limit) return ''
  return (plan.purchased || 0) > 0 ? '已购 ' + plan.purchased + '/' + plan.purchase_limit : '限购 ' + plan.purchase_limit + ' 次'
}
const unavailable = (plan: Plan) => limitReached(plan) || awaitingOrder(plan)
const allBlocked = computed(() => listed.value.length > 0 && listed.value.every(unavailable))
const allLimited = computed(() => listed.value.length > 0 && listed.value.every(limitReached))
const awaitingPlan = computed(() => listed.value.find(awaitingOrder))
const canBuySelected = computed(() => canPurchase.value && !!selectedPlan.value && !unavailable(selectedPlan.value))
const primaryLabel = computed(() => lifetime.value ? '去挑选习题' : canBuySelected.value
  ? (session.user?.is_vip ? '确认续费' : '确认开通') : awaitingPlan.value ? '查看待付款订单' : ios.value ? '联系客服' : '咨询开通')

async function load(valid: ConsumerTicket) {
  action.value = ''
  const [catalog, support, membership] = await Promise.allSettled([fetchPlans({ scope: valid }), fetchSupport({ scope: valid }), refreshMembership({ scope: valid })])
  if (!valid()) return
  if (support.status === 'fulfilled') { contact.value = support.value; contactError.value = false }
  else { contact.value = null; contactError.value = true }
  if (catalog.status === 'fulfilled') {
    plans.value = catalog.value.items; enabled.value = catalog.value.checkout_enabled; iosEnabled.value = catalog.value.ios_enabled
    if (!listed.value.some(plan => plan.id === selectedId.value && !unavailable(plan))) selectedId.value = listed.value.find(plan => !unavailable(plan))?.id || ''
  } else throw catalog.reason
  if (membership.status === 'rejected') throw membership.reason
}
const page = useConsumerPage(load, () => {
  plans.value = []; contact.value = null; enabled.value = false; iosEnabled.value = false
  contactOpen.value = false; contactError.value = false; detailsOpen.value = false
  selectedId.value = ''; cardCode.value = ''; redeemedDays.value = 0; action.value = ''
  attempt = { plan: '', revision: 0, key: '' }
})
const { error, busy, loading } = page

function selectPlan(plan: Plan) {
  if (busy.value || loading.value || lifetime.value || limitReached(plan)) return
  if (awaitingOrder(plan)) {
    if (plan.pending_order) openOrder(plan.pending_order)
    else orders()
    return
  }
  selectedId.value = plan.id; action.value = ''; error.value = ''
}
function purchase(plan: Plan) {
  if (!canPurchase.value || unavailable(plan)) return
  action.value = 'purchase'
  let needsReload = false
  void page.act(async valid => {
    if (!await confirmAction('确认会员套餐', plan.name + '：' + plan.days + ' 天，' + yuan(priceOf(plan)) + '。确认后生成订单，在订单页完成付款。') || !valid()) return
    if (attempt.plan !== plan.id || attempt.revision !== plan.revision) attempt = { plan: plan.id, revision: plan.revision, key: requestKey() }
    try {
      const order = await createOrder(plan, attempt.key)
      if (valid()) { attempt = { plan: '', revision: 0, key: '' }; openOrder(order.id) }
    } catch (cause) {
      // 另一台设备刚创建了订单、或 iPhone 端刚被下架等情况：刷新套餐列表再提示。
      needsReload = ['purchase_limit', 'ios_unavailable'].includes((cause as { code?: string })?.code || '')
      throw cause
    }
  }).then(() => { if (needsReload) void page.refresh() })
}
function primary() {
  if (restricted.value) return
  if (busy.value || loading.value) return
  if (lifetime.value) { uni.switchTab({ url: '/pages/library/index' }); return }
  if (canBuySelected.value && selectedPlan.value) purchase(selectedPlan.value)
  else if (awaitingPlan.value?.pending_order) openOrder(awaitingPlan.value.pending_order)
  else if (awaitingPlan.value) orders()
  else contactOpen.value = true
}
function orders() { navigatePage({ url: '/subpages/orders/index' }) }
function copyContact(value: string) {
  copyWithPrivacy({
    data: value,
    success: () => uni.showToast({ title: '已复制，可粘贴使用', icon: 'none' }),
    fail: () => uni.showToast({ title: '复制失败，可长按号码复制', icon: 'none' }),
  })
}
function callContact() {
  if (!contact.value?.phone) return
  uni.makePhoneCall({ phoneNumber: contact.value.phone, fail: cause => {
    if (!cause.errMsg?.includes('cancel')) uni.showToast({ title: '拨号未完成，可长按复制号码', icon: 'none' })
  } })
}
function previewQr() { if (contact.value?.qr_url) uni.previewImage({ urls: [contact.value.qr_url], current: 0 }) }
function leaveMessage() { contactOpen.value = false; openSupport('membership') }
function redeem() {
  if (restricted.value) return
  const code = cardCode.value.trim()
  if (!code || lifetime.value || busy.value || loading.value) return
  action.value = 'redeem'; redeemedDays.value = 0
  if (code.length < 8) { error.value = '卡密至少需要 8 位，请检查后再试'; return }
  void page.act(async valid => {
    const result = await redeemMembershipCard(code)
    if (!valid()) return
    cardCode.value = ''; session.user = result.user; redeemedDays.value = result.days
    uni.showToast({ title: '兑换成功，会员已生效', icon: 'none' })
  })
}
</script>

<template>
  <view class="membership-page">
    <PageChrome back fallback="/pages/account/index" />
    <view class="content-width member-heading"><text>会员服务</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="order-link" role="button" aria-label="查看会员订单" @click="orders"><wd-icon name="file" size="15px" /><text>会员订单</text><wd-icon name="arrow-right" size="12px" /></button></view>
    <view class="content-width">
      <view class="member-card">
        <view class="member-card-top">
          <view class="grow"><text class="member-title">{{ session.user?.is_vip ? 'VIP 会员' : '解锁更多好资料' }}</text><text class="member-status">{{ session.user?.is_vip || session.user?.membership_status === 'expired' ? membershipExpiry(session.user) : '按需开通，让学习更从容' }}</text></view>
          <view class="member-mark"><wd-icon name="star-fill" size="25px" /></view>
        </view>
        <view class="benefit-grid"><view><wd-icon name="book" size="16px" /><text>专享资料</text></view><view><wd-icon name="image" size="16px" /><text>完整原稿</text></view><view><wd-icon name="file-pdf" size="16px" /><text>PDF 下载</text></view></view>
      </view>
    </view>
    <view v-if="!session.user" class="content-width guest-member-info"><text class="section-title">会员可以做什么</text><text>会员有效期内，可按资料标注查看 VIP 专享原稿，下载可用文件。</text><text>免费资料登录后即可按标注权限使用，是否含答案以每份资料的说明为准。</text></view>
    <AuthGate v-if="!session.user" title="登录查看会员服务" @restored="page.refresh" />
    <template v-else>
      <view class="content-width member-body">
        <view v-if="error && action !== 'redeem'" class="error-strip" role="alert"><text class="grow">{{ error }}</text><wd-button role="button" aria-label="重新加载会员信息" variant="text" icon="refresh" type="danger" @click="page.refresh" /></view>
        <view v-if="loading" class="loading-line"><wd-loading /><text>正在加载会员信息</text></view>

        <view v-if="restricted && !lifetime" class="restricted-notice">
          <view class="restricted-icon"><wd-icon name="info-circle-fill" size="18px" /></view>
          <view class="grow"><text class="restricted-title">当前平台暂不支持开通</text><text class="restricted-copy">已有会员权益可正常使用；对会员有任何疑问，可以联系客服。</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="restricted-action" role="button" aria-label="联系客服" @click="contactOpen = true"><wd-icon name="headset" size="14px" /><text>联系客服</text></button></view>
        </view>

        <view v-if="!lifetime && !restricted" class="plans-section">
          <view class="section-heading"><text class="section-title">选择会员时长</text><text class="section-note">权益相同，按需选择</text></view>
          <view v-if="listed.length" class="plan-grid" :class="{ single: listed.length === 1, two: listed.length === 2 }" aria-role="radiogroup" role="radiogroup" aria-label="会员套餐">
            <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-for="plan in listed" :key="plan.id" class="plan-card" :class="{ selected: selectedId === plan.id, limited: limitReached(plan), awaiting: awaitingOrder(plan) }" role="radio" :aria-label="plan.name + '，' + plan.days + '天，' + yuan(priceOf(plan)) + (limitReached(plan) ? '，已达限购' : awaitingOrder(plan) ? (pendingExpired(plan) ? '，订单已超时' : '，有待付款订单') : plan.purchase_limit ? '，每账号限购' + plan.purchase_limit + '次' : '')" :aria-checked="selectedId === plan.id" :disabled="busy || loading || limitReached(plan)" @click="selectPlan(plan)">
              <text class="plan-name">{{ plan.name }}</text><text class="plan-price">{{ yuan(priceOf(plan)) }}</text><text class="plan-duration">{{ plan.days }} 天会员</text>
              <text v-if="planLimitLabel(plan)" class="plan-limit">{{ planLimitLabel(plan) }}</text>
              <view v-if="selectedId === plan.id" class="plan-check"><wd-icon name="check" size="11px" /></view>
            </button>
          </view>
          <view v-else-if="!loading" class="plans-empty"><text>{{ ios ? 'iPhone 端暂时没有可开通的套餐，可以联系客服了解后续安排。' : '暂时没有可选套餐，可通过下方「咨询开通」了解开通方式。' }}</text></view>
          <text v-if="selectedPlan?.description" class="plan-description">{{ selectedPlan.description }}</text>
          <text v-if="listed.length" class="plan-tip">{{ allBlocked ? (allLimited ? '可选套餐均已达到限购次数，如需再次开通请联系客服。' : '你还有待付款订单，请先完成或取消后再购买。') : canPurchase ? '有效期自动顺延，无自动续费。确认后在订单页付款。' : '套餐价格供参考，可联系客服了解开通方式。' }}</text>
        </view>

        <view v-if="!restricted" class="redeem-panel">
          <view class="redeem-heading"><view class="redeem-icon"><wd-icon name="safe" size="19px" /></view><view class="grow"><text class="section-title">{{ lifetime ? '会员权益长期有效' : '有卡密？直接兑换' }}</text><text class="redeem-caption">{{ lifetime ? '无需重复开通，随时挑选喜欢的习题。' : '兑换即生效，已有会员有效期自动顺延' }}</text></view></view>
          <template v-if="!lifetime && !restricted">
            <view class="redeem-box"><input v-model="cardCode" maxlength="64" placeholder="输入会员卡密" aria-label="会员卡密" :disabled="busy || loading" confirm-type="done" @confirm="redeem" /><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" aria-label="兑换会员卡密" :disabled="busy || loading || !cardCode.trim()" @click="redeem">{{ busy && action === 'redeem' ? '兑换中…' : '兑换' }}</button></view>
            <view v-if="error && action === 'redeem'" class="redeem-error" role="alert">{{ error }}</view>
          </template>
          <view v-if="redeemedDays" class="redeem-success" role="status"><wd-icon name="check-circle" size="18px" /><view><text>兑换成功，已增加 {{ redeemedDays }} 天会员</text><text>{{ membershipExpiry(session.user) }}</text></view></view>
        </view>

        <view class="member-details">
          <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="details-toggle" role="button" :aria-expanded="detailsOpen" @click="detailsOpen = !detailsOpen"><text>会员权益与说明</text><wd-icon :name="detailsOpen ? 'arrow-up' : 'arrow-down'" size="15px" /></button>
          <view v-if="detailsOpen" class="details-content"><text>会员有效期内，可查看 VIP 专享资料的完整原稿，并下载可用文件。是否含答案以资料标注为准。</text><text>续期会从当前到期日顺延；会员已到期时，从开通成功时重新计算。</text><text v-if="contact?.benefits && !restricted">{{ contact.benefits }}</text></view>
        </view>
      </view>

      <view v-if="!restricted" class="member-footer">
        <view class="footer-inner"><button v-if="canPurchase || lifetime" hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="footer-contact" role="button" aria-label="联系客服" @click="contactOpen = true"><wd-icon name="headset" size="22px" /><text>客服</text></button><view class="footer-main"><text v-if="selectedPlan && !lifetime" class="footer-summary">{{ selectedPlan.name }} · {{ selectedPlan.days }} 天 · {{ yuan(priceOf(selectedPlan)) }}</text><wd-button role="button" block :loading="busy && action === 'purchase'" :disabled="busy || loading" @click="primary">{{ primaryLabel }}</wd-button></view></view>
      </view>
    </template>

    <wd-popup v-model="contactOpen" position="bottom" :z-index="1250" root-portal safe-area-inset-bottom custom-style="border-radius:22px 22px 0 0">
      <view class="sheet contact-sheet" aria-role="dialog" role="dialog" aria-modal="true" aria-label="会员客服">
        <view class="sheet-handle" />
        <view class="sheet-head"><view><text class="sheet-title">联系客服</text><text class="contact-sheet-intro">{{ ios ? '兑换、使用或其他问题，都可以问我们' : '开通、兑换或使用问题，都可以问我们' }}</text></view><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="bare-icon" role="button" aria-label="关闭会员客服" @click="contactOpen = false"><wd-icon name="close" size="20px" /></button></view>
        <text v-if="contact?.hours" class="contact-hours"><wd-icon name="time-line" size="14px" /> 服务时间：{{ contact.hours }}</text>
        <view v-if="contactError" class="contact-empty"><text>联系方式暂时没加载成功，可以重试或留言咨询。</text><wd-button role="button" size="small" variant="text" :loading="loading" @click="page.refresh">重新加载</wd-button></view>
        <text v-else-if="!hasContact" class="contact-empty">可以先留下你的问题，我们会在「服务反馈」中回复。</text>
        <view v-if="contact?.wechat" class="contact-row"><view class="contact-row-icon"><wd-icon name="message" size="20px" /></view><view class="grow"><text class="contact-label">客服微信</text><text class="contact-value" selectable>{{ contact.wechat }}</text></view><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" aria-label="复制客服微信" @click="copyContact(contact.wechat)">复制</button></view>
        <view v-if="contact?.phone" class="contact-row"><view class="contact-row-icon"><wd-icon name="phone" size="20px" /></view><view class="grow"><text class="contact-label">联系电话</text><text class="contact-value" selectable>{{ contact.phone }}</text></view><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" aria-label="拨打客服电话" @click="callContact">拨打</button></view>
        <view v-if="contact?.email" class="contact-row"><view class="contact-row-icon"><wd-icon name="email" size="20px" /></view><view class="grow"><text class="contact-label">联系邮箱</text><text class="contact-value" selectable>{{ contact.email }}</text></view><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" aria-label="复制客服邮箱" @click="copyContact(contact.email)">复制</button></view>
        <view v-if="contact?.qr_url" class="contact-qr-block"><image class="contact-qr" :src="contact.qr_url" mode="aspectFit" show-menu-by-longpress @click="previewQr" /><text>点击放大，长按识别客服二维码</text></view>
        <view class="contact-message"><wd-button role="button" block type="info" variant="plain" @click="leaveMessage">留言咨询</wd-button><text>问题和回复可在「服务反馈」中查看</text></view>
      </view>
    </wd-popup>
  </view>
</template>

<style scoped>
.guest-member-info { padding-top:20px; }.guest-member-info > text { display:block;margin-top:10px;font-size:14px;line-height:1.8;color:var(--lc-secondary); }.guest-member-info .section-title { color:var(--lc-text);font-size:17px; }
.membership-page { width:100%;max-width:520px;min-height:100vh;margin:0 auto;padding-bottom:calc(122px + env(safe-area-inset-bottom));background:linear-gradient(180deg,#eaf3ed 0,#f7f9f8 330px); }
.member-heading { display:flex;align-items:center;justify-content:space-between;gap:12px;padding-top:2px;padding-bottom:16px; }
.member-heading > text { font-size:24px;font-weight:700;color:var(--lc-text);line-height:1.5; }
.order-link { display:flex;align-items:center;gap:5px;min-height:40px;margin:0;padding:6px 0;background:transparent;color:var(--lc-secondary);font-size:12px;line-height:1.5; }
.member-card { position:relative;overflow:hidden;padding:20px;border-radius:20px;color:#fff;background:radial-gradient(ellipse at 108% 0,#578465 0,transparent 64%),#264e3b;box-shadow:0 10px 24px #29473818; }
.member-card-top { display:flex;align-items:center;gap:16px; }
.member-title { display:block;font-size:22px;font-weight:650;line-height:1.4; }.member-status { display:block;margin-top:6px;font-size:12px;line-height:1.5;color:#d9e6db; }
.member-mark { display:flex;align-items:center;justify-content:center;width:48px;height:48px;flex:none;border:1px solid #d8bb784a;border-radius:16px;color:#f3d499;background:#f9dca216; }
.benefit-grid { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-top:20px;padding-top:15px;border-top:1px solid #ffffff26; }
.benefit-grid > view { display:flex;align-items:center;justify-content:center;gap:5px;min-width:0;color:#eff3e9;font-size: 12px;white-space:nowrap; }.benefit-grid :deep(.wd-icon) { color:#ddca97; }
.member-body { padding-top:16px; }
.restricted-notice { display:flex;align-items:flex-start;gap:11px;margin-top:8px;padding:14px 15px;border:1px solid #eadfc4;border-radius:14px;background:#fdf8ec; }
.restricted-icon { display:flex;align-items:center;justify-content:center;width:34px;height:34px;flex:none;border-radius:11px;background:#f4e9d1;color:#977947; }
.restricted-title { display:block;color:var(--lc-text);font-size:13px;font-weight:600;line-height:1.5; }
.restricted-copy { display:block;margin-top:3px;color:var(--lc-secondary);font-size:12px;line-height:1.6; }
.restricted-action { display:inline-flex;align-items:center;justify-content:center;gap:5px;min-height:36px;margin:10px 0 0;padding:6px 13px;border-radius:999px;background:var(--lc-primary-soft);color:var(--lc-primary);font-size:12px;line-height:1.5; }
.plans-section { margin-top:8px; }.section-heading { margin:0 0 12px; }.section-title { display:block;margin:0;color:var(--lc-text);font-size:16px;font-weight:650;line-height:1.5; }.section-note { color:var(--lc-muted);font-size: 12px; }
.plan-grid { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px; }.plan-grid.two { grid-template-columns:repeat(2,minmax(0,1fr)); }.plan-grid.single { grid-template-columns:1fr; }
.plan-card { position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;min-width:0;width:100%;margin:0;padding:17px 6px 16px;border:1.5px solid #e3e8e3;border-radius:14px;background:#fff;text-align:center;line-height:1.5;transition:border-color .15s,background-color .15s; }
.plan-card.selected { border-color:var(--lc-primary);background:#edf6ef; }.plan-card:active { opacity:.85; }.plan-card[disabled] { opacity:.7; }.plan-card.awaiting { border-color:#e5d6b0;background:#fdfaf1; }.plan-card.awaiting .plan-limit { color:var(--lc-warning); }
.plan-name { display:block;color:var(--lc-text);font-size:12px;font-weight:600;overflow-wrap:anywhere; }.plan-price { display:block;margin-top:8px;color:#2b694c;font-size:24px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.4;white-space:nowrap; }.plan-duration { display:block;margin-top:5px;color:var(--lc-secondary);font-size: 12px; }.plan-limit { display:block;margin-top:4px;color:var(--lc-muted);font-size:11px;line-height:1.5; }
.plan-check { position:absolute;top:-1px;right:-1px;display:flex;align-items:center;justify-content:center;width:21px;height:19px;border-radius:0 13px 0 10px;background:var(--lc-primary);color:#fff; }
.single .plan-card { display:grid;grid-template-columns:1fr auto;justify-items:start;padding:15px 20px;text-align:left; }.single .plan-price { grid-column:2;grid-row:1/3;margin:0 8px 0 10px; }.single .plan-duration { grid-column:1; }
.plan-description { display:block;margin-top:10px;color:var(--lc-secondary);font-size:12px;line-height:1.7;overflow-wrap:anywhere; }.plan-tip { display:block;margin-top:9px;color:var(--lc-muted);font-size: 12px;line-height:1.7; }
.plans-empty { padding:19px;border:1px dashed #d9e3db;border-radius:14px;text-align:center;color:var(--lc-secondary);font-size:13px; }.plans-empty button { display:flex;align-items:center;justify-content:center;gap:4px;margin:3px 0 0;padding:6px;background:transparent;color:var(--lc-primary);font-size:12px; }
.redeem-panel { margin-top:20px;padding:17px;border:1px solid var(--lc-card-line);border-radius:16px;background:#fff; }.redeem-heading { display:flex;align-items:center;gap:10px; }.redeem-icon { display:flex;align-items:center;justify-content:center;width:36px;height:36px;border-radius:11px;background:#f4f0e6;color:#977947; }.redeem-caption { display:block;margin-top:3px;color:var(--lc-muted);font-size: 12px;line-height:1.6; }
.redeem-box { display:flex;align-items:center;gap:8px;margin-top:14px;padding:5px 5px 5px 12px;border:1px solid #e0e8e1;border-radius:10px;background:#f6f9f6; }.redeem-box:focus-within { border-color:var(--lc-primary); }
.redeem-box input { flex:1;min-width:0;height:38px;color:var(--lc-text);font-size:13px; }.redeem-box button { display:flex;align-items:center;justify-content:center;min-width:65px;min-height:38px;margin:0;padding:6px 12px;border-radius:7px;background:var(--lc-primary);color:#fff;font-size:13px;line-height:1.5; }.redeem-box button[disabled] { color:#7f9688;background:#e5ece6; }
.redeem-error { margin-top:9px;color:#a34040;font-size:12px;line-height:1.7; }.redeem-success { display:flex;align-items:flex-start;gap:8px;margin-top:12px;padding:11px;border-radius:9px;color:var(--lc-primary);background:var(--lc-primary-soft);font-size:12px;line-height:1.6; }.redeem-success text { display:block; }.redeem-success text+text { margin-top:3px;font-size: 12px; }
.member-details { margin-top:14px; }.details-toggle { display:flex;align-items:center;justify-content:space-between;width:100%;min-height:48px;margin:0;padding:8px 2px;background:transparent;color:var(--lc-secondary);font-size:12px; }.details-content { padding:0 2px 10px;font-size:12px;color:var(--lc-secondary);line-height:1.9; }.details-content > text { display:block;margin-bottom:8px;white-space:pre-wrap;overflow-wrap:anywhere; }.details-content button { display:flex;align-items:center;gap:4px;margin:0;padding:8px 0;background:transparent;color:var(--lc-primary);font-size:12px; }
.member-footer { position:fixed;z-index:20;right:0;bottom:0;left:0;max-width:520px;margin:0 auto;padding-bottom:env(safe-area-inset-bottom);border-top:1px solid #e8eee8;background:#fffffffa;box-shadow:0 -4px 16px #27443005; }.footer-inner { display:flex;align-items:center;gap:20px;padding:10px 22px 14px; }.footer-contact { display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;min-width:48px;min-height:50px;margin:0;padding:0;background:transparent;color:var(--lc-primary);font-size: 12px;line-height:1.5; }.footer-main { flex:1;min-width:0; }.footer-summary { display:block;margin-bottom:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:center;color:var(--lc-secondary);font-size: 12px; }.footer-main :deep(.wd-button) { --wot-button-height-medium:44px; }
.contact-sheet { max-height:88vh;overflow-y:auto; }.contact-sheet-intro { display:block;margin-top:5px;color:var(--lc-muted);font-size:12px; }.contact-hours { display:block;margin-bottom:14px;color:var(--lc-secondary);font-size:12px; }.contact-empty { display:block;padding:12px 0 18px;font-size:13px;line-height:1.8;color:var(--lc-secondary); }
.contact-row { display:flex;align-items:center;gap:11px;padding:14px 0;border-bottom:1px solid var(--lc-border); }.contact-row-icon { display:flex;align-items:center;justify-content:center;width:37px;height:37px;flex:none;border-radius:12px;background:var(--lc-primary-soft);color:var(--lc-primary); }.contact-label { display:block;color:var(--lc-text);font-size:13px;font-weight:600; }.contact-value { display:block;margin-top:3px;font-size:12px;line-height:1.5;color:var(--lc-secondary);overflow-wrap:anywhere; }.contact-row button { flex:none;min-width:54px;min-height:38px;margin:0;padding:6px 10px;border-radius:999px;background:var(--lc-primary-soft);color:var(--lc-primary);font-size:12px;line-height:1.5; }
.contact-qr-block { display:flex;flex-direction:column;align-items:center;gap:10px;padding:20px 0 6px;color:var(--lc-muted);font-size: 12px; }.contact-qr { width:144px;height:144px;border:1px solid var(--lc-card-line);border-radius:12px;background:#fff; }.contact-message { margin-top:22px; }.contact-message > text { display:block;margin-top:10px;text-align:center;font-size: 12px;color:var(--lc-muted); }
@media (max-width:359px) { .content-width { padding-right:16px;padding-left:16px; }.member-card { padding:18px 16px; }.member-title { font-size:20px; }.plan-grid { gap:6px; }.plan-price { font-size:21px; }.section-note { font-size: 12px; }.redeem-panel { padding:14px; } }
</style>
