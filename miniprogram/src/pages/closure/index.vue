<script setup lang="ts">
import { ref } from 'vue'
import ServicePage from '../../components/ServicePage.vue'
import { useConsumerPage } from '../../services/consumer-page'
import { applyClosure, cancelClosure, fetchClosure, closureStatus, type Closure } from '../../services/growth'
import { confirmAction } from '../../services/navigation'
import { formatDate } from '../../content'
const item = ref<Closure | null>(null), reason = ref(''), acknowledged = ref(false), resolved = ref(false)
async function load(valid: () => boolean) { const result = await fetchClosure(); if (valid()) { item.value = result.request; resolved.value = true } }
const page = useConsumerPage(load, () => { item.value = null; reason.value = ''; acknowledged.value = false; resolved.value = false })
const { error, loading, busy } = page
function apply() { if (!acknowledged.value) return; void page.act(async valid => { if (!await confirmAction('申请注销账号', '审核通过后，个人资料、收藏、下载与浏览记录会清除，会员权益会失效。确认提交？') || !valid()) return; const result = await applyClosure(reason.value.trim()); if (valid()) { item.value = result.request; reason.value = ''; acknowledged.value = false } }) }
function cancel() { void page.act(async valid => { if (!item.value) return; const result = await cancelClosure(item.value.revision); if (valid()) item.value = result.request }) }
function orders() { uni.navigateTo({ url: '/pages/orders/index' }) }
</script>
<template>
  <ServicePage title="注销账号" description="提交后由管理员审核，审核完成前可随时撤回。" :error="error" :loading="loading" @retry="page.refresh">
    <view class="service-card"><text class="service-card-title">注销后会发生什么</text><text class="service-copy">个人资料、收藏、下载记录、浏览记录、反馈和消息将被清除，账号会员权益失效。按规定需要保留的交易记录会解除与账号的关联。此操作完成后无法恢复。</text><text class="service-copy">请先处理未付款订单和退款申请。注销账号本身不会发起退款；需要退款时，请先在订单页申请。</text><view class="service-actions"><wd-button role="button" variant="plain" size="small" @click="orders">查看我的订单</wd-button></view></view>
    <view v-if="item" class="service-card"><view class="service-row"><text class="service-card-title">{{ closureStatus[item.status] }}</text><text class="service-meta">{{ formatDate(item.updated_at) }}</text></view><text v-if="item.reason" class="service-copy">{{ item.reason }}</text><view v-if="item.reply" class="service-reply">{{ item.reply }}</view><view v-if="item.status === 'pending'" class="service-actions"><wd-button role="button" block variant="plain" :disabled="busy || loading" :loading="busy" @click="cancel">撤回注销申请</wd-button></view></view>
    <view v-if="resolved && !loading && item?.status !== 'pending'" class="service-card service-fields"><wd-textarea v-model="reason" :disabled="busy" :maxlength="500" placeholder="注销原因（选填）" show-word-limit /><wd-checkbox v-model="acknowledged" role="checkbox" :aria-checked="acknowledged" :disabled="busy">我已了解注销后果，并确认申请注销</wd-checkbox><wd-button role="button" type="danger" block :disabled="!acknowledged || busy" :aria-disabled="!acknowledged || busy" :loading="busy" @click="apply">提交注销申请</wd-button></view>
  </ServicePage>
</template>
