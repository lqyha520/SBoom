<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { onHide, onPullDownRefresh, onShow, onUnload, onShareAppMessage, onShareTimeline } from '@dcloudio/uni-app'
import AppTabBar from '../../components/AppTabBar.vue'
import PageChrome from '../../components/PageChrome.vue'
import HomeBanner from '../../components/HomeBanner.vue'
import NoticeBar from '../../components/NoticeBar.vue'
import NoticePopup from '../../components/NoticePopup.vue'
import PaperCard from '../../components/PaperCard.vue'
import TopicCard from '../../components/TopicCard.vue'
import EnhancedSkeleton from '../../components/EnhancedSkeleton.vue'
import SearchGradeBar from '../../components/SearchGradeBar.vue'
import GradePicker from '../../components/GradePicker.vue'
import { errorMessage, favoriteCatalogPaper, fetchCatalog, fetchCatalogSummary, fetchSiteHome } from '../../services/api'
import { ensureSession, requireLogin, session } from '../../services/session'
import { rememberPaperIntent } from '../../services/paper-intent'
import { openCatalog } from '../../services/navigation'
import { createLatestRequest } from '../../services/latest-request'
import { exerciseText, homeSelection, subjectTone } from '../../presentation'
import { fetchTopics, type Topic } from '../../services/experience'
import { readPreferences, rememberSearch, writePreferences } from '../../services/preferences'
import type { CatalogSummary, PaperSummary, SiteCategory, SiteHome } from '../../types'
import { refreshUnread } from '../../services/growth'
import { categoryIcon } from '../../services/category-icons'
import { shareCard, shareTimeline } from '../../services/return-route'
import { captureScroll } from '../../services/page-lifecycle'

const items = ref<PaperSummary[]>([])
const recentPaper = ref<PaperSummary | null>(null)
const total = ref(0)
const loaded = ref(false)
const summary = ref<CatalogSummary | null>(null)
const site = ref<SiteHome | null>(null)
const q = ref('')
const grade = ref('')
const collections = ref<Topic[]>([])
const feed = ref<'featured' | 'latest'>('featured')
const offset = ref(0)
const loading = ref(true)
const contentLoading = ref(true)
const changing = ref('')
const error = ref('')
const contentError = ref('')
const gradePicker = ref(false)
const cards = computed(() => homeSelection(items.value, offset.value))
const banners = computed(() => site.value?.banners || [])
const notices = computed(() => site.value?.notices.banner || [])
const popups = computed(() => site.value?.notices.popup || [])
const grades = computed(() => site.value?.dictionaries.grades || summary.value?.grades || [])
const subjectIcons: Record<string, string> = { 语文: 'book', 数学: 'formula', 英语: 'translate' }
const subjects = computed(() => {
  const names = (site.value?.dictionaries.subjects || summary.value?.subjects || []).slice(0, 3)
  const resolved = names.length ? names : ['语文', '数学', '英语']
  return [...resolved.map(name => ({ label: name, icon: subjectIcons[name] || 'book', tone: subjectTone(name), subject: name })),
    { label: '全部学科', icon: 'apps', tone: 'all-subjects', subject: '' }]
})
const categories = computed<SiteCategory[]>(() => (summary.value?.categories || []).slice(0, 4))
const paperRequests = createLatestRequest()
const contentRequests = createLatestRequest()
const favoriteRequests = createLatestRequest()
let active = true
let activation = 0
let scrollTop = 0
let gradeChosen = false
let papersKey = ''
const imagesActive = ref(false)
let firstContentAt = 0
let contentMetric: 'home_cold' | 'home_warm' = 'home_cold'
async function recordContentReady() {
  if (!firstContentAt) return
  const startedAt = firstContentAt, kind = contentMetric, run = activation
  firstContentAt = 0
  await nextTick()
  if (active && activation === run) uni.$emit?.('lc-performance', { kind, value: Date.now() - startedAt })
}

async function loadPapers(reset = false, anonymous = !session.ready || !!session.error) {
  if (!active) return
  const current = paperRequests.begin()
  loading.value = true; error.value = ''
  const key = JSON.stringify([grade.value, feed.value])
  reset = reset || key !== papersKey
  papersKey = key
  if (reset) { items.value = []; total.value = 0; loaded.value = false; offset.value = 0 }
  const firstVisible = cards.value[0]?.id
  try {
    const result = await fetchCatalog({ limit: 12, grade: grade.value, sort: feed.value }, { scope: current, anonymous })
    if (current()) {
      const previous = result.items.findIndex(item => item.id === firstVisible)
      items.value = result.items; total.value = result.total ?? result.items.length; loaded.value = true
      offset.value = previous >= 0 ? previous : 0
      imagesActive.value = true
      void recordContentReady()
    }
  } catch (cause) { if (current()) error.value = errorMessage(cause) }
  finally { if (current()) loading.value = false }
}
async function loadContent(force = false, anonymous = !session.ready || !!session.error) {
  if (!active) return
  const current = contentRequests.begin()
  contentLoading.value = true; contentError.value = ''
  // Each result can appear immediately; an unavailable optional section must
  // not prevent the catalog, search or other home sections from being used.
  const results = await Promise.allSettled([
    fetchSiteHome({ scope: current, force, anonymous }).then(home => { if (current()) site.value = home }),
    fetchCatalogSummary({ scope: current, force, anonymous }).then(counts => { if (current()) summary.value = counts }),
    fetchTopics({ scope: current, force, anonymous }).then(curated => { if (current()) collections.value = curated.items }),
    !anonymous && session.user ? fetchCatalog({ recent: true, limit: 1 }, { scope: current }).then(result => { if (current()) recentPaper.value = result.items[0] || null }).catch(() => {}) : Promise.resolve(),
  ])
  if (!current()) return
  const labels = ['首页推荐', '分类', '专题']
  contentError.value = results.flatMap((result, index) => result.status === 'rejected' ? [labels[index]] : []).join('、')
  contentLoading.value = false
}
async function load(force = false, anonymous = !session.ready || !!session.error) {
  if (!active || changing.value) { uni.stopPullDownRefresh(); return }
  await Promise.allSettled([loadPapers(false, anonymous), loadContent(force, anonymous), !anonymous && session.user ? refreshUnread({ force }).catch(() => {}) : Promise.resolve()])
  if (active) uni.stopPullDownRefresh()
}
async function favorite(paper: PaperSummary) {
  if (loading.value || changing.value) return
  if (!session.user) rememberPaperIntent({ paperId: paper.id, action: 'favorite', edition: 'original' })
  if (!requireLogin('/pages/paper/index?id=' + encodeURIComponent(paper.id))) return
  const current = favoriteRequests.begin()
  changing.value = paper.id
  try {
    const result = await favoriteCatalogPaper(paper.id, !paper.favorite)
    if (current()) {
      paper.favorite = result.favorite
      if (summary.value) summary.value.favorites = Math.max(0, summary.value.favorites + (result.favorite ? 1 : -1))
      uni.showToast({ title: result.favorite ? '已收藏' : '已取消收藏', icon: 'none' })
    }
  } catch (cause) { if (current()) uni.showToast({ title: errorMessage(cause), icon: 'none' }) }
  finally { if (current()) changing.value = '' }
}
function search() {
  if (session.user && q.value.trim()) writePreferences(session.user.id, rememberSearch(readPreferences(session.user.id), q.value))
  openCatalog({ q: q.value, grade: grade.value })
}
function byGrade(next: string) {
  if (changing.value) return
  gradePicker.value = false
  if (grade.value === next) return
  gradeChosen = true
  grade.value = next
  if (session.user) writePreferences(session.user.id, { ...readPreferences(session.user.id), grade: next })
  scrollTop = 0
  void loadPapers(true, !session.ready || !!session.error)
}
function selectFeed(value: 'featured' | 'latest') {
  if (value === feed.value || changing.value) return
  feed.value = value; scrollTop = 0; void loadPapers(true, !session.ready || !!session.error)
}
function clearGrade() { byGrade('') }
function invalidate() { paperRequests.invalidate(); contentRequests.invalidate(); favoriteRequests.invalidate() }
watch(() => session.user?.id, (owner, previous) => {
  // 首次登录恢复保留用户已经输入的搜索和筛选，公开结果随后重新核验。
  if (!previous && owner) return
  invalidate(); recentPaper.value = null; items.value = []; total.value = 0; loaded.value = false; summary.value = null; site.value = null; collections.value = []
  error.value = ''; contentError.value = ''; loading.value = false; contentLoading.value = false; changing.value = ''
  q.value = ''; grade.value = ''; gradePicker.value = false; offset.value = 0
  scrollTop = 0; imagesActive.value = false; gradeChosen = false
  if (active && previous) void load()
}, { flush: 'sync' })
onShow(async () => {
  active = true
  contentMetric = loaded.value ? 'home_warm' : 'home_cold'
  firstContentAt = Date.now()
  const run = ++activation
  const restoring = !session.ready || !!session.error
  const restored = ensureSession()
  if (session.user && !gradeChosen) grade.value = readPreferences(session.user.id).grade
  void load(false, restoring)
  await nextTick()
  if (active && run === activation && loaded.value) void recordContentReady()
  if (active && run === activation && scrollTop) uni.pageScrollTo?.({ scrollTop, duration: 0 })
  await restored
  if (active && run === activation && restoring && session.user) {
    if (!gradeChosen) grade.value = readPreferences(session.user.id).grade
    else writePreferences(session.user.id, { ...readPreferences(session.user.id), grade: grade.value })
    void load()
  }
})
function leave() { active = false; activation++; imagesActive.value = false; invalidate(); loading.value = false; contentLoading.value = false; changing.value = ''; gradePicker.value = false; uni.stopPullDownRefresh() }
onHide(() => {
  leave()
  const owner = session.user?.id, run = activation
  captureScroll(top => { if (run === activation && owner === session.user?.id) scrollTop = top })
})
function reconnect() { if (active && !changing.value) void load(true) }
uni.$on?.('lc-network-restored', reconnect)
function memoryWarning() {
  if (active) return
  items.value = []; loaded.value = false; recentPaper.value = null; site.value = null; summary.value = null; collections.value = []
}
uni.$on?.('lc-memory-warning', memoryWarning)
onUnload(() => { leave(); uni.$off?.('lc-network-restored', reconnect); uni.$off?.('lc-memory-warning', memoryWarning) })
onPullDownRefresh(() => load(true))
onShareAppMessage(() => shareCard('home'))
onShareTimeline(() => shareTimeline())
</script>

<template>
  <view class="home-page has-tabbar">
    <PageChrome />
    <view class="content-width home-search-row"><SearchGradeBar v-model="q" :grade="grade" placeholder="搜知识点、习题" :disabled="!!changing" @search="search" @select-grade="gradePicker = true" /></view>
    <HomeBanner :banners="banners" :mode="site?.banner_mode || 'welcome'" :grade="grade" :recent="recentPaper" :loading="contentLoading && !site" :active="imagesActive" @select-grade="gradePicker = true" />
    <view class="content-width home-subjects">
      <view class="subject-card">
        <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-for="item in subjects" :key="item.label" class="subject-entry" role="button" :aria-label="item.subject ? item.label + '习题' : '全部习题'" @click="openCatalog({ subject: item.subject, grade })"><view class="subject-symbol" :class="item.tone"><wd-icon :name="item.icon" size="23px" /></view><text class="subject-label">{{ item.label }}</text></button>
      </view>
    </view>
    <NoticeBar :notices="notices" />
    <view v-if="contentError" class="content-width"><view class="home-status" role="status"><text class="grow">{{ contentError }}暂时加载失败</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="section-link" :disabled="contentLoading" @click="loadContent(true)">{{ contentLoading ? '加载中' : '重试' }}</button></view></view>
      <view class="content-width home-feed">
        <view class="feed-heading">
          <view class="feed-title-row">
            <view class="feed-title-group">
              <text class="feed-title">为你精选</text>
              <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-if="items.length > 2" class="change-papers" :disabled="loading || !!changing" role="button" aria-label="换一组习题" @click="offset += 2"><wd-icon name="refresh" size="13px" /><text>换一组</text></button>
            </view>
            <view class="feed-switch" aria-role="group" role="group" aria-label="精选方式">
              <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="feed-tab" :class="{ active: feed === 'featured' }" :aria-pressed="feed === 'featured'" role="button" aria-label="为你精选" @click="selectFeed('featured')"><text>精选</text><view class="feed-tab-mark" aria-hidden="true" /></button>
              <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="feed-tab" :class="{ active: feed === 'latest' }" :aria-pressed="feed === 'latest'" role="button" aria-label="最近上新" @click="selectFeed('latest')"><text>上新</text><view class="feed-tab-mark" aria-hidden="true" /></button>
            </view>
          </view>
        </view>
        <view v-if="error" class="error-strip" role="status"><text class="grow">{{ error }}</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="section-link retry-papers" role="button" :disabled="loading" aria-label="重试加载习题" @click="loadPapers()">{{ loading ? '加载中' : '重试' }}</button></view>
        <EnhancedSkeleton v-if="loading && !items.length" :count="2" type="card" />
        <template v-else-if="cards.length">
          <view class="home-cards">
            <PaperCard :active="imagesActive"
              v-for="paper in cards"
              :key="paper.id"
              :paper="paper"
              :busy="loading || !!changing || !session.ready"
              @favorite="favorite(paper)"
            />
          </view>
          <view v-if="total > items.length" class="feed-all">
            <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" :aria-label="'查看全部 ' + total + ' 份习题'" @click="openCatalog({ grade })"><text>查看全部 {{ total }} 份习题</text><wd-icon name="arrow-right" size="13px" /></button>
          </view>
        </template>
        <view v-else-if="!loading && !error" class="home-empty"><view class="empty-symbol"><wd-icon name="book" size="28px" /></view><text class="empty-title">{{ grade ? '这个年级的练习还在准备中' : '新的练习正在准备中' }}</text><text class="empty-caption">{{ grade ? '换个年级，看看其他练习吧' : '稍后再来，或去习题库逛逛' }}</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="empty-link" role="button" @click="grade ? clearGrade() : openCatalog()">{{ grade ? '查看全部年级' : '进入习题库' }}<wd-icon name="arrow-right" size="14px" /></button></view>
      </view>
      <view v-if="categories.length" class="content-width home-categories">
        <view class="section-heading"><view class="section-head"><text class="section-title">按需练习</text><text class="section-caption">按场景快速找题</text></view></view>
        <view class="category-grid"><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-for="(category, index) in categories" :key="category.id" class="category-entry" role="button" @click="openCatalog({ category: category.id, grade })"><view class="category-symbol" :class="'category-tone-' + index"><wd-icon :name="categoryIcon(category.icon, index % 2 ? 'copy' : 'edit')" size="20px" /></view><view class="grow category-copy"><text class="category-title">{{ exerciseText(category.name) }}</text><text class="category-caption">{{ category.paper_count ? category.paper_count + ' 份练习' : '打开看看' }}</text></view><wd-icon class="category-arrow" name="arrow-right" size="12px" /></button></view>
      </view>
      <view v-if="collections.length" class="home-collections">
        <view class="content-width section-heading"><view class="section-head"><text class="section-title">专题合集</text><text class="section-caption">围绕一个主题，成体系地练</text></view><text v-if="collections.length > 1" class="swipe-hint">左右滑动</text></view>
        <scroll-view class="collection-scroll" scroll-x :show-scrollbar="false"><view class="collection-track"><TopicCard v-for="(collection, index) in collections" :key="collection.id" :topic="collection" :index="index" /></view></scroll-view>
      </view>
    <AppTabBar current="home" />
    <NoticePopup :notices="popups" />
    <GradePicker :open="gradePicker" :value="grade" :options="grades" @close="gradePicker = false" @select="byGrade" />
  </view>
</template>

<style scoped>
.home-page { background: var(--lc-canvas); }
.home-search-row { padding-top: 12px; padding-bottom: 12px; }
.home-subjects { padding-top: 12px; padding-bottom: 4px; animation: fade-in 0.4s ease-out; }
.subject-card { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 2px; padding: 11px 8px 10px; border: 1px solid var(--lc-card-line); border-radius: 16px; background: var(--lc-card); box-shadow: var(--lc-card-shadow-soft); }
.subject-entry { display: flex; flex-direction: column; align-items: center; gap: 7px; min-width: 0; width: 100%; margin: 0; padding: 0; border: 0; border-radius: 12px; background: transparent; font-size: 13px; font-weight: 500; line-height: 1.5; color: var(--lc-secondary); }
.subject-label { display: block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.subject-symbol { display: flex; align-items: center; justify-content: center; width: 44px; height: 44px; border-radius: 14px; color: var(--subject-color); background: var(--subject-tint); transition: transform .18s ease, box-shadow .18s ease; }
.subject-entry:active .subject-symbol { transform: scale(.94); }
@media (hover:hover) { .subject-entry:hover .subject-symbol { transform: translateY(-2px); box-shadow: 0 4px 10px #23392d12; } }
.all-subjects { --subject-color: #68764f; --subject-tint: #eef1e2; }
.home-status { display: flex; align-items: center; gap: 10px; padding: 0 12px; margin-bottom: 18px; border-radius: 12px; background: #fff4dc; color: #80612b; font-size: 13px; }
.home-status .section-link { color: #80612b; }
.home-feed { padding-top: 22px; }
.feed-heading { margin-bottom: 12px; }
.feed-title-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.feed-title-group { display: flex; align-items: center; gap: 10px; min-width: 0; }
.feed-title { flex: none; font-size: 18px; font-weight: 650; line-height: 1.4; color: var(--lc-text); letter-spacing: .1px; }
.feed-switch { display: flex; align-items: center; gap: 2px; flex: none; margin-right: -8px; }
.feed-tab { position: relative; display: flex; align-items: center; justify-content: center; min-width: 44px; min-height: 36px; margin: 0; padding: 0 8px; border: 0; background: transparent; color: var(--lc-secondary); font-size: 13.5px; font-weight: 500; line-height: 1; letter-spacing: .2px; transition: color .16s ease, opacity .16s ease; }
.feed-tab.active { color: var(--lc-primary); font-weight: 650; }
.feed-tab-mark { position: absolute; left: 50%; bottom: 7px; width: 14px; height: 2px; margin-left: -7px; border-radius: 2px; background: var(--lc-primary); opacity: 0; transform: scaleX(.5); transition: opacity .16s ease, transform .16s ease; }
.feed-tab.active .feed-tab-mark { opacity: 1; transform: scaleX(1); }
.change-papers { display: inline-flex; align-items: center; justify-content: center; gap: 5px; flex: none; min-height: 30px; margin: 0; padding: 0 10px; border: 1px solid var(--lc-card-line); border-radius: 999px; background: var(--lc-surface); color: var(--lc-secondary); font-size: 12px; line-height: 1; }
.change-papers:active { border-color: #c9dbce; color: var(--lc-primary); }
.change-papers[disabled] { opacity: .5; }
.home-cards { display: flex; flex-direction: column; gap: 10px; }
.feed-all { display: flex; justify-content: center; padding-top: 12px; }
.feed-all button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 42px; margin: 0; padding: 0 22px; border: 0; border-radius: 999px; background: var(--lc-primary-soft); color: var(--lc-primary); font-size: 13px; font-weight: 600; line-height: 1; }
.retry-papers { color: #a34040; flex: none; }
.home-empty { display: flex; flex-direction: column; align-items: center; padding: 27px 16px 15px; background: var(--lc-card); border: 1px solid var(--lc-card-line); border-radius: 16px; }
.empty-symbol { display: flex; align-items: center; justify-content: center; width: 56px; height: 56px; margin-bottom: 14px; border-radius: 18px; background: #eef4ee; color: #7d9b81; }
.empty-title { font-size: 14px; font-weight: 600; color: #435948; }
.empty-caption { margin-top: 6px; font-size: 13px; color: var(--lc-muted); }
.empty-link { display: inline-flex; align-items: center; gap: 7px; min-height: 40px; margin: 14px 0 0; padding: 0 20px; border-radius: 999px; background: var(--lc-primary-soft); font-size: 13px; font-weight: 600; color: var(--lc-primary); }
.home-categories { padding-top: 26px; }
.home-categories .section-heading, .home-collections .section-heading { margin-bottom: 12px; align-items: flex-end; }
.section-head { min-width: 0; }
.home-categories .section-title, .home-collections .section-title { display: block; font-size: 18px; font-weight: 650; line-height: 1.4; color: var(--lc-text); }
.section-caption { display: block; margin-top: 4px; font-size: 12px; line-height: 1.5; color: var(--lc-muted); }
.category-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; animation: slide-up 0.5s ease-out; }
.category-entry { display: flex; align-items: center; gap: 10px; min-width: 0; min-height: 74px; margin: 0; padding: 12px; border: 1px solid var(--lc-card-line); border-radius: 16px; background: var(--lc-card); box-shadow: var(--lc-card-shadow-soft); font-size: 13px; text-align: left; line-height: 1.5; transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease; }
.category-entry:active { transform: scale(.98); border-color: #c5d8c4; }
@media (hover:hover) { .category-entry:hover { border-color: #c9ddcc; box-shadow: var(--lc-card-shadow); } }
.category-symbol { display: flex; align-items: center; justify-content: center; flex: none; width: 40px; height: 40px; border-radius: 13px; background: var(--category-bg, #f7efe0); color: var(--category-ink, #8a6a32); }
.category-tone-0 { --category-bg: #f7efe0; --category-ink: #8a6a32; }
.category-tone-1 { --category-bg: #eaf0f8; --category-ink: #52709c; }
.category-tone-2 { --category-bg: #eaf3ec; --category-ink: #4c7a5c; }
.category-tone-3 { --category-bg: #f8ece6; --category-ink: #a86650; }
.category-copy { display: flex; flex-direction: column; justify-content: center; }
.category-title { display: block; color: var(--lc-text); font-size: 14px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.category-caption { display: block; margin-top: 3px; color: var(--lc-muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.category-arrow { flex: none; color: #a3b0a6; transition: transform .18s ease, color .18s ease; }
@media (hover:hover) { .category-entry:hover .category-arrow { transform: translateX(1px); color: #7e9a85; } }
.home-collections { padding-top: 28px; }
.swipe-hint { flex: none; font-size: 11.5px; color: var(--lc-muted); }
.collection-scroll { width: 100%; }
.collection-track { display: flex; gap: 12px; padding: 0 var(--lc-page-gutter) 8px; animation: slide-up 0.6s ease-out; }
@keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes slide-up { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
@media (max-height:680px) { .home-search-row { padding-top:8px;padding-bottom:8px; }.home-subjects { padding-top:8px; }.subject-card { padding:9px 8px 8px; }.subject-symbol { width:40px;height:40px;border-radius:13px; }.home-feed { padding-top:18px; } }
@media (max-width: 359px) { .home-cards { gap: 8px; } .feed-switch { margin-right: -7px; } .feed-tab { min-width: 42px; padding: 0 7px; font-size: 13px; } .category-grid { gap: 8px; } .category-entry { gap: 8px; padding: 10px; } .category-symbol { width: 36px; height: 36px; border-radius: 12px; } .category-arrow { display: none; } .collection-track { padding-left: 16px; padding-right: 16px; } .collection-card { width: 235px; } }
@media (prefers-reduced-motion: reduce) { .home-subjects, .category-grid, .collection-track { animation: none; } .feed-tab { transition: none; } }
</style>
