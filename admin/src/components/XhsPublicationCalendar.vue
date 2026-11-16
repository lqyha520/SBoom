<script setup lang="ts">
import { permissionDirective as vPermission } from '../permissions'
import { computed, onActivated, onDeactivated, onUnmounted, ref, watch } from 'vue'
import { navigateAdmin } from '../navigation'
import { formatWorkflowDate, workflowError, workflowStatus } from '../xhs-workflow'
import { getPublicationCalendar, localDay, weekStart, type CalendarData } from '../xhs-workspace'
const start = ref(weekStart()), account = ref('__all__'), loading = ref(false), error = ref('')
const pendingPage = ref(1)
const data = ref<CalendarData>({ items: [], unscheduled: [], accounts: [] })
const visible = computed(() => data.value.items.filter(item => account.value === '__all__' || item.account_key === account.value))
const days = computed(() => {
  const grouped = new Map<string, CalendarData['items']>()
  for (const item of visible.value) {
    if (!item.calendar_at) continue
    const key = localDay(new Date(item.calendar_at))
    const entries = grouped.get(key) || []; entries.push(item); grouped.set(key, entries)
  }
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(start.value); date.setDate(date.getDate() + index)
    const key = localDay(date)
    return { date, key, items: grouped.get(key) || [] }
  })
})
const weekLabel = computed(() => `${localDay(start.value)} — ${days.value[6]!.key}`)
const pending = computed(() => data.value.unscheduled.filter(item => account.value === '__all__' || item.account_key === account.value))
const pendingTotal = computed(() => data.value.unscheduled_total ?? pending.value.length)
const quiet = computed(() => data.value.accounts.filter(item => (account.value === '__all__' || item.id === account.value) && (!item.last_published_at || Date.now() - new Date(item.last_published_at).getTime() >= 14 * 86400000)))
let sequence = 0, active = true, receivedPage = false
async function load() {
  if (!active) return
  const id = ++sequence; loading.value = true; error.value = ''
  const end = new Date(start.value); end.setDate(end.getDate() + 7)
  try {
    const result = await getPublicationCalendar(start.value.toISOString(), end.toISOString(), account.value === '__all__' ? '' : account.value, pendingPage.value)
    if (id === sequence) {
      data.value = result
      if (result.unscheduled_page !== undefined && pendingPage.value !== result.unscheduled_page) {
        receivedPage = true; pendingPage.value = result.unscheduled_page
      }
    }
  }
  catch (cause) { if (id === sequence) error.value = workflowError(cause) }
  finally { if (id === sequence) loading.value = false }
}
function move(amount: number) { const next = new Date(start.value); next.setDate(next.getDate() + amount); start.value = next }
function choose(value: string) { if (value) start.value = weekStart(new Date(value + 'T12:00:00')) }
watch([start, account], () => { if (pendingPage.value !== 1) pendingPage.value = 1; else void load() })
watch(pendingPage, () => { if (receivedPage) receivedPage = false; else void load() })
onActivated(() => { active = true; if (!loading.value) void load() })
function deactivate() { active = false; sequence++; loading.value = false }
onDeactivated(deactivate); onUnmounted(deactivate)
void load()
</script>
<template><section aria-label="发布日历" :aria-busy="loading"><div class="calendar-toolbar"><div class="calendar-week-nav"><UButton label="上一周" icon="i-lucide-chevron-left" variant="outline" @click="move(-7)" /><UButton label="下一周" icon="i-lucide-chevron-right" trailing variant="outline" @click="move(7)" /></div><input class="workflow-native" type="date" aria-label="发布日历日期" :value="localDay(start)" @input="choose(($event.target as HTMLInputElement).value)" /><UButton label="本周" variant="ghost" @click="start=weekStart()" /><USelect v-model="account" class="calendar-account" aria-label="日历账号筛选" :items="[{value:'__all__',label:'全部账号'},...data.accounts.map(item=>({value:item.id,label:item.name}))]" /><UButton label="刷新日历" icon="i-lucide-refresh-cw" variant="ghost" :loading="loading" @click="load" /></div>
<div class="workflow-list-meta" role="status"><strong>{{ weekLabel }}</strong><span>{{ loading ? '正在读取发布安排…' : error ? '日历读取失败' : '本周 ' + visible.length + ' 项 · 未排期 ' + pendingTotal + ' 项' }}</span></div>
<p class="workflow-hint">按本机时区显示。点击计划进入发布准备；同账号一小时内的记录会提示排期接近，排期不会自动发布。</p><UAlert v-if="error" :title="error" color="error" />
<div v-if="error" class="workflow-empty-state"><p>暂时无法读取发布安排，请重新加载。</p><UButton label="重新加载日历" variant="outline" @click="load" /></div>
<div v-else-if="loading" class="publication-calendar" aria-hidden="true"><article v-for="day in days" :key="day.key"><h3>{{ day.date.toLocaleDateString('zh-CN',{weekday:'short'}) }} <small>{{ day.date.getMonth()+1 }}/{{ day.date.getDate() }}</small></h3><div class="calendar-placeholder"></div><div class="calendar-placeholder short"></div></article></div>
<template v-else>
<div class="publication-calendar"><article v-for="day in days" :key="day.key" :class="{today:day.key===localDay(new Date())}"><h3>{{ day.date.toLocaleDateString('zh-CN',{weekday:'short'}) }} <small>{{ day.date.getMonth()+1 }}/{{ day.date.getDate() }}</small><span v-if="day.key===localDay(new Date())" class="calendar-today">今天</span></h3><button v-permission="'xhsPublishing:view'" v-for="item in day.items" :key="item.id" type="button" :class="{conflict:item.conflicts.length}" @click="navigateAdmin('xhsPublishing',{id:item.id})"><time>{{ new Date(item.calendar_at!).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}) }}</time><strong>{{ item.title }}</strong><span>{{ item.data.account || '未指定账号' }} · {{ workflowStatus(item.status) }}</span><small v-if="item.conflicts.length">同账号排期接近 · 请检查</small></button><p v-if="!day.items.length">暂无安排</p></article></div>
<div v-if="quiet.length" class="workflow-step"><h3>账号发布登记提醒</h3><p v-for="item in quiet" :key="item.id">{{ item.name }}：{{ item.last_published_at ? '已超过 14 天没有新的发布登记，上次为 '+formatWorkflowDate(item.last_published_at) : '还没有实际发布登记' }}。请结合小红书实际情况核对。</p></div>
<div class="workflow-card"><h3>尚未排期 · {{ pendingTotal }} 项</h3><p v-if="!pending.length" class="workflow-hint">{{ account === '__all__' ? '所有进行中的发布计划都已排期。' : '当前账号没有尚未排期的发布计划。' }}</p><div class="workflow-list"><button v-permission="'xhsPublishing:view'" v-for="item in pending" :key="item.id" type="button" class="workflow-list-item" @click="navigateAdmin('xhsPublishing',{id:item.id})"><strong>{{ item.title }}</strong><span>{{ item.data.account || '未指定账号' }} · {{ workflowStatus(item.status) }}</span></button></div><div v-if="pendingTotal>20" class="workflow-pagination"><UPagination v-model:page="pendingPage" :total="pendingTotal" :items-per-page="20" :disabled="loading" aria-label="未排期记录分页" /></div></div></template></section></template>
<style scoped>
.calendar-toolbar{display:grid;grid-template-columns:auto minmax(150px,180px) auto minmax(140px,1fr) auto;align-items:center;gap:8px;margin:16px 0}
.calendar-week-nav{display:flex;gap:8px}.publication-calendar .calendar-today{margin-left:5px;font-size:11px;color:var(--ui-primary)}
.publication-calendar{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:10px;margin:18px 0}.publication-calendar article{min-height:180px;border:1px solid var(--ui-border);border-radius:12px;padding:12px;background:var(--ui-bg)}.publication-calendar article.today{border-color:var(--ui-primary)}h3{font-weight:600}h3 small{font-weight:400}.publication-calendar button{display:grid;gap:6px;width:100%;padding:12px;margin-top:10px;background:var(--ui-bg-muted);border-radius:8px;text-align:left;overflow-wrap:anywhere;font-size:12px;cursor:pointer}.publication-calendar button:focus-visible{outline:2px solid var(--ui-primary);outline-offset:2px}.publication-calendar time{color:var(--ui-primary)}.publication-calendar span,.publication-calendar p{color:var(--ui-text-muted);font-size:12px}.publication-calendar .conflict{background:#fff4df}.publication-calendar .conflict small{color:#886429}.publication-calendar p{margin-top:14px}.calendar-placeholder{height:18px;margin-top:20px;border-radius:5px;background:var(--ui-bg-accented)}.calendar-placeholder.short{width:60%;margin-top:10px}
@media(max-width:1200px){.publication-calendar{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:800px){.calendar-toolbar{grid-template-columns:1fr auto}.calendar-week-nav{grid-column:1/-1}.calendar-toolbar :deep(.calendar-account){width:100%}}
@media(max-width:600px){.publication-calendar{grid-template-columns:1fr}.publication-calendar article{min-height:100px}}
</style>
