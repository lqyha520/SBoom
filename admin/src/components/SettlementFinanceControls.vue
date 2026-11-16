<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAdminPage } from '../admin-page'
import { adminRoute, navigateAdmin, useAdminLeaveGuard } from '../navigation'
import { useBeforeUnload } from '../unsaved'
import { financeControls, saveFinanceControls, type FinanceControls } from '../promotion-finance'
const props = defineProps<{ actor: number }>()
const value = ref<FinanceControls | null>(null), review = ref(false), payment = ref(false)
const dirty = computed(() => !!value.value && (review.value !== value.value.separate_review || payment.value !== value.value.separate_payment))
const pending = computed(() => adminRoute.tab === 'financeSettings' && dirty.value)
useBeforeUnload(pending)
useAdminLeaveGuard(() => {
  if (!pending.value) return true
  if (!window.confirm('财务复核规则尚未保存，确认离开并放弃修改？')) return false
  reset()
  return true
})
const roles = [{ icon: 'i-lucide-receipt-text', name: '费用核对与制单', detail: '核对渠道费用，整理订单并生成结算单。' }, { icon: 'i-lucide-shield-check', name: '审核与异议处理', detail: '核定个人费用与税款，回复并处理结算异议。' }, { icon: 'i-lucide-wallet', name: '付款登记与批次', detail: '整理付款清单，核对回单并登记已完成的付款。' }]
const page = useAdminPage(async valid => { const result = await financeControls(); if (valid()) { value.value = result; review.value = result.separate_review; payment.value = result.separate_payment } })
function reset() { if (value.value) { review.value = value.value.separate_review; payment.value = value.value.separate_payment } }
function save() { void page.act(async valid => { if (!value.value || !dirty.value) return; const result = await saveFinanceControls(props.actor, { revision: value.value.revision, separate_review: review.value, separate_payment: payment.value }); if (valid()) { value.value = result; review.value = result.separate_review; payment.value = result.separate_payment; page.notice.value = '财务复核规则已保存' } }) }
</script>
<template>
  <div class="field-stack promotion-finance-page">
    <div class="promotion-heading"><div><h2>财务分工与复核</h2><p>在管理员授权中分别分配以下职责，再按团队人数开启独立复核。</p></div><UButton label="刷新复核设置" icon="i-lucide-refresh-cw" variant="outline" :disabled="page.busy.value || dirty" :loading="page.loading.value" @click="page.load" /></div>
    <UAlert v-if="page.error.value" :title="page.error.value" color="error" /><UAlert v-if="page.notice.value" :title="page.notice.value" color="success" />
    <div class="promotion-role-grid"><article v-for="(role, index) in roles" :key="role.name" class="promotion-role-card"><div class="promotion-role-title"><UIcon :name="role.icon" /><span>{{ index + 1 }}</span></div><h3>{{ role.name }}</h3><p>{{ role.detail }}</p></article></div>
    <div class="promotion-detail-actions"><p class="text-xs text-muted">财务权限只扩大结算数据范围；其他业务仍按原授权控制。</p><UButton label="管理财务账号与授权" variant="link" @click="navigateAdmin('adminAccounts')" /></div>
    <form v-if="value" class="field-stack promotion-form" @submit.prevent="save">
      <div class="promotion-section-caption"><h3>独立复核规则</h3><span :class="dirty ? 'text-warning' : 'text-success'">{{ dirty ? '有未保存修改' : '与已保存设置一致' }}</span></div>
      <div class="promotion-control-card"><UCheckbox v-model="review" label="审核人必须与费用核对人、制单人不同" :disabled="page.busy.value || page.loading.value" /><p>审核账号须不同于本单的费用核对账号和制单账号。</p></div>
      <div class="promotion-control-card"><UCheckbox v-model="payment" label="付款登记人必须与审核人不同" :disabled="page.busy.value || page.loading.value" /><p>审核后的付款由另一账号登记，付款批次也遵循此规则。</p></div>
      <div class="promotion-form-footer"><p>规则也适用于超级管理员；单人财务可保持关闭。</p><div class="promotion-detail-actions"><UButton v-if="dirty" label="撤销未保存修改" variant="outline" :disabled="page.busy.value" @click="reset" /><UButton label="保存财务复核规则" type="submit" :loading="page.busy.value" :disabled="!dirty || page.busy.value || page.loading.value" /></div></div>
    </form>
  </div>
</template>
