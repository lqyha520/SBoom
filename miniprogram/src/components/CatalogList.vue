<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AuthGate from './AuthGate.vue'
import AppTabBar from './AppTabBar.vue'
import PageChrome from './PageChrome.vue'
import PaperRow from './PaperRow.vue'
import PaperSkeleton from './PaperSkeleton.vue'
import SearchField from './SearchField.vue'
import CatalogFilterSheet from './CatalogFilterSheet.vue'
import { errorMessage, favoriteCatalogPaper, fetchCatalog, fetchCatalogSummary } from '../services/api'
import { ensureSession, session } from '../services/session'
import { createLatestRequest } from '../services/latest-request'
import { catalogSelection, openCatalog } from '../services/navigation'
import { exerciseText, subjectOptions } from '../presentation'
import type { CatalogSummary, PaperSummary } from '../types'

const props = withDefaults(defineProps<{ view?: 'all' | 'favorites' | 'downloads' }>(), { view: 'all' })
const items = ref<PaperSummary[]>([])
const summary = ref<CatalogSummary | null>(null)
const total = ref(0)
const more = ref(false)
const loading = ref(false)
const error = ref('')
const changing = ref('')
const q = ref('')
const grade = ref('')
const subject = ref('')
const category = ref('')
const filterOpen = ref(false)
const filterCount = computed(() => Number(!!grade.value) + Number(!!category.value))
const subjects = computed(() => subjectOptions(summary.value?.subjects || ['语文', '数学', '英语']))
// category 存的是分类 id，展示名要在后台返回的分类表里查（分类改名后小程序自动跟着变）
const categoryName = computed(() => summary.value?.categories.find(item => item.id === category.value)?.name || '')
const requests = createLatestRequest()
let active = false
let selectionRevision = -1
let timer: ReturnType<typeof setTimeout> | undefined
const filtered = computed(() => !!(q.value || grade.value || subject.value || category.value))

async function refresh(reset = true) {
  if (!session.user || !active) { uni.stopPullDownRefresh(); return }
  if (reset) clearTimeout(timer)
  if (!reset && (loading.value || !more.value)) return
  const current = requests.begin()
  loading.value = true; error.value = ''
  try {
    const result = await fetchCatalog({ q: q.value, grade: grade.value, subject: subject.value, category: category.value,
      favorite: props.view === 'favorites', downloaded: props.view === 'downloads', offset: reset ? 0 : items.value.length, limit: 20 })
    if (!current()) return
    items.value = reset ? result.items : [...items.value, ...result.items.filter(item => !items.value.some(old => old.id === item.id))]
    total.value = result.total; more.value = result.has_more
    if (reset) { const counts = await fetchCatalogSummary(); if (current()) summary.value = counts }
  } catch (cause) { if (current()) error.value = errorMessage(cause) }
  finally { if (current()) { loading.value = false; uni.stopPullDownRefresh() } }
}
async function activate() {
  active = true
  if (await ensureSession() && active) {
    if (props.view === 'all' && selectionRevision !== catalogSelection.revision) {
      q.value = catalogSelection.q; grade.value = catalogSelection.grade
      subject.value = catalogSelection.subject; category.value = catalogSelection.category
      selectionRevision = catalogSelection.revision
    }
    clearTimeout(timer); void refresh()
  }
}
function deactivate() { active = false; clearTimeout(timer); requests.invalidate(); loading.value = false; filterOpen.value = false; uni.stopPullDownRefresh() }
watch([q, grade, subject, category], () => {
  clearTimeout(timer); requests.invalidate(); more.value = false
  if (active && session.user) { loading.value = true; timer = setTimeout(() => { void refresh() }, 300) }
}, { flush: 'sync' })
watch(() => session.user?.id, () => {
  requests.invalidate(); clearTimeout(timer); items.value = []; summary.value = null; total.value = 0; more.value = false
  error.value = ''; loading.value = false; q.value = ''; grade.value = ''; subject.value = ''; category.value = ''
  selectionRevision = catalogSelection.revision
  filterOpen.value = false
}, { flush: 'sync' })
function resetFilters() { q.value = ''; grade.value = ''; subject.value = ''; category.value = '' }
function applyFilters(filters: { grade: string; category: string }) { grade.value = filters.grade; category.value = filters.category }
async function favorite(paper: PaperSummary) {
  if (changing.value || loading.value) return
  const current = requests.begin()
  changing.value = paper.id
  try {
    await favoriteCatalogPaper(paper.id, !paper.favorite)
    if (current()) await refresh()
  } catch (cause) { if (current()) error.value = errorMessage(cause) }
  finally { changing.value = '' }
}
defineExpose({ activate, deactivate, refresh, loadMore: () => refresh(false) })
onMounted(activate)
onBeforeUnmount(deactivate)
</script>

<template>
  <view class="catalog-page" :class="{ 'has-tabbar': view !== 'downloads' }">
    <PageChrome :back="view === 'downloads'" fallback="/pages/account/index" />
    <view class="catalog-band"><view class="content-width catalog-header">
      <template v-if="session.user"><view class="catalog-search-row"><button class="catalog-grade" role="button" aria-label="选择年级和分类" @click="filterOpen = true"><text>{{ grade || '全部年级' }}</text><wd-icon name="down" size="11px" /></button><view class="grow"><SearchField v-model="q" :placeholder="view === 'favorites' ? '搜索收藏' : view === 'downloads' ? '搜索下载记录' : '搜索习题'" @search="refresh()" /></view></view><view class="catalog-tab-row"><view class="catalog-tabs"><wd-tabs v-model="subject" :slidable-num="4" :map-num="100" line-theme="text"><wd-tab name="" title="全部" /><wd-tab v-for="value in subjects" :key="value" :name="value" :title="value" /></wd-tabs></view><button class="bare-icon catalog-filter" :class="{ selected: filterCount }" role="button" aria-label="筛选年级和分类" title="筛选年级和分类" @click="filterOpen = true"><wd-icon name="filter" size="19px" /><view v-if="filterCount" class="filter-dot" /></button></view></template>
    </view></view>
    <AuthGate v-if="!session.user" />
    <view v-else class="content-width catalog-body">
      <view v-if="grade || category" class="active-filters"><wd-tag v-if="grade" closable variant="light" type="primary" @close="grade = ''">{{ grade }}</wd-tag><wd-tag v-if="category" closable variant="light" type="primary" @close="category = ''">{{ exerciseText(categoryName) || '已选分类' }}</wd-tag></view>
      <view v-if="error" class="error-strip"><text class="grow">{{ error }}</text><wd-button icon="refresh" type="danger" variant="text" role="button" aria-label="重试加载" @click="refresh()" /></view>
      <view class="list-caption"><text class="result-count">{{ loading ? '正在检索习题' : '共 ' + total + ' 份习题' }}</text><button v-if="filtered" class="section-link" role="button" @click="resetFilters"><wd-icon name="close-circle" size="14px" /><text>清除筛选</text></button><text v-else>{{ view === 'all' ? '精选优先' : view === 'downloads' ? '最近下载' : '最近收藏' }}</text></view>
      <PaperSkeleton v-if="loading && !items.length" />
      <view v-else-if="items.length" class="paper-list catalog-paper-list"><PaperRow v-for="paper in items" :key="paper.id" :paper="paper" :busy="!!changing || loading" @favorite="favorite(paper)" /></view>
      <view v-else-if="!loading && !error" class="catalog-empty"><wd-empty :icon="filtered ? 'no-result' : view === 'favorites' ? 'no-collection' : 'no-content'" :tip="filtered ? '没有匹配的习题' : view === 'favorites' ? '还没有收藏的习题' : view === 'downloads' ? '暂无下载记录' : '暂无已发布习题'"><template #bottom><view v-if="filtered || view !== 'all'" class="empty-actions"><wd-button v-if="filtered" variant="plain" role="button" @click="resetFilters">清除筛选</wd-button><wd-button v-else variant="plain" icon="book" role="button" @click="openCatalog()">去习题库看看</wd-button></view></template></wd-empty></view>
      <view v-if="loading && items.length" class="loading-line"><wd-loading size="18px" /><text>正在加载</text></view>
      <view v-else-if="more" class="loading-line"><wd-button variant="text" icon="down" role="button" @click="refresh(false)">加载更多</wd-button></view>
      <view v-else-if="items.length" class="list-end">已显示全部 {{ total }} 份习题</view>
    </view>
    <CatalogFilterSheet :open="filterOpen" :grade="grade" :category="category" :grades="summary?.grades || []" :categories="summary?.categories || []" @close="filterOpen = false" @apply="applyFilters" />
    <AppTabBar v-if="view !== 'downloads'" :current="view === 'favorites' ? 'favorites' : 'library'" />
  </view>
</template>

<style scoped>
.catalog-band { background: transparent; }
.catalog-header { padding-top: 18px; --wot-search-plain-block-bg: #fff; }
.catalog-search-row { display: flex; align-items: center; gap: 9px; }
.catalog-grade { display: flex; align-items: center; justify-content: space-between; gap: 4px; width: 78px; min-height: 44px; flex: none; padding: 0; margin: 0; background: transparent; color: var(--lc-text); font-size: 12px; line-height: 1.5; }
.catalog-grade text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.catalog-tab-row { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.catalog-tabs { flex: 1; min-width: 0; margin-left: -10px; --wot-tabs-nav-item-padding: 14px 8px; --wot-tabs-nav-item-font-size: 14px; }
.catalog-filter { position: relative; }
.catalog-filter.selected { color: var(--lc-primary); background: var(--lc-primary-soft); }
.filter-dot { position: absolute; top: 9px; right: 9px; width: 5px; height: 5px; border-radius: 50%; background: var(--lc-primary); }
.catalog-body { padding-bottom: 30px; }
.catalog-paper-list { padding: 2px 16px; border: 1px solid var(--lc-card-line); border-radius: 14px; background: var(--lc-card); box-shadow: var(--lc-card-shadow-soft); }
.active-filters { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding-top: 18px; }
.catalog-empty { padding: 40px 0; }
.catalog-body .list-caption { min-height: 44px; }
</style>
