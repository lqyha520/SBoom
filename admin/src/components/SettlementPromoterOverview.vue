<script setup lang="ts">
import { computed } from 'vue'
import { yuan } from '../growth'
import type { SettlementSummary, SettlementTiming } from '../settlement-operations'
import SettlementTimeliness from './SettlementTimeliness.vue'
import type { SettlementKind } from '../settlements'
const props = defineProps<{ summary: SettlementSummary; disabled?: boolean }>()
defineEmits<{ select: [kind: SettlementKind, status: string]; timing: [value: SettlementTiming] }>()
const processing = computed(() => props.summary.pending.count + props.summary.reviewing.count + props.summary.approved.count)
</script>
<template>
  <section class="space-y-3" aria-label="我的推广结算">
    <div class="promoter-cards">
      <button type="button" class="metric text-left" :disabled="disabled" @click="$emit('select', 'rewards', 'available')">
        <span class="metric-label">可申请 · {{ summary.available.count }} 笔</span><strong class="metric-number">{{ summary.available.unknown && summary.available.unknown === summary.available.count ? '待核对' : yuan(summary.available.amount_fen) }}</strong>
        <span class="text-xs text-muted">{{ summary.available.unknown ? '已知参考税前小计；另有 ' + summary.available.unknown + ' 笔金额待核对' : '参考税前奖励，最终金额以对账为准' }}</span>
      </button>
      <article class="metric"><span class="metric-label">处理中</span><strong class="metric-number">{{ processing }} 份</strong>
        <div class="flex flex-wrap gap-1">
          <UButton :label="'待对账 ' + summary.pending.count" variant="link" size="xs" :disabled="disabled" @click="$emit('select', 'requests', 'pending')" />
          <UButton :label="'对账中 ' + summary.reviewing.count" variant="link" size="xs" :disabled="disabled" @click="$emit('select', 'requests', 'reviewing')" />
          <UButton :label="'待付款 ' + summary.approved.count" variant="link" size="xs" :disabled="disabled" @click="$emit('select', 'statements', 'approved')" />
        </div><span class="text-xs text-muted">已核定待付 {{ yuan(summary.approved.amount_fen) }}；其余申请金额待审核。</span>
      </article>
      <button type="button" class="metric text-left" :disabled="disabled" @click="$emit('select', 'statements', 'paid')">
        <span class="metric-label">已付款 · {{ summary.paid.count }} 份</span><strong class="metric-number">{{ yuan(summary.paid.amount_fen) }}</strong><span class="text-xs text-muted">已登记的实际付款，到账请核对收款账户</span>
      </button>
    </div>
    <div class="actions-row text-sm">
      <UButton v-if="summary.holding.count" :label="'等待期内 ' + summary.holding.count + ' 笔'" variant="outline" :disabled="disabled" @click="$emit('select', 'rewards', 'holding')" />
      <UButton v-if="summary.exception.count" :label="'异常待处理 ' + summary.exception.count + ' 笔'" color="warning" variant="outline" :disabled="disabled" @click="$emit('select', 'rewards', 'exception')" />
      <SettlementTimeliness :summary="summary" :disabled="disabled" @select="$emit('timing', $event)" />
    </div>
  </section>
</template>
<style scoped>
.promoter-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.metric{display:flex;flex-direction:column;gap:10px;align-items:flex-start}.metric-number{font-variant-numeric:tabular-nums}
@media(max-width:760px){.promoter-cards{grid-template-columns:1fr;gap:10px}.metric{display:grid;grid-template-columns:1fr auto;align-items:center;gap:8px 14px;padding:14px 16px}.metric-number{margin:0}.metric>span:last-child,.metric>div{grid-column:1/-1}}
</style>
