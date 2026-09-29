<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useAdminListRoute } from '../navigation'
import type { UserInfo } from '../api'
import { useAdminPage } from '../admin-page'
import { createCards, disableCard, getCards, type MembershipCard, dateTime } from '../growth'
const props = defineProps<{ user: UserInfo }>()
const items = ref<MembershipCard[]>([]), total = ref(0), status = ref('all'), q = ref(''), pageNumber = ref(1)
const days = ref(30), quantity = ref(1), expires = ref(''), generated = ref<string[]>([])
const page = useAdminPage(async valid => {
  const result = await getCards(status.value === 'all' ? '' : status.value, (pageNumber.value - 1) * 50, q.value.trim())
  if (valid()) { items.value = result.items; total.value = result.total }
}, () => { generated.value = [] })
const { error, notice, loading, busy } = page
const routeState = useAdminListRoute('membershipCards', { status, q, page: pageNumber }, () => { void page.load() })
watch([status, q], () => { if (!routeState.restoring) { if (pageNumber.value !== 1) pageNumber.value = 1; else void page.load() } })
watch(pageNumber, () => { if (!routeState.restoring) void page.load() })
onBeforeUnmount(() => { generated.value = [] })
function generate() {
  void page.act(async valid => {
    const end = expires.value ? Math.floor(new Date(expires.value + 'T23:59:59+08:00').getTime() / 1000) : null
    if (end !== null && (!Number.isFinite(end) || end <= Date.now() / 1000)) throw new Error('失效日期必须是今天或之后')
    const result = await createCards(props.user.id, Number(days.value), Number(quantity.value), end)
    if (valid()) { generated.value = result.items.map(item => item.code); notice.value = '卡密已生成，请立即复制或导出；离开页面后不再显示'; await page.load() }
  })
}
function disable(id: string) {
  if (!window.confirm('确定作废这张卡密吗？作废后不能恢复。')) return
  void page.act(async valid => { await disableCard(props.user.id, id); if (valid()) { notice.value = '卡密已作废'; await page.load() } })
}
async function copy() {
  try { await navigator.clipboard.writeText(generated.value.join('\n')); notice.value = '已复制' }
  catch { error.value = '复制失败，请选中文本手动复制' }
}
function download() {
  const url = URL.createObjectURL(new Blob([generated.value.join('\n')], { type: 'text/plain;charset=utf-8' }))
  const link = document.createElement('a'); link.href = url; link.download = 'membership-cards.txt'; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>
<template>
  <section class="admin-section">
    <div class="section-toolbar"><p>卡密只在生成时显示一次，请及时保存。</p><div class="actions-row">
      <USelect v-model="status" aria-label="卡密状态" :items="[{label:'全部',value:'all'},{label:'可用',value:'active'},{label:'已兑换',value:'redeemed'},{label:'已作废',value:'disabled'}]" />
      <UInput v-model="q" placeholder="卡密尾号（4 位）" :maxlength="4" aria-label="卡密尾号" />
      <UButton label="刷新" variant="outline" :loading="loading" @click="page.load()" />
    </div></div>
    <UAlert v-if="error" :title="error" color="error" /><UAlert v-if="notice" :title="notice" color="success" />
    <form class="actions-row card-form" @submit.prevent="generate">
      <UFormField label="会员天数"><UInput v-model="days" type="number" min="1" max="3660" /></UFormField>
      <UFormField label="生成数量"><UInput v-model="quantity" type="number" min="1" max="1000" /></UFormField>
      <UFormField label="失效日期（北京时间当天结束，可选）"><UInput v-model="expires" type="date" /></UFormField>
      <UButton type="submit" label="生成卡密" :loading="busy" />
    </form>
    <div v-if="generated.length" class="generated"><strong>本次生成的卡密：</strong><textarea :value="generated.join('\n')" readonly rows="5" /><UButton label="复制全部" @click="copy" /><UButton label="导出卡密" @click="download" /></div>
    <div class="data-scroll"><table class="data-table"><thead><tr><th>卡密尾号</th><th>天数</th><th>状态</th><th>失效时间</th><th>兑换时间</th><th>操作</th></tr></thead>
      <tbody><tr v-for="item in items" :key="item.id"><td>****{{ item.code_hint }}</td><td>{{ item.days }} 天</td><td>{{ item.status === 'active' ? '可用' : item.status === 'redeemed' ? '已兑换' : '已作废' }}</td><td>{{ item.expires_at ? dateTime(item.expires_at) : '不限' }}</td><td>{{ dateTime(item.redeemed_at) }}</td><td><UButton v-if="item.status === 'active'" label="作废" color="error" variant="soft" @click="disable(item.id)" /></td></tr>
        <tr v-if="!items.length"><td colspan="6">{{ loading ? '正在加载' : '暂无卡密' }}</td></tr></tbody></table></div>
    <div class="actions-row"><span>共 {{ total }} 张，第 {{ pageNumber }} 页</span><UButton label="上一页" :disabled="loading || pageNumber <= 1" @click="pageNumber--" /><UButton label="下一页" :disabled="loading || pageNumber * 50 >= total" @click="pageNumber++" /></div>
  </section>
</template>
<style scoped>.card-form{align-items:end;margin:20px 0}.generated{padding:14px;margin:14px 0;background:var(--ui-bg-elevated);border-radius:8px}.generated textarea{display:block;width:100%;margin:10px 0;font-family:monospace}</style>
