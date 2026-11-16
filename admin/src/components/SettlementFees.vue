<script setup lang="ts">
import { feeBasisNames, personalBasisNames, type FeeDraft } from '../settlements'
const fees = defineModel<FeeDraft[]>({ required: true })
defineProps<{ disabled?: boolean; label: string; allowPercent?: boolean; personal?: boolean; references?: boolean }>()
</script>

<template>
  <fieldset class="field-stack" :disabled="disabled">
    <legend class="font-medium text-sm mb-2">{{ label }}</legend>
    <div v-for="(fee, index) in fees" :key="index" class="actions-row">
      <UInput v-model="fee.name" :aria-label="label + '名称' + (index + 1)" placeholder="费用名称" maxlength="80" required />
      <USelect v-if="allowPercent" :model-value="fee.mode || 'fixed'" :items="[{ label: '固定金额', value: 'fixed' }, { label: '按百分比', value: 'percent' }]" :aria-label="label + '方式' + (index + 1)" @update:model-value="fee.mode = $event as 'fixed' | 'percent'" />
      <template v-if="allowPercent && fee.mode === 'percent'">
        <UInput v-model="fee.rate" :aria-label="label + '比例' + (index + 1)" placeholder="比例（%）" inputmode="decimal" required />
        <span class="text-sm">%</span>
        <USelect v-model="fee.basis" :items="Object.entries(personal ? personalBasisNames : feeBasisNames).map(([value, label]) => ({ value, label }))" :aria-label="label + '计算基数' + (index + 1)" />
      </template>
      <UInput v-else v-model="fee.amount" :aria-label="label + '金额' + (index + 1)" placeholder="金额（元）" inputmode="decimal" required />
      <UInput v-if="references" v-model="fee.source_ref" :aria-label="label + '凭据关联编号' + (index + 1)" placeholder="选填：凭据号/费用项" maxlength="120" />
      <UButton :label="'移除' + label + (index + 1)" variant="ghost" color="neutral" icon="i-lucide-x" @click="fees.splice(index, 1)" />
    </div>
    <p v-if="!fees.length" class="text-xs text-muted">无{{ label }}</p>
    <p v-if="allowPercent" class="text-xs text-muted">各项按所选基数分别计算，不逐项叠乘；每项不足一分部分舍去。比例和固定金额可混合使用。</p>
    <p v-if="references" class="text-xs text-muted">同一实际费用使用相同关联编号，防止换名重复扣除；一张发票多项费用用“凭据号/费用项”。在成本台账登记原始凭据总额后，使用“原始凭据号/费用项”关联，跨订单的共同与个人扣费合计不能超过总额。台账登记不会自动扣减奖励。</p>
    <p v-if="personal" class="text-xs text-muted">个人费用按本张结算单计算一次，不按订单重复扣；历史调整后可用奖励最低按 0 计算。</p>
    <UButton :label="'添加' + label" variant="outline" :disabled="disabled || fees.length >= 20" class="self-start" @click="fees.push({ name: '', amount: '', mode: 'fixed', rate: '', basis: personal ? 'reward_gross' : 'after_channel' })" />
  </fieldset>
</template>
