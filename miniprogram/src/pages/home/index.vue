<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onHide, onPullDownRefresh, onShow, onUnload, onShareAppMessage } from '@dcloudio/uni-app'
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
import { openCatalog } from '../../services/navigation'
import { createLatestRequest } from '../../services/latest-request'
import { exerciseText, homeSelection, subjectTone } from '../../presentation'
import { fetchTopics, type Topic } from '../../services/experience'
import { readPreferences, rememberSearch, writePreferences } from '../../services/preferences'
import type { CatalogSummary, PaperSummary, SiteCategory, SiteHome } from '../../types'
import { refreshUnread } from '../../services/growth'
import { shareCard } from '../../services/return-route'

const items = ref<PaperSummary[]>([])
const recentPaper = ref<PaperSummary | null>(null)
const total = ref(0)
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
const feedCaption = computed(() => grade.value ? grade.value + ' · ' + total.value + ' 份练习' : '发现适合你的下一份练习')
const paperRequests = createLatestRequest()
const contentRequests = createLatestRequest()
const favoriteRequests = createLatestRequest()
let active = true
const imagesActive = ref(false)

async function loadPapers(reset = false) {
  if (!active || changing.value) return
  const current = paperRequests.begin()
  loading.value = true; error.value = ''
  if (reset) { items.value = []; total.value = 0; offset.value = 0 }
  try {
    const result = await fetchCatalog({ limit: 12, grade: grade.value, sort: feed.value }, { scope: current })
    if (current()) { items.value = result.items; total.value = result.total; offset.value = 0 }
  } catch (cause) { if (current()) error.value = errorMessage(cause) }
  finally { if (current()) loading.value = false }
}
async function loadContent(force = false) {
  if (!active) return
  const current = contentRequests.begin()
  contentLoading.value = true; contentError.value = ''
  // Each result can appear immediately; an unavailable optional section must
  // not prevent the catalog, search or other home sections from being used.
  const results = await Promise.allSettled([
    fetchSiteHome({ scope: current, force }).then(home => { if (current()) site.value = home }),
    fetchCatalogSummary({ scope: current }).then(counts => { if (current()) summary.value = counts }),
    fetchTopics({ scope: current, force }).then(curated => { if (current()) collections.value = curated.items }),
    session.user ? fetchCatalog({ recent: true, limit: 1 }, { scope: current }).then(result => { if (current()) recentPaper.value = result.items[0] || null }).catch(() => {}) : Promise.resolve(),
  ])
  if (!current()) return
  const labels = ['首页推荐', '分类', '专题']
  contentError.value = results.flatMap((result, index) => result.status === 'rejected' ? [labels[index]] : []).join('、')
  contentLoading.value = false
}
async function load(force = false) {
  if (!active || changing.value) { uni.stopPullDownRefresh(); return }
  await Promise.allSettled([loadPapers(), loadContent(force)])
  if (active) uni.stopPullDownRefresh()
  if (active && session.user) void refreshUnread().catch(() => {})
}
async function favorite(paper: PaperSummary) {
  if (loading.value || changing.value) return
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
  gradePicker.value = false
  if (grade.value === next) return
  grade.value = next
  if (session.user) writePreferences(session.user.id, { ...readPreferences(session.user.id), grade: next })
  void loadPapers(true)
}
function selectFeed(value: 'featured' | 'latest') {
  if (value === feed.value || loading.value || changing.value) return
  feed.value = value; void loadPapers(true)
}
function clearGrade() { byGrade('') }
function invalidate() { paperRequests.invalidate(); contentRequests.invalidate(); favoriteRequests.invalidate() }
watch(() => session.user?.id, (owner, previous) => {
  invalidate(); recentPaper.value = null; items.value = []; total.value = 0; summary.value = null; site.value = null; collections.value = []
  error.value = ''; contentError.value = ''; loading.value = false; contentLoading.value = false; changing.value = ''
  q.value = ''; grade.value = ''; gradePicker.value = false; offset.value = 0
  if (active && previous && !owner) void load()
}, { flush: 'sync' })
onShow(async () => {
  active = true
  await ensureSession()
  if (active) {
    imagesActive.value = true
    if (session.user) grade.value = readPreferences(session.user.id).grade
    void load()
  }
})
function leave() { active = false; imagesActive.value = false; invalidate(); loading.value = false; contentLoading.value = false; changing.value = ''; gradePicker.value = false; uni.stopPullDownRefresh() }
onHide(leave)
function reconnect() { if (active && !changing.value) void load(true) }
uni.$on?.('lc-network-restored', reconnect)
function memoryWarning() {
  if (active) return
  items.value = []; recentPaper.value = null; site.value = null; summary.value = null; collections.value = []
}
uni.$on?.('lc-memory-warning', memoryWarning)
onUnload(() => { leave(); uni.$off?.('lc-network-restored', reconnect); uni.$off?.('lc-memory-warning', memoryWarning) })
onPullDownRefresh(() => load(true))
onShareAppMessage(() => shareCard('home'))
</script>

<template>
  <view class="home-page has-tabbar">
    <PageChrome />
    <view class="content-width home-search-row"><SearchGradeBar v-model="q" :grade="grade" placeholder="搜知识点、习题" :disabled="loading || !!changing" @search="search" @select-grade="gradePicker = true" /></view>
    <HomeBanner :banners="banners" :grade="grade" :recent="recentPaper" :loading="contentLoading" :active="imagesActive" />
    <view class="content-width home-subjects">
      <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-for="item in subjects" :key="item.label" class="subject-entry" role="button" :aria-label="item.subject ? item.label + '习题' : '全部习题'" @click="openCatalog({ subject: item.subject, grade })"><view class="subject-symbol" :class="item.tone"><wd-icon :name="item.icon" size="24px" /></view><text>{{ item.label }}</text></button>
    </view>
    <NoticeBar :notices="notices" />
    <view v-if="contentError" class="content-width"><view class="home-status" role="status"><text class="grow">{{ contentError }}暂时加载失败</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="section-link" :disabled="contentLoading" @click="loadContent(true)">{{ contentLoading ? '加载中' : '重试' }}</button></view></view>
    <template v-if="session.ready">
      <view class="content-width home-feed">
        <view class="section-heading feed-heading">
          <view class="feed-tabs"><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" :class="{ active: feed === 'featured' }" :aria-pressed="feed === 'featured'" :disabled="loading || !!changing" role="button" @click="selectFeed('featured')">为你精选</button><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" :class="{ active: feed === 'latest' }" :aria-pressed="feed === 'latest'" :disabled="loading || !!changing" role="button" @click="selectFeed('latest')">最近上新</button></view>
          <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-if="items.length > 2" class="change-papers" :disabled="loading || !!changing" role="button" aria-label="换一组习题" @click="offset += 2"><wd-icon name="refresh" size="14px" /><text>换一组</text></button>
        </view>
        <text class="feed-caption">{{ feedCaption }}</text>
        <view v-if="error" class="error-strip" role="status"><text class="grow">{{ error }}</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="section-link retry-papers" role="button" :disabled="loading" aria-label="重试加载习题" @click="loadPapers()">{{ loading ? '加载中' : '重试' }}</button></view>
        <EnhancedSkeleton v-if="loading && !items.length" :count="2" type="card" />
        <transition-group v-else-if="cards.length" name="list" tag="view" class="home-cards">
          <PaperCard :active="imagesActive"
            v-for="paper in cards" 
            :key="paper.id" 
            :paper="paper" 
            :busy="loading || !!changing" 
            @favorite="favorite(paper)" 
          />
        </transition-group>
        <view v-else-if="!loading && !error" class="home-empty"><view class="empty-symbol"><wd-icon name="book" size="28px" /></view><text class="empty-title">{{ grade ? '这个年级的练习还在准备中' : '新的练习正在准备中' }}</text><text class="empty-caption">{{ grade ? '换个年级，看看其他练习吧' : '稍后再来，或去习题库逛逛' }}</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="empty-link" role="button" @click="grade ? clearGrade() : openCatalog()">{{ grade ? '查看全部年级' : '进入习题库' }}<wd-icon name="arrow-right" size="14px" /></button></view>
      </view>
      <view v-if="categories.length" class="content-width home-categories">
        <view class="section-heading"><text class="section-title">按需练习</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="section-link" role="button" @click="openCatalog({ grade })">全部习题<wd-icon name="arrow-right" size="14px" /></button></view>
        <view class="category-grid"><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-for="(category, index) in categories" :key="category.id" class="category-entry" role="button" @click="openCatalog({ category: category.id, grade })"><view class="category-symbol" :class="'category-tone-' + index"><wd-icon :name="category.icon || (index % 2 ? 'copy' : 'edit')" size="21px" /></view><view class="grow"><text class="category-title">{{ exerciseText(category.name) }}</text><text class="category-caption">{{ category.description || (category.paper_count ? category.paper_count + ' 份练习' : '打开看看') }}</text></view><wd-icon name="arrow-right" size="12px" color="#91a094" /></button></view>
      </view>
      <view v-if="collections.length" class="home-collections">
        <view class="content-width section-heading"><view><text class="section-title">专题合集</text><text class="section-caption">围绕一个主题，系统练一练</text></view><text v-if="collections.length > 1" class="swipe-hint">左右滑动</text></view>
        <scroll-view class="collection-scroll" scroll-x :show-scrollbar="false"><view class="collection-track"><TopicCard v-for="(collection, index) in collections" :key="collection.id" :topic="collection" :index="index" /></view></scroll-view>
      </view>
      <view v-if="!contentLoading || categories.length || collections.length" class="content-width home-more"><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="all-papers" role="button" @click="openCatalog({ grade })"><view><text class="all-papers-title">还想练点什么？</text><text class="all-papers-caption">去习题库，找到更多好练习</text></view><view class="all-papers-arrow"><wd-icon name="arrow-right" size="20px" /></view></button></view>
    </template>
    <AppTabBar current="home" />
    <NoticePopup :notices="popups" />
    <GradePicker :open="gradePicker" :value="grade" :options="grades" @close="gradePicker = false" @select="byGrade" />
  </view>
</template>

<style scoped>
.home-page { background: var(--lc-canvas); }
.home-search-row { padding-top: 12px; padding-bottom: 12px; }
.home-subjects { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; padding-top: 14px; padding-bottom: 16px; animation: fade-in 0.4s ease-out; }
.subject-entry { display: flex; flex-direction: column; align-items: center; gap: 8px; min-width: 0; width: 100%; margin: 0; padding: 0; background: transparent; font-size: 12px; line-height: 1.5; color: #374c3d; }
.subject-entry > text { display: block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.subject-symbol { display: flex; align-items: center; justify-content: center; width: 50px; height: 50px; border-radius: 17px; color: var(--subject-color); background: var(--subject-tint); transition: transform .18s ease, box-shadow .18s ease; }
.subject-entry:active .subject-symbol { transform: scale(.94); box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
@media (hover:hover) { .subject-entry:hover .subject-symbol { transform: translateY(-2px); box-shadow: var(--lc-card-shadow-soft); } }
.all-subjects { --subject-color: #777951; --subject-tint: #eeefdf; }
.home-status { display: flex; align-items: center; gap: 10px; padding: 0 12px; margin-bottom: 18px; border-radius: 10px; background: #fff4dc; color: #80612b; font-size: 12px; }
.home-status .section-link { color: #80612b; }
.home-feed { padding-top: 0; }
.feed-heading { margin-bottom: 0; gap: 8px; }
.feed-tabs { display: flex; align-items: center; gap: 20px; }
.feed-tabs button { position: relative; min-height: 44px; margin: 0; padding: 6px 0; border-radius: 0; font-size: 15px; font-weight: 500; line-height: 1.5; color: var(--lc-muted); background: transparent; }
.feed-tabs button.active { font-size: 18px; font-weight: 650; color: #2b4131; }
.feed-tabs button.active::before { content: ''; position: absolute; left: 0; bottom: 0; width: 20px; height: 3px; border-radius: 99px; background: var(--lc-primary); }
.change-papers { display: flex; align-items: center; justify-content: flex-end; gap: 4px; flex: none; min-height: 44px; margin: 0; padding: 0; background: transparent; font-size: 12px; line-height: 1.5; color: #617d67; }
.change-papers[disabled] { opacity: .5; }
.feed-caption { display: block; margin: 5px 0 14px; font-size: 12px; color: var(--lc-muted); }
.home-cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 13px; animation: show-papers .18s ease-out; }
.retry-papers { color: #a34040; flex: none; }
.home-empty { display: flex; flex-direction: column; align-items: center; padding: 27px 16px 13px; background: #fff; border: 1px solid #e6ede5; border-radius: 16px; }
.empty-symbol { display: flex; align-items: center; justify-content: center; width: 56px; height: 56px; margin-bottom: 14px; border-radius: 18px; background: #eef4ee; color: #7d9b81; }
.empty-title { font-size: 14px; font-weight: 600; color: #435948; }
.empty-caption { margin-top: 6px; font-size: 12px; color: var(--lc-muted); }
.empty-link { display: flex; align-items: center; gap: 7px; min-height: 44px; margin: 10px 0 0; padding: 0; background: transparent; font-size: 12px; color: var(--lc-primary); }
.home-categories { padding-top: 23px; }
.home-categories .section-heading { margin-bottom: 10px; }
.category-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; animation: slide-up 0.5s ease-out; }
.category-entry { display: flex; align-items: center; gap: 8px; min-width: 0; min-height: 85px; margin: 0; padding: 12px 10px; background: #fff; border: 1px solid #e7ede4; border-radius: 14px; font-size: 12px; text-align: left; line-height: 1.5; transition: all 0.2s ease; }
.category-entry:active { transform: scale(0.98); border-color: #c5d8c4; }
@media (hover:hover) { .category-entry:hover { border-color: #b8d5b7; box-shadow: var(--lc-card-shadow-soft); } }
.category-symbol { display: flex; align-items: center; justify-content: center; flex: none; width: 30px; height: 34px; color: #8a784b; }
.category-tone-1 { color: #7883a3; }.category-tone-2 { color: #7b977f; }.category-tone-3 { color: #b48673; }
.category-title { display: block; color: var(--lc-text); font-size: 14px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.category-caption { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; font-size: 12px; color: var(--lc-muted); margin-top: 4px; }
.home-collections { padding-top: 28px; }
.home-collections .section-heading { margin-bottom: 14px; }
.section-title { font-size: 17px; color: #2b4131; }
.section-caption { display: block; margin-top: 4px; font-size: 12px; color: var(--lc-muted); }
.swipe-hint { font-size: 12px; color: var(--lc-muted); }
.collection-scroll { width: 100%; }
.collection-track { display:flex;gap:12px;padding:0 var(--lc-page-gutter) 8px; }
.home-more { padding-top: 25px; }
.all-papers { display: flex; align-items: center; justify-content: space-between; gap: 15px; width: 100%; margin: 0; padding: 20px 18px; text-align: left; border: 1px solid #e2e9df; border-radius: 16px; background: transparent; line-height: 1.5; }
.all-papers-title { display: block; color: #47614c; font-size: 14px; font-weight: 600; }
.all-papers-caption { display: block; margin-top: 4px; font-size: 12px; color: var(--lc-muted); }
.all-papers-arrow { display: flex; align-items: center; justify-content: center; flex: none; width: 36px; height: 36px; border-radius: 50%; background: #e7eee3; color: #52775a; }
@keyframes show-papers { from { transform: translateY(4px); opacity: .6; } to { transform: translateY(0); opacity: 1; } }
@keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes slide-up { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
.list-enter-active,
.list-leave-to {
  transition: all 0.3s ease;
}
.list-enter-from,
.list-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
.list-enter-to {
  opacity: 1;
  transform: translateY(0);
}
.home-subjects { animation: fade-in 0.4s ease-out; }
.collection-track { animation: slide-up 0.6s ease-out; }
@media (max-width: 359px) { .home-cards { gap: 10px; } .feed-tabs { gap: 14px; } .feed-tabs button { font-size: 14px; } .feed-tabs button.active { font-size: 17px; } .category-entry { gap: 5px; padding: 12px 8px; } .category-symbol { width: 25px; } .collection-track { padding-left: 16px; padding-right: 16px; } .collection-card { width: 235px; } }
</style>
