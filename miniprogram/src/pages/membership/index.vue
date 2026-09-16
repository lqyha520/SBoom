<script setup lang="ts">
import { computed, ref } from 'vue'
import PageChrome from '../../components/PageChrome.vue'
import AuthGate from '../../components/AuthGate.vue'
import { useConsumerPage } from '../../services/consumer-page'
import { fetchPlans, createOrder, requestKey, yuan, openOrder, redeemMembershipCard, type Plan } from '../../services/growth'
import { fetchSupport, openSupport, type SupportSettings } from '../../services/experience'
import { refreshMembership, session } from '../../services/session'
import { membershipExpiry } from '../../presentation'
import { checkoutSupport } from '../../services/checkout'
import { confirmAction } from '../../services/navigation'

const plans = ref<Plan[]>([])
const contact = ref<SupportSettings | null>(null)
const enabled = ref(false), iosEnabled = ref(false)
const contactOpen = ref(false), contactError = ref(false), detailsOpen = ref(false)
const selectedId = ref(''), cardCode = ref('')
const action = ref<'redeem' | 'purchase' | ''>('')
const redeemedDays = ref(0)
let attempt = { plan: '', revision: 0, key: '' }
const supported = computed(() => checkoutSupport(iosEnabled.value))
const lifetime = computed(() => session.user?.is_vip && session.user.vip_expires_at === null)
const hasContact = computed(() => !!(contact.value?.wechat || contact.value?.phone || contact.value?.email || contact.value?.qr_url))
const canPurchase = computed(() => enabled.value && supported.value && !!session.user?.has_wechat && !lifetime.value)
const selectedPlan = computed(() => plans.value.find(plan => plan.id === selectedId.value))
const primaryLabel = computed(() => lifetime.value ? '去挑选习题' : canPurchase.value && selectedPlan.value
  ? (session.user?.is_vip ? '确认续费' : '确认开通') : '咨询开通')

async function load(valid: () => boolean) {
  action.value = ''
  const [catalog, support, membership] = await Promise.allSettled([fetchPlans(), fetchSupport(), refreshMembership()])
  if (!valid()) return
  if (support.status === 'fulfilled') { contact.value = support.value; contactError.value = false }
  else { contact.value = null; contactError.value = true }
  if (catalog.status === 'fulfilled') {
    plans.value = catalog.value.items; enabled.value = catalog.value.checkout_enabled; iosEnabled.value = catalog.value.ios_enabled
    if (!plans.value.some(plan => plan.id === selectedId.value)) selectedId.value = plans.value[0]?.id || ''
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
  if (busy.value || loading.value || lifetime.value) return
  selectedId.value = plan.id; action.value = ''; error.value = ''
}
function purchase(plan: Plan) {
  if (!canPurchase.value) return
  action.value = 'purchase'
  void page.act(async valid => {
    if (!await confirmAction('确认会员套餐', plan.name + '：' + plan.days + ' 天，' + yuan(plan.price_fen) + '。确认后生成订单，在订单页完成微信支付。') || !valid()) return
    if (attempt.plan !== plan.id || attempt.revision !== plan.revision) attempt = { plan: plan.id, revision: plan.revision, key: requestKey() }
    const order = await createOrder(plan, attempt.key)
    if (valid()) { attempt = { plan: '', revision: 0, key: '' }; openOrder(order.id) }
  })
}
function primary() {
  if (busy.value || loading.value) return
  if (lifetime.value) { uni.switchTab({ url: '/pages/library/index' }); return }
  if (canPurchase.value && selectedPlan.value) purchase(selectedPlan.value)
  else contactOpen.value = true
}
function orders() { uni.navigateTo({ url: '/pages/orders/index' }) }
function copyContact(value: string) {
  uni.setClipboardData({
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
    <view class="content-width member-heading"><text>会员服务</text><button class="order-link" role="button" aria-label="查看会员订单" @click="orders"><wd-icon name="file" size="15px" /><text>会员订单</text><wd-icon name="arrow-right" size="12px" /></button></view>
    <view class="content-width">
      <view class="member-card">
        <view class="member-card-top">
          <view class="grow"><text class="member-title">{{ session.user?.is_vip ? 'VIP 会员' : '解锁更多好资料' }}</text><text class="member-status">{{ session.user?.is_vip || session.user?.membership_status === 'expired' ? membershipExpiry(session.user) : '按需开通，让学习更从容' }}</text></view>
          <view class="member-mark"><wd-icon name="star-fill" size="25px" /></view>
        </view>
        <view class="benefit-grid"><view><wd-icon name="book" size="16px" /><text>专享资料</text></view><view><wd-icon name="image" size="16px" /><text>完整原稿</text></view><view><wd-icon name="file-pdf" size="16px" /><text>PDF 下载</text></view></view>
      </view>
    </view>
    <AuthGate v-if="!session.user" />
    <template v-else>
      <view class="content-width member-body">
        <button class="contact-entry" role="button" aria-label="联系客服咨询会员" @click="contactOpen = true">
          <view class="contact-icon"><wd-icon name="headset" size="24px" /></view>
          <view class="grow"><text class="contact-title">联系客服</text><text class="contact-subtitle">开通咨询 · 卡密帮助 · 售后服务</text></view>
          <view class="contact-cta"><text>咨询</text><wd-icon name="arrow-right" size="12px" /></view>
        </button>
        <view v-if="error && action !== 'redeem'" class="error-strip" role="alert"><text class="grow">{{ error }}</text><wd-button role="button" aria-label="重新加载会员信息" variant="text" icon="refresh" type="danger" @click="page.refresh" /></view>
        <view v-if="loading" class="loading-line"><wd-loading /><text>正在加载会员信息</text></view>

        <view v-if="!lifetime" class="plans-section">
          <view class="section-heading"><text class="section-title">选择会员时长</text><text class="section-note">权益相同，按需选择</text></view>
          <view v-if="plans.length" class="plan-grid" :class="{ single: plans.length === 1, two: plans.length === 2 }" role="radiogroup" aria-label="会员套餐">
            <button v-for="plan in plans" :key="plan.id" class="plan-card" :class="{ selected: selectedId === plan.id }" role="radio" :aria-label="plan.name + '，' + plan.days + '天，' + yuan(plan.price_fen)" :aria-checked="selectedId === plan.id" :disabled="busy || loading" @click="selectPlan(plan)">
              <text class="plan-name">{{ plan.name }}</text><text class="plan-price">{{ yuan(plan.price_fen) }}</text><text class="plan-duration">{{ plan.days }} 天会员</text>
              <view v-if="selectedId === plan.id" class="plan-check"><wd-icon name="check" size="11px" /></view>
            </button>
          </view>
          <view v-else-if="!loading" class="plans-empty"><text>暂时没有可选套餐</text><button role="button" @click="contactOpen = true">咨询开通方式<wd-icon name="arrow-right" size="12px" /></button></view>
          <text v-if="selectedPlan?.description" class="plan-description">{{ selectedPlan.description }}</text>
          <text v-if="plans.length" class="plan-tip">{{ canPurchase ? '有效期自动顺延，无自动续费。确认后在订单页付款。' : '套餐价格供参考，可联系客服了解开通方式。' }}</text>
        </view>

        <view class="redeem-panel">
          <view class="redeem-heading"><view class="redeem-icon"><wd-icon name="safe" size="19px" /></view><view class="grow"><text class="section-title">{{ lifetime ? '会员权益长期有效' : '有卡密？直接兑换' }}</text><text class="redeem-caption">{{ lifetime ? '无需重复开通，随时挑选喜欢的习题。' : '兑换即生效，已有会员有效期自动顺延' }}</text></view></view>
          <template v-if="!lifetime">
            <view class="redeem-box"><input v-model="cardCode" maxlength="64" placeholder="输入会员卡密" aria-label="会员卡密" :disabled="busy || loading" confirm-type="done" @confirm="redeem" /><button role="button" aria-label="兑换会员卡密" :disabled="busy || loading || !cardCode.trim()" @click="redeem">{{ busy && action === 'redeem' ? '兑换中…' : '兑换' }}</button></view>
            <view v-if="error && action === 'redeem'" class="redeem-error" role="alert">{{ error }}</view>
          </template>
          <view v-if="redeemedDays" class="redeem-success" role="status"><wd-icon name="check-circle" size="18px" /><view><text>兑换成功，已增加 {{ redeemedDays }} 天会员</text><text>{{ membershipExpiry(session.user) }}</text></view></view>
        </view>

        <view class="member-details">
          <button class="details-toggle" role="button" :aria-expanded="detailsOpen" @click="detailsOpen = !detailsOpen"><text>会员权益与说明</text><wd-icon :name="detailsOpen ? 'arrow-up' : 'arrow-down'" size="15px" /></button>
          <view v-if="detailsOpen" class="details-content"><text>会员有效期内，可查看 VIP 专享资料的完整原稿，并下载可用的 PDF 文件。</text><text>续期会从当前到期日顺延；会员已到期时，从开通成功时重新计算。</text><text v-if="contact?.benefits">{{ contact.benefits }}</text><button role="button" @click="contactOpen = true">还有疑问？联系客服<wd-icon name="arrow-right" size="12px" /></button></view>
        </view>
      </view>

      <view class="member-footer">
        <view class="footer-inner"><button class="footer-contact" role="button" aria-label="联系客服" @click="contactOpen = true"><wd-icon name="headset" size="22px" /><text>客服</text></button><view class="footer-main"><text v-if="selectedPlan && !lifetime" class="footer-summary">{{ selectedPlan.name }} · {{ selectedPlan.days }} 天 · {{ yuan(selectedPlan.price_fen) }}</text><wd-button role="button" block :loading="busy && action === 'purchase'" :disabled="busy || loading" @click="primary">{{ primaryLabel }}</wd-button></view></view>
      </view>
    </template>

    <wd-popup v-model="contactOpen" position="bottom" :z-index="1250" root-portal safe-area-inset-bottom custom-style="border-radius:24px 24px 0 0">
      <view class="sheet contact-sheet" role="dialog" aria-modal="true" aria-label="会员客服">
        <view class="sheet-handle" />
        <view class="sheet-head"><view><text class="sheet-title">联系客服</text><text class="contact-sheet-intro">开通、兑换或使用问题，都可以问我们</text></view><button class="bare-icon" role="button" aria-label="关闭会员客服" @click="contactOpen = false"><wd-icon name="close" size="20px" /></button></view>
        <text v-if="contact?.hours" class="contact-hours"><wd-icon name="time-line" size="14px" /> 服务时间：{{ contact.hours }}</text>
        <view v-if="contactError" class="contact-empty"><text>联系方式暂时没加载成功，可以重试或留言咨询。</text><wd-button role="button" size="small" variant="text" :loading="loading" @click="page.refresh">重新加载</wd-button></view>
        <text v-else-if="!hasContact" class="contact-empty">可以先留下你的问题，我们会在「服务反馈」中回复。</text>
        <view v-if="contact?.wechat" class="contact-row"><view class="contact-row-icon"><wd-icon name="message" size="20px" /></view><view class="grow"><text class="contact-label">客服微信</text><text class="contact-value" selectable>{{ contact.wechat }}</text></view><button role="button" aria-label="复制客服微信" @click="copyContact(contact.wechat)">复制</button></view>
        <view v-if="contact?.phone" class="contact-row"><view class="contact-row-icon"><wd-icon name="phone" size="20px" /></view><view class="grow"><text class="contact-label">联系电话</text><text class="contact-value" selectable>{{ contact.phone }}</text></view><button role="button" aria-label="拨打客服电话" @click="callContact">拨打</button></view>
        <view v-if="contact?.email" class="contact-row"><view class="contact-row-icon"><wd-icon name="email" size="20px" /></view><view class="grow"><text class="contact-label">联系邮箱</text><text class="contact-value" selectable>{{ contact.email }}</text></view><button role="button" aria-label="复制客服邮箱" @click="copyContact(contact.email)">复制</button></view>
        <view v-if="contact?.qr_url" class="contact-qr-block"><image class="contact-qr" :src="contact.qr_url" mode="aspectFit" show-menu-by-longpress @click="previewQr" /><text>点击放大，长按识别客服二维码</text></view>
        <view class="contact-message"><wd-button role="button" block type="info" variant="plain" @click="leaveMessage">留言咨询</wd-button><text>问题和回复可在「服务反馈」中查看</text></view>
      </view>
    </wd-popup>
  </view>
</template>

<style scoped>
.membership-page { width:100%;max-width:520px;min-height:100vh;margin:0 auto;padding-bottom:calc(122px + env(safe-area-inset-bottom));background:linear-gradient(180deg,#eaf3ed 0,#f7f9f8 330px); }
.member-heading { display:flex;align-items:center;justify-content:space-between;gap:12px;padding-top:2px;padding-bottom:16px; }
.member-heading > text { font-size:24px;font-weight:700;color:var(--lc-text);line-height:1.5; }
.order-link { display:flex;align-items:center;gap:5px;min-height:40px;margin:0;padding:6px 0;background:transparent;color:var(--lc-secondary);font-size:12px;line-height:1.5; }
.member-card { position:relative;overflow:hidden;padding:20px;border-radius:20px;color:#fff;background:radial-gradient(ellipse at 108% 0,#578465 0,transparent 64%),#264e3b;box-shadow:0 10px 24px #29473818; }
.member-card-top { display:flex;align-items:center;gap:16px; }
.member-title { display:block;font-size:22px;font-weight:650;line-height:1.4; }.member-status { display:block;margin-top:6px;font-size:12px;line-height:1.5;color:#d9e6db; }
.member-mark { display:flex;align-items:center;justify-content:center;width:48px;height:48px;flex:none;border:1px solid #d8bb784a;border-radius:16px;color:#f3d499;background:#f9dca216; }
.benefit-grid { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-top:20px;padding-top:15px;border-top:1px solid #ffffff26; }
.benefit-grid > view { display:flex;align-items:center;justify-content:center;gap:5px;min-width:0;color:#eff3e9;font-size:11px;white-space:nowrap; }.benefit-grid :deep(.wd-icon) { color:#ddca97; }
.member-body { padding-top:16px; }
.contact-entry { display:flex;align-items:center;gap:12px;width:100%;margin:0;padding:15px 14px;border:1px solid #dce9de;border-radius:16px;background:#fff;text-align:left;box-shadow:0 4px 12px #25433405; }
.contact-icon { display:flex;align-items:center;justify-content:center;width:43px;height:43px;flex:none;border-radius:14px;color:var(--lc-primary);background:#eaf4ed; }
.contact-title { display:block;color:var(--lc-text);font-size:16px;font-weight:650;line-height:1.4; }.contact-subtitle { display:block;margin-top:4px;font-size:11px;line-height:1.5;color:var(--lc-secondary); }
.contact-cta { display:flex;align-items:center;gap:3px;flex:none;padding:7px 10px;border-radius:999px;background:var(--lc-primary-soft);color:var(--lc-primary);font-size:12px;line-height:1.5; }
.plans-section { margin-top:25px; }.section-heading { margin:0 0 12px; }.section-title { display:block;margin:0;color:var(--lc-text);font-size:16px;font-weight:650;line-height:1.5; }.section-note { color:var(--lc-muted);font-size:11px; }
.plan-grid { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px; }.plan-grid.two { grid-template-columns:repeat(2,minmax(0,1fr)); }.plan-grid.single { grid-template-columns:1fr; }
.plan-card { position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;min-width:0;width:100%;margin:0;padding:17px 6px 16px;border:1.5px solid #e3e8e3;border-radius:14px;background:#fff;text-align:center;line-height:1.5;transition:border-color .15s,background-color .15s; }
.plan-card.selected { border-color:var(--lc-primary);background:#edf6ef; }.plan-card:active,.contact-entry:active { opacity:.85; }.plan-card[disabled] { opacity:.7; }
.plan-name { display:block;color:var(--lc-text);font-size:12px;font-weight:600;overflow-wrap:anywhere; }.plan-price { display:block;margin-top:8px;color:#2b694c;font-size:24px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.4;white-space:nowrap; }.plan-duration { display:block;margin-top:5px;color:var(--lc-secondary);font-size:11px; }
.plan-check { position:absolute;top:-1px;right:-1px;display:flex;align-items:center;justify-content:center;width:21px;height:19px;border-radius:0 13px 0 10px;background:var(--lc-primary);color:#fff; }
.single .plan-card { display:grid;grid-template-columns:1fr auto;justify-items:start;padding:15px 20px;text-align:left; }.single .plan-price { grid-column:2;grid-row:1/3;margin:0 8px 0 10px; }.single .plan-duration { grid-column:1; }
.plan-description { display:block;margin-top:10px;color:var(--lc-secondary);font-size:12px;line-height:1.7;overflow-wrap:anywhere; }.plan-tip { display:block;margin-top:9px;color:var(--lc-muted);font-size:11px;line-height:1.7; }
.plans-empty { padding:19px;border:1px dashed #d9e3db;border-radius:14px;text-align:center;color:var(--lc-secondary);font-size:13px; }.plans-empty button { display:flex;align-items:center;justify-content:center;gap:4px;margin:3px 0 0;padding:6px;background:transparent;color:var(--lc-primary);font-size:12px; }
.redeem-panel { margin-top:20px;padding:17px;border:1px solid var(--lc-card-line);border-radius:16px;background:#fff; }.redeem-heading { display:flex;align-items:center;gap:10px; }.redeem-icon { display:flex;align-items:center;justify-content:center;width:36px;height:36px;border-radius:11px;background:#f4f0e6;color:#977947; }.redeem-caption { display:block;margin-top:3px;color:var(--lc-muted);font-size:11px;line-height:1.6; }
.redeem-box { display:flex;align-items:center;gap:8px;margin-top:14px;padding:5px 5px 5px 12px;border:1px solid #e0e8e1;border-radius:10px;background:#f6f9f6; }.redeem-box:focus-within { border-color:var(--lc-primary); }
.redeem-box input { flex:1;min-width:0;height:38px;color:var(--lc-text);font-size:13px; }.redeem-box button { display:flex;align-items:center;justify-content:center;min-width:65px;min-height:38px;margin:0;padding:6px 12px;border-radius:7px;background:var(--lc-primary);color:#fff;font-size:13px;line-height:1.5; }.redeem-box button[disabled] { color:#7f9688;background:#e5ece6; }
.redeem-error { margin-top:9px;color:#a34040;font-size:12px;line-height:1.7; }.redeem-success { display:flex;align-items:flex-start;gap:8px;margin-top:12px;padding:11px;border-radius:9px;color:var(--lc-primary);background:var(--lc-primary-soft);font-size:12px;line-height:1.6; }.redeem-success text { display:block; }.redeem-success text+text { margin-top:3px;font-size:11px; }
.member-details { margin-top:14px; }.details-toggle { display:flex;align-items:center;justify-content:space-between;width:100%;min-height:48px;margin:0;padding:8px 2px;background:transparent;color:var(--lc-secondary);font-size:12px; }.details-content { padding:0 2px 10px;font-size:12px;color:var(--lc-secondary);line-height:1.9; }.details-content > text { display:block;margin-bottom:8px;white-space:pre-wrap;overflow-wrap:anywhere; }.details-content button { display:flex;align-items:center;gap:4px;margin:0;padding:8px 0;background:transparent;color:var(--lc-primary);font-size:12px; }
.member-footer { position:fixed;z-index:20;right:0;bottom:0;left:0;max-width:520px;margin:0 auto;padding-bottom:env(safe-area-inset-bottom);border-top:1px solid #e8eee8;background:#fffffffa;box-shadow:0 -4px 16px #27443005; }.footer-inner { display:flex;align-items:center;gap:20px;padding:10px 22px 14px; }.footer-contact { display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;min-width:48px;min-height:50px;margin:0;padding:0;background:transparent;color:var(--lc-primary);font-size:11px;line-height:1.5; }.footer-main { flex:1;min-width:0; }.footer-summary { display:block;margin-bottom:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:center;color:var(--lc-secondary);font-size:11px; }.footer-main :deep(.wd-button) { --wot-button-height-medium:44px; }
.contact-sheet { max-height:88vh;overflow-y:auto; }.contact-sheet-intro { display:block;margin-top:5px;color:var(--lc-muted);font-size:12px; }.contact-hours { display:block;margin-bottom:14px;color:var(--lc-secondary);font-size:12px; }.contact-empty { display:block;padding:12px 0 18px;font-size:13px;line-height:1.8;color:var(--lc-secondary); }
.contact-row { display:flex;align-items:center;gap:11px;padding:14px 0;border-bottom:1px solid var(--lc-border); }.contact-row-icon { display:flex;align-items:center;justify-content:center;width:37px;height:37px;flex:none;border-radius:12px;background:var(--lc-primary-soft);color:var(--lc-primary); }.contact-label { display:block;color:var(--lc-text);font-size:13px;font-weight:600; }.contact-value { display:block;margin-top:3px;font-size:12px;line-height:1.5;color:var(--lc-secondary);overflow-wrap:anywhere; }.contact-row button { flex:none;min-width:54px;min-height:38px;margin:0;padding:6px 10px;border-radius:999px;background:var(--lc-primary-soft);color:var(--lc-primary);font-size:12px;line-height:1.5; }
.contact-qr-block { display:flex;flex-direction:column;align-items:center;gap:10px;padding:20px 0 6px;color:var(--lc-muted);font-size:11px; }.contact-qr { width:144px;height:144px;border:1px solid var(--lc-card-line);border-radius:12px;background:#fff; }.contact-message { margin-top:22px; }.contact-message > text { display:block;margin-top:10px;text-align:center;font-size:11px;color:var(--lc-muted); }
@media (max-width:359px) { .content-width { padding-right:16px;padding-left:16px; }.member-card { padding:18px 16px; }.member-title { font-size:20px; }.contact-entry { gap:9px;padding:13px 11px; }.contact-icon { width:36px;height:36px; }.contact-subtitle { font-size:10px; }.contact-cta { padding:6px 8px; }.plan-grid { gap:6px; }.plan-price { font-size:21px; }.section-note { font-size:10px; }.redeem-panel { padding:14px; } }
</style>
