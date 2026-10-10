<script setup lang="ts">
import { getCurrentInstance, computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import AuthGate from './AuthGate.vue'
import AppTabBar from './AppTabBar.vue'
import PageChrome from './PageChrome.vue'
import PaperRow from './PaperRow.vue'
import EnhancedSkeleton from './EnhancedSkeleton.vue'
import SearchGradeBar from './SearchGradeBar.vue'
import CatalogFilterSheet from './CatalogFilterSheet.vue'
import FavoriteGroups from './FavoriteGroups.vue'
import FavoriteBatchActions from './FavoriteBatchActions.vue'
import { clearHistory, fetchTopics, type Topic } from '../services/experience'
import { readPreferences, rememberSearch, writePreferences } from '../services/preferences'
import { errorMessage, favoriteCatalogPaper, fetchCatalogWindow, fetchCatalog, fetchCatalogSummary } from '../services/api'
import { ensureSession, requireLogin, session } from '../services/session'
import { createLatestRequest } from '../services/latest-request'
import { catalogSelection, openCatalog, openCatalogPaper, confirmAction } from '../services/navigation'
import { exerciseText, subjectOptions } from '../presentation'
import type { CatalogSummary, PaperSummary } from '../types'
import { emptyTags, fetchTags, tagKinds, openRequests, type CatalogTag, type TagFilters } from '../services/growth'
import GradePicker from './GradePicker.vue'
import { reconcileRows } from '../services/catalog-rows'
import { safeDestination } from '../services/return-route'

const props = withDefaults(defineProps<{ view?: 'all' | 'favorites' | 'downloads' | 'recent'; topicId?: string }>(), { view: 'all', topicId: '' })
const canBrowse = computed(() => props.view === 'all' || !!session.user)
const items = ref<PaperSummary[]>([])
// 保留三页内容，限制行组件、手势处理器和返回时的权限核验开销。
const windowSize = 60
const windowStart = ref(0)
const nextOffset = ref(0)
const imagesActive = ref(false)
const instance = getCurrentInstance()
const visibleImages = reactive(new Set<string>())
const observingImages = ref(true)
let imageObserver: UniApp.IntersectionObserver | undefined
watch([() => items.value.length, imagesActive], async () => {
  imageObserver?.disconnect(); imageObserver = undefined; observingImages.value = true
  if (!imagesActive.value) return
  await nextTick()
  if (!imagesActive.value || !items.value.length) return
  try {
    imageObserver = uni.createIntersectionObserver(instance?.proxy, { thresholds: [0], observeAll: true })
    observingImages.value = true
    imageObserver.relativeToViewport({ top: 400, bottom: 400 }).observe('.list-image-target', result => {
      const id = String((result as unknown as { dataset?: { paperId?: string } }).dataset?.paperId || '')
      if (result.intersectionRatio > 0) visibleImages.add(id); else visibleImages.delete(id)
    })
  } catch { imageObserver?.disconnect(); imageObserver = undefined; observingImages.value = false }
})
onBeforeUnmount(() => imageObserver?.disconnect())
const windowFull = computed(() => nextOffset.value >= windowStart.value + windowSize)
const summary = ref<CatalogSummary | null>(null)
const total = ref(0)
const more = ref(false)
const loading = ref(false)
const appending = ref(false)
const appendError = ref('')
const error = ref('')
const changing = reactive(new Set<string>())
let actionGeneration = 0, favoriteRevision = 0
const favoriteUpdates = new Map<string, { favorite: boolean; revision: number }>()
function invalidateActions() { actionGeneration++; changing.clear(); favoriteUpdates.clear() }
const q = ref('')
const searchInput = ref('')
const expandedRow = ref('')
const gradeOpen = ref(false)
const metadataError = ref('')
const metadataLoading = ref(false)
const metadataRequests = createLatestRequest()
let metadataAt = 0
let activation = 0
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
const selecting = ref(false), batchBusy = ref(false), selectedIds = ref<string[]>([])
const allSelected = computed(() => items.value.length > 0 && selectedIds.value.length === items.value.length)
function endSelection() { selecting.value = false; selectedIds.value = []; batchBusy.value = false }
function toggleSelection(id: string) {
  if (batchBusy.value) return
  selectedIds.value = selectedIds.value.includes(id) ? selectedIds.value.filter(value => value !== id) : [...selectedIds.value, id]
}
function selectAll() { if (!batchBusy.value) selectedIds.value = allSelected.value ? [] : items.value.map(item => item.id) }
function batchCompleted() { endSelection(); void refresh(); void groupControl.value?.refresh() }
watch(items, rows => { const ids = new Set(rows.map(item => item.id)); selectedIds.value = selectedIds.value.filter(id => ids.has(id)) })
const groupControl = ref<InstanceType<typeof FavoriteGroups> | null>(null)
const onlyFree = ref(false)
const sort = ref('featured')
const sorts = [{ value: 'featured', label: '精选' }, { value: 'latest', label: '最新' }, { value: 'popular', label: '热门' }]
const searches = ref<string[]>([])
const hasTabbar = computed(() => !props.topicId && (props.view === 'all' || props.view === 'favorites'))
const recordTitle = computed(() => ({ all: '', favorites: '我的收藏', downloads: '下载记录', recent: '最近浏览' })[props.view])
const recordDescription = computed(() => ({ all: '', favorites: '收藏喜欢的资料，下次接着练', downloads: '查找获取过的资料，方便再次打开', recent: '回到上次看过的资料，继续学习' })[props.view])
const topicOptions = computed(() => [{ id: '', title: '全部专题' }, ...topics.value])
const filterOpen = ref(false)
const filterCount = computed(() => Number(!!category.value) + chosenTags.value.length)
// Banner 可指向暂时没有资料的科目；保留该选项，避免标签组件把筛选重置成全部。
const subjects = computed(() => subjectOptions([...(summary.value?.subjects || ['语文', '数学', '英语']), ...(subject.value ? [subject.value] : [])]))
// category 存的是分类 id，展示名要在后台返回的分类表里查（分类改名后小程序自动跟着变）
const categoryName = computed(() => summary.value?.categories.find(item => item.id === category.value)?.name || '')
const requests = createLatestRequest()
let active = false
let selectionRevision = -1
let searchTimer: ReturnType<typeof setTimeout> | undefined
let loaded = false
let scrollTop = 0
const filtered = computed(() => !!(q.value || grade.value || subject.value || category.value || (!props.topicId && topic.value) || onlyFree.value || favoriteGroup.value || chosenTags.value.length || sort.value !== 'featured'))
const temporaryFilters = computed(() => !!(q.value || category.value || (!props.topicId && topic.value) || onlyFree.value || favoriteGroup.value || chosenTags.value.length || sort.value !== 'featured'))
function preferences() {
  const saved = readPreferences(session.user?.id || '')
  grade.value = saved.grade; subject.value = saved.subject; searches.value = saved.history
}
function cancelSearch() { clearTimeout(searchTimer); searchTimer = undefined }
let recordNextSearch = false
function rememberExplicitSearch(value: string) {
  if (!session.user || !value.trim()) return
  const saved = rememberSearch(readPreferences(session.user.id), value)
  writePreferences(session.user.id, saved); searches.value = saved.history
}
function commitSearch(value: string, explicit = false) {
  cancelSearch()
  if (!active) return
  const next = value.trim().slice(0, 120)
  recordNextSearch = explicit
  if (explicit) rememberExplicitSearch(next)
  if (q.value !== next) q.value = next
}
function search(value = searchInput.value) {
  const retry = q.value === value.trim()
  searchInput.value = value
  commitSearch(value, true)
  if (retry) void refresh()
}
watch(searchInput, value => {
  cancelSearch()
  if (active && value.trim() !== q.value) searchTimer = setTimeout(() => commitSearch(value), 300)
})
async function loadMetadata(force = false) {
  if (!active || metadataLoading.value || (!force && metadataAt && Date.now() - metadataAt < 300000)) return
  const current = metadataRequests.begin()
  const anonymous = props.view === 'all' && !session.user && (!session.ready || !!session.error)
  metadataLoading.value = true
  const results = await Promise.allSettled([
    fetchCatalogSummary({ scope: current, force, anonymous }).then(value => { if (current()) summary.value = value }),
    fetchTopics({ scope: current, force, anonymous }).then(value => { if (current()) topics.value = value.items }),
    fetchTags({ scope: current, force, anonymous }).then(value => { if (current()) tags.value = value.items }),
  ])
  if (!current()) return
  metadataError.value = results.flatMap((result, index) => result.status === 'rejected' ? [['分类', '专题', '教学标签'][index]] : []).join('、')
  metadataAt = metadataError.value ? 0 : Date.now()
  metadataLoading.value = false
}
async function reload() { await Promise.allSettled([refresh(), loadMetadata(true)]) }
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
  if (batchBusy.value) { uni.stopPullDownRefresh(); return }
  if (!canBrowse.value || !active) { uni.stopPullDownRefresh(); return }
  if (reset) expandedRow.value = ''
  if (!reset && (loading.value || !more.value || windowFull.value)) return
  const current = requests.begin()
  const anonymous = props.view === 'all' && !session.user && (!session.ready || !!session.error)
  const revision = favoriteRevision
  const offset = reset ? windowStart.value : nextOffset.value
  loading.value = true; appending.value = !reset; error.value = ''; appendError.value = ''
  try {
    const record = recordNextSearch && reset
    recordNextSearch = false
    const filters = { record, q: q.value, grade: grade.value, subject: subject.value, category: category.value,
      favorite: props.view === 'favorites', downloaded: props.view === 'downloads', recent: props.view === 'recent',
      favorite_group: favoriteGroup.value === '__ungrouped' ? '' : favoriteGroup.value, ungrouped: favoriteGroup.value === '__ungrouped', topic: topic.value, only_free: onlyFree.value, sort: sort.value,
      ...tagFilters }
    // Revalidate the retained window in one bounded request, alongside its head.
    // The server returns current rights for every retained row; no private policy is cached.
    const [result, window] = await Promise.all([
      fetchCatalog({ ...filters, offset, limit: Math.min(20, windowStart.value + windowSize - offset) }, { scope: current, anonymous }),
      preserveWindow && !anonymous ? fetchCatalogWindow(items.value.map(item => item.id), { scope: current }) : Promise.resolve(null),
    ])
    if (!current()) return
    if (!result.items.length && windowStart.value && result.total <= windowStart.value) {
      windowStart.value = Math.max(0, Math.floor((result.total - 1) / windowSize) * windowSize)
      items.value = []; loaded = false; scrollTop = 0
      return await refresh()
    }
    for (const item of [...result.items, ...(window?.items || [])]) {
      const update = favoriteUpdates.get(item.id)
      if (update && update.revision > revision) item.favorite = update.favorite
    }
    const head = new Map(result.items.map(item => [item.id, item]))
    const retained = (window?.items || []).map(item => {
      const context = head.get(item.id)
      return context && Object.prototype.hasOwnProperty.call(context, 'activity_at') ? { ...item, activity_at: context.activity_at } : item
    })
    const headUnchanged = preserveWindow && result.items.every((item, index) => item.id === items.value[index]?.id)
      && retained.length === items.value.length && result.total === total.value
    const existing = new Map(items.value.map(item => [item.id, item]))
    const validWindow = headUnchanged && retained.every(item => existing.has(item.id) && existing.get(item.id)!.revision === item.revision)
    items.value = validWindow ? reconcileRows(items.value, retained) : reset ? result.items : [...items.value, ...result.items.filter(item => !existing.has(item.id))]
    if (!validWindow) nextOffset.value = offset + result.items.length
    total.value = result.total; more.value = nextOffset.value < result.total && (validWindow || result.has_more !== false) && result.items.length > 0
    loaded = true
    if (preserveWindow) { if (!validWindow) scrollTop = 0; await nextTick(); if (current()) uni.pageScrollTo({ scrollTop, duration: 0 }) }

  } catch (cause) { if (current()) { if (reset) error.value = errorMessage(cause); else appendError.value = errorMessage(cause) } }
  finally { if (current()) { loading.value = false; appending.value = false; uni.stopPullDownRefresh() } }
}
async function turnWindow(direction: -1 | 1) {
  if (!active || loading.value || batchBusy.value || (direction < 0 ? !windowStart.value : !windowFull.value || !more.value)) return
  windowStart.value = Math.max(0, windowStart.value + direction * windowSize)
  nextOffset.value = windowStart.value
  items.value = []; loaded = false; scrollTop = 0; invalidateActions()
  uni.pageScrollTo({ scrollTop: 0, duration: 0 })
  await refresh()
}
async function activate() {
  const run = ++activation
  active = false
  cancelSearch()
  const anonymous = props.view === 'all' && !session.user && (!session.ready || !!session.error)
  const restored = ensureSession()
  if (!anonymous) await restored
  if (run !== activation) return
  if (canBrowse.value) {
    const previousSelection = selectionRevision
    if (selectionRevision < 0 && !props.topicId) preferences()
    if (!props.topicId && props.view === 'all' && catalogSelection.revision > 0 && selectionRevision !== catalogSelection.revision) {
      recordNextSearch = !!catalogSelection.q
      q.value = catalogSelection.q; grade.value = catalogSelection.grade
      subject.value = catalogSelection.subject; category.value = catalogSelection.category; topic.value = catalogSelection.topic
      onlyFree.value = false; sort.value = 'featured'; Object.assign(tagFilters, emptyTags())
    }
    selectionRevision = catalogSelection.revision
    searchInput.value = q.value
    searches.value = readPreferences(session.user?.id || '').history
    await nextTick()
    if (run !== activation) return
    active = true
    imagesActive.value = true
    void groupControl.value?.refresh()
    void loadMetadata()
    void refresh(true, loaded && previousSelection === catalogSelection.revision)
  } else active = true
  if (anonymous) void restored.then(() => { if (run === activation && active && session.user) void activate() })
}
function deactivate() {
  endSelection()
  imagesActive.value = false
  invalidateActions()
  active = false; activation++; cancelSearch(); requests.invalidate(); metadataRequests.invalidate()
  loading.value = false; metadataLoading.value = false; filterOpen.value = false; gradeOpen.value = false; expandedRow.value = ''
  uni.stopPullDownRefresh()
}
watch([q, grade, subject, category, topic, sort, onlyFree, favoriteGroup, () => Object.values(tagFilters).join(':')], () => {
  endSelection()
  windowStart.value = 0; nextOffset.value = 0
  invalidateActions(); items.value = []; total.value = 0; appendError.value = ''
  requests.invalidate(); more.value = false
  loaded = false; scrollTop = 0; expandedRow.value = ''
  if (active && canBrowse.value) { uni.pageScrollTo({ scrollTop: 0, duration: 0 }); loading.value = true; void refresh() }
})
watch([grade, subject], () => {
  if (session.user) writePreferences(session.user.id, { ...readPreferences(session.user.id), grade: grade.value, subject: subject.value })
})
watch(() => session.user?.id, (owner, previous) => {
  if (props.view === 'all' && !previous && owner) {
    // 从公开浏览恢复登录时保留搜索上下文，刷新权限和个人数据。
    invalidateActions(); requests.invalidate(); metadataRequests.invalidate()
    metadataAt = 0; metadataLoading.value = false; loading.value = false
    return
  }
  endSelection()
  windowStart.value = 0; nextOffset.value = 0
  invalidateActions(); appendError.value = ''; appending.value = false
  requests.invalidate(); metadataRequests.invalidate(); cancelSearch(); metadataAt = 0; metadataError.value = ''; metadataLoading.value = false; searchInput.value = ''; expandedRow.value = ''; items.value = []; summary.value = null; total.value = 0; more.value = false
  error.value = ''; loading.value = false; q.value = ''; grade.value = ''; subject.value = ''; category.value = ''
  selectionRevision = catalogSelection.revision
  loaded = false; scrollTop = 0
  topic.value = props.topicId; topics.value = []; tags.value = []; Object.assign(tagFilters, emptyTags()); favoriteGroup.value = ''; onlyFree.value = false; sort.value = 'featured'; if (!props.topicId) preferences()
  filterOpen.value = false; gradeOpen.value = false
  if (active && previous && !owner) void activate()
}, { flush: 'sync' })
watch(() => props.topicId, value => { topic.value = value })
function clearConditions() { cancelSearch(); searchInput.value = ''; q.value = ''; category.value = ''; topic.value = props.topicId; onlyFree.value = false; favoriteGroup.value = ''; sort.value = 'featured'; Object.assign(tagFilters, emptyTags()) }
function resetFilters() { clearConditions(); grade.value = ''; subject.value = '' }
function applyFilters(filters: { grade: string; category: string; tags: TagFilters }) { grade.value = filters.grade; category.value = filters.category; Object.assign(tagFilters, filters.tags) }
async function favorite(paper: PaperSummary) {
  if (changing.has(paper.id)) return
  if (!requireLogin('/pages/paper/index?id=' + encodeURIComponent(paper.id))) return
  const generation = actionGeneration
  const current = () => active && generation === actionGeneration
  changing.add(paper.id)
  try {
    const result = await favoriteCatalogPaper(paper.id, !paper.favorite)
    if (current()) {
      paper.favorite = result.favorite
      favoriteUpdates.set(paper.id, { favorite: result.favorite, revision: ++favoriteRevision })
      const displayed = items.value.find(item => item.id === paper.id)
      if (displayed) displayed.favorite = result.favorite
      if (props.view === 'favorites' && !result.favorite) {
        items.value = items.value.filter(item => item.id !== paper.id)
        total.value = Math.max(0, total.value - 1)
        void refresh(true, true)
      }
    }
  } catch (cause) { if (current()) uni.showToast({ title: errorMessage(cause), icon: 'none' }) }
  finally { if (current()) changing.delete(paper.id) }
}
function handleDownload(paper: PaperSummary) { openCatalogPaper(paper.id) }
function handleShare(paper: PaperSummary) {
  // #ifdef H5
  const path = safeDestination('/pages/paper/index?id=' + encodeURIComponent(paper.id))
  uni.setClipboardData({
    data: window.location.origin + window.location.pathname + '#' + path,
    success: () => uni.showToast({ title: '资料链接已复制', icon: 'none' }),
    fail: () => uni.showToast({ title: '复制失败，请重试', icon: 'none' }),
  })
  // #endif
}
defineExpose({ activate, deactivate, refresh, reload, rememberScroll: (top: number) => { scrollTop = top }, loadMore: () => refresh(false), shareTitle: computed(() => topicHeader.value?.title || '习题专题') })
function reconnect() { if (active && !changing.size) { void refresh(true, loaded); void loadMetadata(true) } }
function memoryWarning() {
  // 可见页面保留当前阅读位置；隐藏页释放行数据，下次进入重新核验权限。
  if (active) return
  items.value = []; summary.value = null; topics.value = []; tags.value = []
  metadataAt = 0; loaded = false; scrollTop = 0; nextOffset.value = windowStart.value
}
onMounted(() => { uni.$on?.('lc-network-restored', reconnect); uni.$on?.('lc-memory-warning', memoryWarning); void activate() })
onBeforeUnmount(() => { uni.$off?.('lc-network-restored', reconnect); uni.$off?.('lc-memory-warning', memoryWarning) })
onBeforeUnmount(deactivate)
</script>

<template>
  <view class="catalog-page" :class="{ 'has-tabbar': hasTabbar, 'batch-mode': selecting }">
    <view class="catalog-sticky">
      <PageChrome :back="!hasTabbar" fallback="/pages/account/index" />
      <view v-if="recordTitle && view !== 'favorites'" class="content-width record-heading">
        <view class="record-title-row">
          <text class="page-title">{{ recordTitle }}</text>
          <button
            v-if="view === 'recent' && canBrowse"
            class="section-link"
            hover-class="control-pressed"
            role="button"
            :disabled="loading || (!items.length && !filtered)"
            @click="clearRecent"
          >
            清空记录
          </button>
        </view>
        <text class="record-description">{{ recordDescription }}</text>
      </view>
      <view v-if="topicId" class="content-width topic-header">
        <text class="topic-page-title">{{ topicHeader?.title || '习题专题' }}</text>
        <text v-if="topicHeader?.description">{{ topicHeader.description }}</text>
        <text v-if="!loading && !metadataLoading && !metadataError && !error && canBrowse && !topicHeader">
          该专题已下架或暂不可用
        </text>
        <!-- #ifdef MP-WEIXIN -->
        <button
          hover-class="control-pressed"
          :hover-start-time="0"
          :hover-stay-time="80"
          v-if="topicHeader"
          class="section-link"
          open-type="share"
        >
          分享专题
        </button>
        <!-- #endif -->
      </view>
      <view class="catalog-band">
        <view class="content-width catalog-header">
          <view v-if="selecting" class="selection-heading"><text class="section-title">整理收藏</text><button class="section-link" role="checkbox" :aria-checked="allSelected" :disabled="batchBusy" @click="selectAll">{{ allSelected ? '取消全选' : '全选已加载' }}</button></view>
          <template v-else-if="canBrowse">
            <SearchGradeBar
              v-model="searchInput"
              :grade="grade"
              :placeholder="view === 'favorites' ? '搜索收藏' : view === 'downloads' ? '搜索下载记录' : '搜索习题'"
              @search="search()"
              @select-grade="gradeOpen = true"
            />
            <view class="catalog-tab-row">
              <view class="catalog-tabs">
                <wd-tabs :key="subjects.join('|')" v-model="subject" :slidable-num="4" :map-num="100" line-theme="text">
                  <wd-tab name="" title="全部" />
                  <wd-tab v-for="value in subjects" :key="value" :name="value" :title="value" />
                </wd-tabs>
              </view>
              <button
                hover-class="control-pressed"
                :hover-start-time="0"
                :hover-stay-time="80"
                class="bare-icon catalog-filter"
                :class="{ selected: filterCount }"
                role="button"
                aria-label="更多筛选"
                title="更多筛选"
                @click="filterOpen = true"
              >
                <wd-icon name="filter" size="19px" />
                <view v-if="filterCount" class="filter-dot" />
              </button>
            </view>
          </template>
        </view>
      </view>
    </view>
    <AuthGate
      v-if="!canBrowse"
      :title="view === 'favorites' ? '收藏好资料，下次接着练' : '登录查看使用记录'"
      description="登录后可同步收藏、分组和下载记录"
      browse
      @restored="activate"
    />
    <view v-else class="content-width catalog-body">
      <view v-if="metadataError" class="metadata-status" role="status">
        <text class="grow">{{ metadataError }}暂未加载，已显示的资料仍可使用</text>
        <button
          hover-class="control-pressed"
          :hover-start-time="0"
          :hover-stay-time="80"
          class="section-link"
          :disabled="metadataLoading"
          @click="loadMetadata(true)"
        >
          重试
        </button>
      </view>
      <view v-if="!selecting && !q && searches.length" class="search-history">
        <view class="history-heading">
          <text>最近搜索</text>
          <button
            hover-class="control-pressed"
            class="section-link"
            role="button"
            aria-label="清空搜索记录"
            @click="clearSearches"
          >
            清空
          </button>
        </view>
        <scroll-view class="history-scroll" scroll-x :show-scrollbar="false">
          <view class="history-track">
            <button
              hover-class="control-pressed"
              role="button"
              v-for="value in searches"
              :key="value"
              @click="search(value)"
            >
              {{ value }}
            </button>
          </view>
        </scroll-view>
      </view>
      <view v-if="!selecting" class="experience-toolbar">
        <view v-if="view === 'all' && !topicId" class="sort-buttons">
          <button
            hover-class="control-pressed"
            :hover-start-time="0"
            :hover-stay-time="80"
            role="button"
            v-for="item in sorts"
            :key="item.value"
            :class="{ selected: sort === item.value }"
            :aria-pressed="sort === item.value"
            @click="sort = item.value"
          >
            {{ item.label }}
          </button>
        </view>
        <button
          hover-class="control-pressed"
          :hover-start-time="0"
          :hover-stay-time="80"
          role="button"
          class="filter-free"
          :class="{ selected: onlyFree }"
          :aria-pressed="onlyFree"
          @click="onlyFree = !onlyFree"
        >
          仅免费
        </button>
        <picker
          v-if="topics.length && !topicId"
          class="topic-picker"
          :range="topicOptions.map((item) => item.title)"
          :value="
            Math.max(
              0,
              topicOptions.findIndex((item) => item.id === topic),
            )
          "
          @change="topic = topicOptions[Number($event.detail.value)]!.id"
        >
          <view class="topic-choice">
            <text class="topic-choice-label">
              {{ topicOptions.find((item) => item.id === topic)?.title || '全部专题' }}
            </text>
            <text class="topic-choice-arrow">▾</text>
          </view>
        </picker>
      </view>
      <FavoriteGroups
        ref="groupControl"
        v-if="view === 'favorites' && !selecting"
        :selected="favoriteGroup"
        @select="favoriteGroup = $event"
      />
      <view v-if="!selecting && (grade || category || chosenTags.length)" class="active-filters">
        <wd-tag v-if="grade" closable variant="light" type="primary" @close="grade = ''">{{ grade }}</wd-tag>
        <wd-tag v-if="category" closable variant="light" type="primary" @close="category = ''">
          {{ exerciseText(categoryName) || '已选分类' }}
        </wd-tag>
        <wd-tag v-for="tag in chosenTags" :key="tag.kind" closable variant="light" @close="tagFilters[tag.kind] = ''">
          {{ tag.name }}
        </wd-tag>
      </view>
      <view v-if="error" class="error-strip">
        <text class="grow">{{ error }}</text>
        <wd-button icon="refresh" type="danger" variant="text" role="button" aria-label="重试加载" @click="refresh()" />
      </view>
      <view class="list-caption">
        <text class="result-count">{{ loading && !appending ? '正在检索习题' : '共 ' + total + ' 份习题' }}</text>
        <button
          hover-class="control-pressed"
          :hover-start-time="0"
          :hover-stay-time="80"
          v-if="filtered && !selecting"
          class="section-link"
          role="button"
          aria-label="全部重置"
          @click="resetFilters"
        >
          <wd-icon name="close-circle" size="14px" />
          <text>全部重置</text>
        </button>
        <text v-else>
          {{
            topicId
              ? '专题顺序'
              : view === 'all'
                ? sort === 'latest'
                  ? '最新发布'
                  : sort === 'popular'
                    ? '热门习题'
                    : '精选优先'
                : view === 'downloads'
                  ? '最近下载'
                  : view === 'recent'
                    ? '最近浏览'
                    : '最近收藏'
          }}
        </text>
      </view>
      <view v-if="!selecting && (temporaryFilters || view === 'favorites' && items.length)" class="list-tools">
        <button v-if="temporaryFilters" class="section-link" role="button" aria-label="清除本次条件" @click="clearConditions"><wd-icon name="close" size="14px" /><text>清除本次条件</text></button>
        <button v-if="view === 'favorites' && items.length" class="section-link" role="button" aria-label="批量整理" :disabled="loading || changing.size > 0" @click="expandedRow = ''; selecting = true"><wd-icon name="edit" size="16px" /><text>批量整理</text></button>
      </view>
      <EnhancedSkeleton v-if="loading && !items.length" :count="4" type="row" />
      <view v-else-if="items.length" class="paper-list catalog-paper-list">
        <view v-for="paper in items" :key="paper.id" class="list-image-target" :data-paper-id="paper.id">
          <PaperRow
            :paper="paper"
            :active="imagesActive && (!observingImages || visibleImages.has(paper.id))"
            @open="rememberExplicitSearch(q)"
            :busy="batchBusy || changing.has(paper.id)"
            :selectable="selecting"
            :selected="selectedIds.includes(paper.id)"
            @select="toggleSelection(paper.id)"
            :expanded="expandedRow === paper.id"
            @expand="expandedRow = $event ? paper.id : ''"
            @favorite="favorite(paper)"
            @download="handleDownload(paper)"
            @share="handleShare(paper)"
          />
        </view>
      </view>
      <view v-else-if="!loading && !error" class="catalog-empty">
        <wd-empty
          :icon="filtered ? 'no-result' : view === 'favorites' ? 'no-collection' : 'no-content'"
          :tip="
            filtered
              ? '没有匹配的习题'
              : view === 'favorites'
                ? '还没有收藏的习题'
                : view === 'downloads'
                  ? '暂无下载记录'
                  : view === 'recent'
                    ? '暂无浏览记录'
                    : '新的习题正在准备中'
          "
        >
          <template #bottom>
            <text class="empty-guidance">
              {{
                q
                  ? '试试更短的关键词，或清除关键词继续浏览'
                  : filtered
                    ? '可以减少筛选条件，看看其他合适的练习'
                    : view === 'favorites'
                      ? '遇到喜欢的资料，点一下爱心就能留在这里'
                      : view === 'downloads'
                        ? '下载过的资料会显示在这里，方便再次查找'
                        : view === 'recent'
                          ? '看过的资料会留在这里，下次接着练'
                          : '可以先提交资料需求，让我们知道你想练什么'
              }}
            </text>
            <view v-if="filtered || view !== 'all'" class="empty-actions">
              <wd-button v-if="q" role="button" @click="search('')">清除关键词</wd-button>
              <wd-button v-if="filtered" variant="plain" role="button" @click="resetFilters">清除筛选</wd-button>
              <wd-button v-else variant="plain" icon="book" role="button" @click="openCatalog()">
                去习题库看看
              </wd-button>
            </view>
          </template>
        </wd-empty>
      </view>
      <view v-if="loading && items.length" class="loading-line">
        <wd-loading size="18px" />
        <text>正在加载</text>
      </view>
      <view v-if="view === 'all' && !loading && !error && !items.length" class="request-entry">
        <text>没有找到需要的资料？</text>
        <wd-button variant="plain" size="small" @click="openRequests({ q, grade, subject })">提交资料需求</wd-button>
      </view>
      <view v-else-if="appendError" class="error-strip" role="alert">
        <text class="grow">下一页加载失败，已加载的资料仍可查看</text>
        <wd-button variant="text" icon="refresh" @click="refresh(false)">重试下一页</wd-button>
      </view>
      <view v-else-if="more && !loading && !windowFull" class="loading-line">
        <wd-button variant="text" icon="down" role="button" :disabled="batchBusy" @click="refresh(false)">加载更多</wd-button>
      </view>
      <view v-else-if="items.length && !loading && !more" class="list-end">
        {{ windowStart ? '已到最后一组' : '已显示全部 ' + total + ' 份习题' }}
      </view>
      <view v-if="windowStart || windowFull" class="loading-line window-controls">
        <wd-button variant="plain" :disabled="loading || !windowStart" @click="turnWindow(-1)">上一组</wd-button>
        <text>{{ nextOffset > windowStart ? windowStart + 1 + '–' + nextOffset : '等待加载' }} / {{ total }}</text>
        <wd-button variant="plain" :disabled="loading || !windowFull || !more" @click="turnWindow(1)">下一组</wd-button>
      </view>
    </view>
    <GradePicker
      :open="gradeOpen"
      :value="grade"
      :options="summary?.grades || []"
      @close="gradeOpen = false"
      @select="grade = $event"
    />
    <CatalogFilterSheet
      :open="filterOpen"
      :grade="grade"
      :category="category"
      :grades="summary?.grades || []"
      :categories="summary?.categories || []"
      :tags="tags"
      :tag-filters="tagFilters"
      @close="filterOpen = false"
      @apply="applyFilters"
    />
    <AppTabBar v-if="hasTabbar" :current="view === 'favorites' ? 'favorites' : 'library'" />
    <FavoriteBatchActions v-if="selecting" :ids="selectedIds" @busy="batchBusy = $event" @completed="batchCompleted" @close="endSelection" @refresh="refresh()" />
  </view>
</template>


<style scoped src="./CatalogList.scss"></style>
