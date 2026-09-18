<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import AuthGate from './AuthGate.vue'
import AppTabBar from './AppTabBar.vue'
import PageChrome from './PageChrome.vue'
import PaperRow from './PaperRow.vue'
import EnhancedSkeleton from './EnhancedSkeleton.vue'
import SearchField from './SearchField.vue'
import CatalogFilterSheet from './CatalogFilterSheet.vue'
import FavoriteGroups from './FavoriteGroups.vue'
import { clearHistory, fetchTopics, type Topic } from '../services/experience'
import { readPreferences, rememberSearch, writePreferences } from '../services/preferences'
import { errorMessage, favoriteCatalogPaper, fetchCatalog, fetchCatalogSummary } from '../services/api'
import { ensureSession, requireLogin, session } from '../services/session'
import { createLatestRequest } from '../services/latest-request'
import { catalogSelection, openCatalog, openCatalogPaper, confirmAction } from '../services/navigation'
import { exerciseText, subjectOptions } from '../presentation'
import type { CatalogSummary, PaperSummary } from '../types'
import { emptyTags, fetchTags, tagKinds, openRequests, type CatalogTag, type TagFilters } from '../services/growth'
import { debounce } from '../utils/performance'

const props = withDefaults(defineProps<{ view?: 'all' | 'favorites' | 'downloads' | 'recent'; topicId?: string }>(), { view: 'all', topicId: '' })
const canBrowse = computed(() => props.view === 'all' || !!session.user)
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
const topic = ref(props.topicId)
const topics = ref<Topic[]>([])
const tags = ref<CatalogTag[]>([])
const tagFilters = reactive(emptyTags())
const chosenTags = computed(() => tagKinds.filter(item => tagFilters[item.kind]).map(item => ({ kind: item.kind, name: tags.value.find(tag => tag.id === tagFilters[item.kind])?.name || item.label })))
const topicHeader = computed(() => topics.value.find(item => item.id === props.topicId))
const favoriteGroup = ref('')
const groupControl = ref<InstanceType<typeof FavoriteGroups> | null>(null)
const onlyFree = ref(false)
const sort = ref('featured')
const sorts = [{ value: 'featured', label: '精选' }, { value: 'latest', label: '最新' }, { value: 'popular', label: '热门' }]
const searches = ref<string[]>([])
const hasTabbar = computed(() => !props.topicId && (props.view === 'all' || props.view === 'favorites'))
const topicOptions = computed(() => [{ id: '', title: '全部专题' }, ...topics.value])
const filterOpen = ref(false)
const filterCount = computed(() => Number(!!grade.value) + Number(!!category.value) + chosenTags.value.length)
const subjects = computed(() => subjectOptions(summary.value?.subjects || ['语文', '数学', '英语']))
// category 存的是分类 id，展示名要在后台返回的分类表里查（分类改名后小程序自动跟着变）
const categoryName = computed(() => summary.value?.categories.find(item => item.id === category.value)?.name || '')
const requests = createLatestRequest()
let active = false
let selectionRevision = -1
let timer: ReturnType<typeof setTimeout> | undefined
let loaded = false
let scrollTop = 0
const filtered = computed(() => !!(q.value || grade.value || subject.value || category.value || (!props.topicId && topic.value) || onlyFree.value || favoriteGroup.value || chosenTags.value.length))
function preferences() {
  const saved = readPreferences(session.user?.id || '')
  grade.value = saved.grade; subject.value = saved.subject; searches.value = saved.history
}
const debouncedSearch = debounce((value: string) => {
  q.value = value
  if (session.user && value.trim()) {
    const saved = rememberSearch(readPreferences(session.user.id), value)
    writePreferences(session.user.id, saved); searches.value = saved.history
  }
  clearTimeout(timer)
  void refresh()
}, 300)
function search(value = q.value) {
  debouncedSearch(value)
}
function clearSearches() {
  searches.value = []
  if (session.user) writePreferences(session.user.id, { ...readPreferences(session.user.id), history: [] })
}
async function clearRecent() {
  const owner = session.user?.id
  if (!await confirmAction('清空浏览记录', '仅清空最近浏览，不影响收藏与下载记录。') || owner !== session.user?.id) return
  try { await clearHistory(); await refresh() } catch (cause) { error.value = errorMessage(cause) }
}

async function refresh(reset = true, preserveWindow = false) {
  if (!canBrowse.value || !active) { uni.stopPullDownRefresh(); return }
  if (reset) clearTimeout(timer)
  if (!reset && (loading.value || !more.value)) return
  const current = requests.begin()
  loading.value = true; error.value = ''
  try {
    const filters = { q: q.value, grade: grade.value, subject: subject.value, category: category.value,
      favorite: props.view === 'favorites', downloaded: props.view === 'downloads', recent: props.view === 'recent',
      favorite_group: favoriteGroup.value, topic: topic.value, only_free: onlyFree.value, sort: sort.value,
      ...tagFilters }
    const wanted = preserveWindow ? Math.max(20, items.value.length) : 20
    const result = await fetchCatalog({ ...filters, offset: reset ? 0 : items.value.length, limit: 20 })
    while (current() && reset && result.has_more && result.items.length < wanted) {
      const next = await fetchCatalog({ ...filters, offset: result.items.length, limit: 20 })
      if (!next.items.length) { result.has_more = false; break }
      result.items.push(...next.items)
      result.total = next.total; result.has_more = next.has_more
    }
    if (!current()) return
    items.value = reset ? result.items : [...items.value, ...result.items.filter(item => !items.value.some(old => old.id === item.id))]
    total.value = result.total; more.value = result.has_more
    loaded = true
    if (preserveWindow) { await nextTick(); if (current()) uni.pageScrollTo({ scrollTop, duration: 0 }) }
    if (reset) {
      const [counts, collections, labels] = await Promise.all([fetchCatalogSummary(), fetchTopics(), fetchTags()])
      if (current()) { summary.value = counts; topics.value = collections.items; tags.value = labels.items }
    }
  } catch (cause) { if (current()) error.value = errorMessage(cause) }
  finally { if (current()) { loading.value = false; uni.stopPullDownRefresh() } }
}
async function activate() {
  active = true
  await ensureSession()
  if (canBrowse.value && active) {
    const previousSelection = selectionRevision
    if (selectionRevision < 0 && !props.topicId) preferences()
    if (!props.topicId && props.view === 'all' && catalogSelection.revision > 0 && selectionRevision !== catalogSelection.revision) {
      q.value = catalogSelection.q; grade.value = catalogSelection.grade
      subject.value = catalogSelection.subject; category.value = catalogSelection.category; topic.value = catalogSelection.topic
      selectionRevision = catalogSelection.revision
    }
    selectionRevision = catalogSelection.revision
    searches.value = readPreferences(session.user?.id || '').history
    void groupControl.value?.refresh()
    clearTimeout(timer); void refresh(true, loaded && previousSelection === catalogSelection.revision)
  }
}
function deactivate() { active = false; clearTimeout(timer); requests.invalidate(); loading.value = false; filterOpen.value = false; uni.stopPullDownRefresh() }
watch([q, grade, subject, category, topic, sort, onlyFree, favoriteGroup, () => Object.values(tagFilters).join(':')], () => {
  requests.invalidate(); more.value = false
  loaded = false; scrollTop = 0
  if (active && canBrowse.value) { loading.value = true; void refresh() }
}, { flush: 'sync' })
watch([grade, subject], () => {
  if (session.user) writePreferences(session.user.id, { ...readPreferences(session.user.id), grade: grade.value, subject: subject.value })
})
watch(() => session.user?.id, (owner, previous) => {
  requests.invalidate(); clearTimeout(timer); items.value = []; summary.value = null; total.value = 0; more.value = false
  error.value = ''; loading.value = false; q.value = ''; grade.value = ''; subject.value = ''; category.value = ''
  selectionRevision = catalogSelection.revision
  loaded = false; scrollTop = 0
  topic.value = props.topicId; topics.value = []; tags.value = []; Object.assign(tagFilters, emptyTags()); favoriteGroup.value = ''; onlyFree.value = false; sort.value = 'featured'; if (!props.topicId) preferences()
  filterOpen.value = false
  if (active && previous && !owner) void refresh()
}, { flush: 'sync' })
watch(() => props.topicId, value => { topic.value = value })
function resetFilters() { q.value = ''; grade.value = ''; subject.value = ''; category.value = ''; topic.value = props.topicId; onlyFree.value = false; favoriteGroup.value = ''; Object.assign(tagFilters, emptyTags()) }
function applyFilters(filters: { grade: string; category: string; tags: TagFilters }) { grade.value = filters.grade; category.value = filters.category; Object.assign(tagFilters, filters.tags) }
async function favorite(paper: PaperSummary) {
  if (changing.value || loading.value) return
  if (!requireLogin('/pages/paper/index?id=' + encodeURIComponent(paper.id))) return
  const current = requests.begin()
  changing.value = paper.id
  try {
    const result = await favoriteCatalogPaper(paper.id, !paper.favorite)
    if (current()) {
      paper.favorite = result.favorite
      if (props.view === 'favorites' && !result.favorite) {
        items.value = items.value.filter(item => item.id !== paper.id)
        total.value = Math.max(0, total.value - 1)
      }
    }
  } catch (cause) { if (current()) error.value = errorMessage(cause) }
  finally { changing.value = '' }
}
async function handleDownload(paper: PaperSummary) {
  if (!requireLogin('/pages/paper/index?id=' + encodeURIComponent(paper.id))) return
  // Navigate to paper detail and trigger download
  openCatalogPaper(paper.id)
}
async function handleShare(paper: PaperSummary) {
  // #ifdef MP-WEIXIN
  uni.share({
    title: exerciseText(paper.title),
    path: '/pages/paper/index?id=' + encodeURIComponent(paper.id)
  })
  // #endif
}
defineExpose({ activate, deactivate, refresh, rememberScroll: (top: number) => { scrollTop = top }, loadMore: () => refresh(false), shareTitle: computed(() => topicHeader.value?.title || '习题专题') })
onMounted(activate)
onBeforeUnmount(deactivate)
</script>

<template>
  <view class="catalog-page" :class="{ 'has-tabbar': hasTabbar }">
    <PageChrome :back="!hasTabbar" fallback="/pages/account/index" />
    <view v-if="topicId" class="content-width topic-header"><text class="topic-page-title">{{ topicHeader?.title || '习题专题' }}</text><text v-if="topicHeader?.description">{{ topicHeader.description }}</text><text v-if="!loading && !error && canBrowse && !topicHeader">该专题已下架或暂不可用</text><!-- #ifdef MP-WEIXIN --><button v-if="topicHeader" class="section-link" open-type="share">分享专题</button><!-- #endif --></view>
    <view class="catalog-band"><view class="content-width catalog-header">
      <template v-if="canBrowse"><view class="catalog-search-row"><button class="catalog-grade" role="button" aria-label="选择年级和分类" @click="filterOpen = true"><text>{{ grade || '全部年级' }}</text><wd-icon name="down" size="11px" /></button><view class="grow"><SearchField v-model="q" :placeholder="view === 'favorites' ? '搜索收藏' : view === 'downloads' ? '搜索下载记录' : '搜索习题'" @search="search()" /></view></view><view class="catalog-tab-row"><view class="catalog-tabs"><wd-tabs v-model="subject" :slidable-num="4" :map-num="100" line-theme="text"><wd-tab name="" title="全部" /><wd-tab v-for="value in subjects" :key="value" :name="value" :title="value" /></wd-tabs></view><button class="bare-icon catalog-filter" :class="{ selected: filterCount }" role="button" aria-label="筛选年级和分类" title="筛选年级和分类" @click="filterOpen = true"><wd-icon name="filter" size="19px" /><view v-if="filterCount" class="filter-dot" /></button></view></template>
    </view></view>
    <AuthGate v-if="!canBrowse" />
    <view v-else class="content-width catalog-body">
      <view v-if="view === 'recent'" class="experience-toolbar"><text>最近浏览</text><button class="section-link" role="button" @click="clearRecent">清空浏览记录</button></view>
      <view v-if="!q && searches.length" class="search-history"><text>最近搜索</text><button role="button" v-for="value in searches" :key="value" @click="search(value)">{{ value }}</button><button class="section-link" role="button" @click="clearSearches">清空</button></view>
      <view class="experience-toolbar"><view v-if="view === 'all' && !topicId" class="sort-buttons"><button role="button" v-for="item in sorts" :key="item.value" :class="{ selected: sort === item.value }" :aria-pressed="sort === item.value" @click="sort = item.value">{{ item.label }}</button></view><button role="button" class="filter-free" :class="{ selected: onlyFree }" :aria-pressed="onlyFree" @click="onlyFree = !onlyFree">{{ onlyFree ? '✓ ' : '' }}仅免费</button><picker v-if="topics.length && !topicId" :range="topicOptions.map(item => item.title)" :value="Math.max(0, topicOptions.findIndex(item => item.id === topic))" @change="topic = topicOptions[Number($event.detail.value)]!.id"><view class="topic-choice">{{ topicOptions.find(item => item.id === topic)?.title || '全部专题' }} ▾</view></picker></view>
      <FavoriteGroups ref="groupControl" v-if="view === 'favorites'" :selected="favoriteGroup" @select="favoriteGroup = $event" />
      <view v-if="grade || category || chosenTags.length" class="active-filters"><wd-tag v-if="grade" closable variant="light" type="primary" @close="grade = ''">{{ grade }}</wd-tag><wd-tag v-if="category" closable variant="light" type="primary" @close="category = ''">{{ exerciseText(categoryName) || '已选分类' }}</wd-tag><wd-tag v-for="tag in chosenTags" :key="tag.kind" closable variant="light" @close="tagFilters[tag.kind] = ''">{{ tag.name }}</wd-tag></view>
      <view v-if="error" class="error-strip"><text class="grow">{{ error }}</text><wd-button icon="refresh" type="danger" variant="text" role="button" aria-label="重试加载" @click="refresh()" /></view>
      <view class="list-caption"><text class="result-count">{{ loading ? '正在检索习题' : '共 ' + total + ' 份习题' }}</text><button v-if="filtered" class="section-link" role="button" @click="resetFilters"><wd-icon name="close-circle" size="14px" /><text>清除筛选</text></button><text v-else>{{ view === 'all' ? (sort === 'latest' ? '最新发布' : sort === 'popular' ? '热门习题' : '精选优先') : view === 'downloads' ? '最近下载' : view === 'recent' ? '最近浏览' : '最近收藏' }}</text></view>
      <EnhancedSkeleton v-if="loading && !items.length" :count="4" type="row" />
      <view v-else-if="items.length" class="paper-list catalog-paper-list"><PaperRow v-for="paper in items" :key="paper.id" :paper="paper" :busy="!!changing || loading" @favorite="favorite(paper)" @download="handleDownload(paper)" @share="handleShare(paper)" /></view>
      <view v-else-if="!loading && !error" class="catalog-empty"><wd-empty :icon="filtered ? 'no-result' : view === 'favorites' ? 'no-collection' : 'no-content'" :tip="filtered ? '没有匹配的习题' : view === 'favorites' ? '还没有收藏的习题' : view === 'downloads' ? '暂无下载记录' : view === 'recent' ? '暂无浏览记录' : '暂无已发布习题'"><template #bottom><view v-if="filtered || view !== 'all'" class="empty-actions"><wd-button v-if="filtered" variant="plain" role="button" @click="resetFilters">清除筛选</wd-button><wd-button v-else variant="plain" icon="book" role="button" @click="openCatalog()">去习题库看看</wd-button></view></template></wd-empty></view>
      <view v-if="loading && items.length" class="loading-line"><wd-loading size="18px" /><text>正在加载</text></view>
      <view v-if="view === 'all' && !loading && !error && !items.length" class="request-entry"><text>没有找到需要的资料？</text><wd-button variant="plain" size="small" @click="openRequests({ q, grade, subject })">提交资料需求</wd-button></view>
      <view v-else-if="more" class="loading-line"><wd-button variant="text" icon="down" role="button" @click="refresh(false)">加载更多</wd-button></view>
      <view v-else-if="items.length" class="list-end">已显示全部 {{ total }} 份习题</view>
    </view>
    <CatalogFilterSheet :open="filterOpen" :grade="grade" :category="category" :grades="summary?.grades || []" :categories="summary?.categories || []" :tags="tags" :tag-filters="tagFilters" @close="filterOpen = false" @apply="applyFilters" />
    <AppTabBar v-if="hasTabbar" :current="view === 'favorites' ? 'favorites' : 'library'" />
  </view>
</template>

<style scoped>
.topic-header { display:flex;flex-direction:column;gap:10px;padding-top:20px;color:var(--lc-secondary);font-size:13px;line-height:1.7; }.topic-page-title { font-size:24px;font-weight:650;color:var(--lc-text); }.request-entry { display:flex;align-items:center;justify-content:center;gap:12px;flex-wrap:wrap;font-size:13px;color:var(--lc-muted);padding:0 0 28px; }
.experience-toolbar,.sort-buttons,.search-history { display:flex;align-items:center;gap:10px;flex-wrap:wrap; }.experience-toolbar { margin:14px 0;font-size:13px; }.experience-toolbar button,.search-history button { margin:0;padding:5px 10px;font-size:12px;line-height:1.7;background:var(--lc-background);color:var(--lc-secondary);border-radius:16px; }.experience-toolbar .selected { color:var(--lc-primary);background:var(--lc-primary-soft); }.search-history { padding-top:14px;font-size:12px;color:var(--lc-muted); }.topic-choice { max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--lc-primary); }
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
