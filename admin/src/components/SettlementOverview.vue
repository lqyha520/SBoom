<script setup lang="ts">
import { yuan } from '../growth'
import type { SettlementSummary, SettlementTiming } from '../settlement-operations'
import SettlementTimeliness from './SettlementTimeliness.vue'
import type { SettlementKind } from '../settlements'
defineProps<{ summary: SettlementSummary; disabled?: boolean }>()
defineEmits<{ select: [kind: SettlementKind, status: string]; timing: [value: SettlementTiming] }>()
const cards: { key: 'pending' | 'reviewing' | 'approved'; label: string; kind: SettlementKind; hint: string }[] = [
  { key: 'pending', label: '待对账申请', kind: 'requests', hint: '扣个人费用前参考余额' },
  { key: 'reviewing', label: '对账中申请', kind: 'requests', hint: '扣个人费用前参考余额' },
  { key: 'approved', label: '待付款结算单', kind: 'statements', hint: '核定应付' },
]
</script>
<template>
  <div class="settlement-summary-grid" aria-label="结算金额汇总">
    <button v-for="card in cards" :key="card.key" type="button" class="metric promotion-action-card text-left" :data-stage="card.key" :disabled="disabled" @click="$emit('select', card.kind, card.key)">
      <div class="metric-label"><span>{{ card.label }} · {{ summary[card.key]?.count ?? 0 }} {{ card.kind === 'rewards' ? '笔' : '份' }}</span><UIcon name="i-lucide-arrow-up-right" aria-hidden="true" /></div>
      <div class="metric-number">{{ summary[card.key]?.unknown === summary[card.key]?.count && summary[card.key]?.count ? '待核对' : yuan(summary[card.key]?.amount_fen ?? 0) }}</div><p class="text-xs text-muted">{{ summary[card.key]?.unknown ? '已知金额小计' : card.hint }}<span v-if="summary[card.key]?.unknown">；另有 {{ summary[card.key].unknown }} {{ card.kind === 'rewards' ? '笔订单' : '份申请' }}金额待核对</span></p>
    </button>
  </div>
  <div class="promotion-secondary"><div class="actions-row"><UButton :label="'可申请奖励 · ' + summary.available.count + ' 笔'" variant="link" :disabled="disabled" @click="$emit('select', 'rewards', 'available')" /><UButton :label="'等待期内 · ' + summary.holding.count + ' 笔'" variant="link" :disabled="disabled" @click="$emit('select', 'rewards', 'holding')" /><UButton :label="'已付款 · ' + yuan(summary.paid.amount_fen)" variant="link" :disabled="disabled" @click="$emit('select', 'statements', 'paid')" /><UButton v-if="summary.exception.count" :label="summary.exception.count + ' 笔异常订单待处理'" color="warning" variant="link" :disabled="disabled" @click="$emit('select', 'rewards', 'exception')" /></div><SettlementTimeliness :summary="summary" :disabled="disabled" @select="$emit('timing', $event)" /></div>
</template>
<style scoped>
.settlement-summary-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}
.metric{background:#f6f9f7;border-color:#e5ede8;padding:18px}.metric-number{margin:8px 0 6px}
.promotion-secondary{margin-top:16px;padding-top:12px}
@media(max-width:650px){.settlement-summary-grid{grid-template-columns:minmax(0,1fr);gap:10px}.metric{display:grid;grid-template-columns:1fr auto;align-items:center;gap:5px 14px;padding:14px 16px}.metric-number{font-size:24px;margin:0}.metric>p{grid-column:1/-1}}
</style>
