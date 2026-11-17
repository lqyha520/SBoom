<script setup lang="ts">
import { computed, ref } from 'vue'
import type { UserInfo } from '../api'
import { canAdmin } from '../permissions'
import { useAdminListRoute, type AdminTab } from '../navigation'
import SettlementManager from './SettlementManager.vue'
import SettlementBatches from './SettlementBatches.vue'
import SettlementBills from './SettlementBills.vue'
import SettlementMonthly from './SettlementMonthly.vue'
import SettlementFinanceControls from './SettlementFinanceControls.vue'
import Reconciliations from './Reconciliations.vue'
import FinanceOverview from './FinanceOverview.vue'
import FinanceExpenses from './FinanceExpenses.vue'
import PromotionTabs from './PromotionTabs.vue'
import '../promotion-layout.css'

const props = defineProps<{ user: UserInfo; active: AdminTab }>()
const section = ref(canAdmin('settlementCosts') ? 'channels' : 'wechat')
const billSections = computed(() => [
  ...(canAdmin('settlementCosts') ? [{ value: 'channels', label: '渠道账单' }] : []),
  ...(canAdmin('reconciliations') ? [{ value: 'wechat', label: '微信账单核对' }] : []),
])
const billSection = computed(() => billSections.value.some(item => item.value === section.value) ? section.value : billSections.value[0]?.value)
if (props.active === 'financeBills') useAdminListRoute('financeBills', { section })
</script>
<template>
  <SettlementManager v-if="active === 'financeSettlements'" :user="user" mode="finance" route-tab="financeSettlements" />
  <SettlementManager v-else-if="active === 'referralEarnings'" :user="user" mode="personal" route-tab="referralEarnings" />
  <SettlementManager v-else-if="active === 'referralRules'" :user="user" mode="rules" route-tab="referralRules" />
  <FinanceOverview v-else-if="active === 'financeOverview'" :user="user" />
  <FinanceExpenses v-else-if="active === 'financeExpenses'" :user="user" />
  <section v-else class="admin-section promotion-workspace">
    <div v-if="active === 'financePayments'" class="promotion-panel"><SettlementBatches :user="user" /></div>
    <div v-else-if="active === 'financeMonthly'" class="promotion-panel"><SettlementMonthly :user="user" route-tab="financeMonthly" /></div>
    <div v-else-if="active === 'financeSettings'" class="promotion-panel"><SettlementFinanceControls :actor="user.id" /></div>
    <template v-else-if="active === 'financeBills'">
      <PromotionTabs v-if="billSections.length > 1" v-model="section" id="finance-bills" label="账单对账导航" :items="billSections" />
      <section v-if="billSection === 'channels'" id="finance-bills-panel-channels" role="tabpanel" aria-labelledby="finance-bills-tab-channels" class="promotion-panel"><div class="promotion-heading"><div><h2>渠道账单</h2><p>导入支付渠道账单，核对实收、手续费与退款差异。</p></div></div><SettlementBills :actor="user.id" :editable="canAdmin('settlementCosts', 'run')" /></section>
      <section v-else id="finance-bills-panel-wechat" role="tabpanel" aria-labelledby="finance-bills-tab-wechat" class="promotion-panel"><h2 class="font-semibold mb-4">微信账单核对</h2><Reconciliations :user="user" route-tab="financeBills" /></section>
    </template>
  </section>
</template>
