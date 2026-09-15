<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onHide, onPullDownRefresh, onShow, onUnload } from '@dcloudio/uni-app'
import AuthGate from '../../components/AuthGate.vue'
import AppTabBar from '../../components/AppTabBar.vue'
import PageChrome from '../../components/PageChrome.vue'
import HomeBanner from '../../components/HomeBanner.vue'
import NoticeBar from '../../components/NoticeBar.vue'
import NoticePopup from '../../components/NoticePopup.vue'
import PaperCard from '../../components/PaperCard.vue'
import PaperSkeleton from '../../components/PaperSkeleton.vue'
import SearchField from '../../components/SearchField.vue'
import { errorMessage, favoriteCatalogPaper, fetchCatalog, fetchCatalogSummary, fetchSiteHome } from '../../services/api'
import { ensureSession, session } from '../../services/session'
import { openCatalog } from '../../services/navigation'
import { createLatestRequest } from '../../services/latest-request'
import { useTabBarOverlay } from '../../services/tabbar-overlay'
import { exerciseText, homeSelection, subjectTone, uniqueValues } from '../../presentation'
import type { CatalogSummary, PaperSummary, SiteCategory, SiteHome } from '../../types'

const items = ref<PaperSummary[]>([])
const summary = ref<CatalogSummary | null>(null)
const site = ref<SiteHome | null>(null)
const q = ref('')
const grade = ref('')
const feed = ref<'featured' | 'latest'>('featured')
const offset = ref(0)
const loading = ref(false)
const changing = ref('')
const error = ref('')
const gradePicker = ref(false)
useTabBarOverlay(() => gradePicker.value)
const gradeValue = ref<(string | number)[]>([''])
const cards = computed(() => homeSelection(items.value, offset.value))
const banners = computed(() => site.value?.banners || [])
const notices = computed(() => site.value?.notices.banner || [])
const popups = computed(() => site.value?.notices.popup || [])
const gradeColumns = computed(() => [{ value: '', label: '全部年级' }, ...uniqueValues(summary.value?.grades || []).map(value => ({ value, label: value }))])
// 学科入口取后台字典（顺序可控），只保留前三个再加「全部」，保持四宫格布局
const subjectIcons: Record<string, string> = { 语文: 'book', 数学: 'formula', 英语: 'translate' }
const subjects = computed(() => {
  const names = (site.value?.dictionaries.subjects || []).slice(0, 3)
  const resolved = names.length ? names : ['语文', '数学', '英语']
  return [...resolved.map(name => ({ label: name, icon: subjectIcons[name] || 'book', tone: subjectTone(name), subject: name })),
    { label: '全部', icon: 'apps', tone: 'general', subject: '' }]
})
// 首页专题位：只展示有已发布习题的分类（summary 已按后台顺序返回，且带图标与简介）
const topics = computed<SiteCategory[]>(() => (summary.value?.categories || []).slice(0, 2))
const requests = createLatestRequest()
let active = true
async function load() {
  if (!session.user || !active || changing.value) { uni.stopPullDownRefresh(); return }
  const current = requests.begin()
  loading.value = true; error.value = ''
  try {
    const [papers, counts, home] = await Promise.all([
      fetchCatalog({ limit: 12, grade: grade.value, sort: feed.value }), fetchCatalogSummary(), fetchSiteHome(),
    ])
    if (current()) { items.value = papers.items; summary.value = counts; site.value = home; offset.value = 0 }
  } catch (cause) { if (current()) error.value = errorMessage(cause) }
  finally { if (current()) { loading.value = false; uni.stopPullDownRefresh() } }
}
async function favorite(paper: PaperSummary) {
  if (loading.value || changing.value) return
  const current = requests.begin()
  changing.value = paper.id; error.value = ''
  try {
    const result = await favoriteCatalogPaper(paper.id, !paper.favorite)
    if (current()) {
      paper.favorite = result.favorite
      if (summary.value) summary.value.favorites = Math.max(0, summary.value.favorites + (result.favorite ? 1 : -1))
    }
  } catch (cause) { if (current()) error.value = errorMessage(cause) }
  finally { changing.value = '' }
}
function search() { openCatalog({ q: q.value, grade: grade.value }) }
function byGrade(event: { value: (string | number)[] }) { grade.value = String(event.value[0] || ''); void load() }
function selectFeed(value: 'featured' | 'latest') {
  if (value === feed.value || loading.value || changing.value) return
  feed.value = value; void load()
}
watch(() => session.user?.id, () => {
  requests.invalidate(); items.value = []; summary.value = null; site.value = null; error.value = ''; loading.value = false
  q.value = ''; grade.value = ''; gradePicker.value = false; gradeValue.value = ['']; offset.value = 0
}, { flush: 'sync' })
onShow(async () => { active = true; if (await ensureSession() && active) void load() })
function leave() { active = false; requests.invalidate(); loading.value = false; gradePicker.value = false; uni.stopPullDownRefresh() }
onHide(leave)
onUnload(leave)
onPullDownRefresh(load)
</script>

<template>
  <view class="home-page has-tabbar">
    <view class="home-hero"><PageChrome /><view class="content-width home-search-row"><button class="grade-entry" role="button" aria-label="选择年级" :disabled="!session.user || loading || !!changing" @click="gradePicker = true"><text>{{ grade || '全部年级' }}</text><wd-icon name="down" size="11px" /></button><view class="grow"><SearchField v-model="q" placeholder="搜索习题" @search="search" /></view></view><HomeBanner :banners="banners" :grade="grade" /></view>
    <NoticeBar v-if="session.user" :notices="notices" />
    <view class="content-width home-subjects"><wd-grid :column="4" :border="false" clickable bg-color="transparent" custom-class="subject-grid"><wd-grid-item v-for="item in subjects" :key="item.label" :text="item.label" role="button" :aria-label="item.subject ? item.label + '习题' : '全部习题'" @click="openCatalog({ subject: item.subject, grade })"><template #icon><view class="subject-symbol" :class="item.tone"><wd-icon :name="item.icon" size="23px" /></view></template></wd-grid-item></wd-grid></view>
    <AuthGate v-if="!session.user" />
    <template v-else>
      <view class="content-width home-feed"><view class="section-heading"><view class="feed-tabs"><button :class="{ active: feed === 'featured' }" :aria-pressed="feed === 'featured'" role="button" @click="selectFeed('featured')">为你精选</button><button :class="{ active: feed === 'latest' }" :aria-pressed="feed === 'latest'" role="button" @click="selectFeed('latest')">最近上新</button></view><button class="bare-icon" :disabled="loading || !!changing || items.length < 3" role="button" aria-label="换一组习题" title="换一组习题" @click="offset += 2"><wd-icon name="refresh" size="19px" /></button></view>
        <view v-if="error" class="error-strip"><text class="grow">{{ error }}</text><wd-button icon="refresh" variant="text" type="danger" role="button" aria-label="重试加载首页" @click="load" /></view>
        <PaperSkeleton v-if="loading && !items.length" cards :count="2" />
        <view v-else-if="cards.length" :key="feed + ':' + offset" class="home-cards" :aria-busy="loading"><PaperCard v-for="paper in cards" :key="paper.id" :paper="paper" :busy="loading || !!changing" @favorite="favorite(paper)" /></view>
        <view v-else-if="!loading && !error" class="home-empty"><wd-empty icon="no-content" tip="暂无已发布习题"><template #bottom><view class="empty-actions"><wd-button variant="plain" icon="refresh" role="button" @click="load">刷新</wd-button></view></template></wd-empty></view>
      </view>
      <view v-if="topics.length" class="content-width home-topics"><button v-for="(topic, index) in topics" :key="topic.id" class="topic-entry" role="button" @click="openCatalog({ category: topic.id, grade })"><view class="topic-symbol" :class="{ alternate: index === 1 }"><wd-icon :name="topic.icon || (index === 0 ? 'edit' : 'copy')" size="19px" /></view><view class="grow"><text class="topic-title">{{ exerciseText(topic.name) }}</text><text class="topic-caption">{{ topic.description || '跟上每一课' }}</text></view></button></view>
      <view v-if="items.length" class="home-more"><button class="section-link" role="button" @click="openCatalog({ grade })"><text>全部习题</text><wd-icon name="arrow-right" size="15px" /></button></view>
    </template>
    <AppTabBar current="home" />
    <NoticePopup :notices="popups" />
    <wd-picker v-model="gradeValue" v-model:visible="gradePicker" title="选择年级" :columns="gradeColumns" :z-index="1200" root-portal @confirm="byGrade" />
  </view>
</template>

<style scoped>
.home-hero { border-radius: 0 0 48% 9% / 0 0 7% 2%; overflow: hidden; background-color: var(--lc-hero); background-image: radial-gradient(60% 64% at 94% -12%, #ffffff70 0%, #ffffff00 68%), radial-gradient(48% 52% at 2% 110%, #ffffff45 0%, #ffffff00 70%), linear-gradient(168deg, #eaf5ec 0%, #daebde 58%, #e6f2e8 100%); }
.home-search-row { display: flex; align-items: center; gap: 9px; padding: 18px 18px 0; --wot-search-plain-block-bg: #fff; }
.grade-entry { display: flex; align-items: center; justify-content: space-between; gap: 4px; min-height: 44px; width: 78px; padding: 0; margin: 0; background: transparent; font-size: 12px; line-height: 1.5; color: var(--lc-text); flex: none; }
.grade-entry text { min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.home-subjects { padding: 16px 12px 8px; }
.home-subjects :deep(.subject-grid) { --wot-grid-item-padding: 8px 0 12px; --wot-grid-item-text-color: #28372f; --wot-grid-item-font-size: 12px; --wot-grid-item-text-spacing: 8px; }
.subject-symbol { display: flex; align-items: center; justify-content: center; width: 49px; height: 49px; border-radius: 50%; color: var(--subject-color); background: var(--subject-tint); transition: transform .18s; }
.subject-symbol:active { transform: scale(.94); }
.home-feed { padding-top: 3px; }
.feed-tabs { display: flex; align-items: center; gap: 20px; }
.feed-tabs button { position: relative; min-height: 44px; margin: 0; padding: 6px 0; border-radius: 0; font-size: 16px; font-weight: 600; line-height: 1.5; color: var(--lc-muted); background: transparent; }
.feed-tabs button.active { color: var(--lc-text); }
.feed-tabs button.active::before { content: ''; position: absolute; left: 0; bottom: 2px; width: 20px; height: 3px; border-radius: 99px; background: var(--lc-primary); }
.home-cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 19px; animation: show-papers .18s ease-out; }
.home-topics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; padding-top: 22px; padding-bottom: 4px; }
.topic-entry { display: flex; align-items: center; gap: 10px; margin: 0; padding: 0; min-height: 48px; min-width: 0; background: transparent; font-size: 12px; line-height: 1.5; text-align: left; }
.topic-symbol { width: 38px; height: 42px; display: flex; align-items: center; justify-content: center; flex: none; border-radius: 50%; background: var(--lc-warning-bg); color: var(--lc-warning); }
.topic-symbol.alternate { background: #f1ebf6; color: #86639a; }
.topic-title { display: block; color: var(--lc-text); overflow-wrap: anywhere; }
.topic-caption { display: block; font-size: 11px; color: var(--lc-muted); margin-top: 3px; }
.home-more { text-align: center; padding-top: 10px; }
.home-empty { padding: 28px 0; }
@keyframes show-papers { from { transform: translateY(4px); opacity: .6; } to { transform: translateY(0); opacity: 1; } }
@media (max-width: 359px) { .home-search-row { padding-left: 14px; padding-right: 14px; gap: 6px; } .home-cards { gap: 14px; } .home-topics { gap: 12px; } .topic-entry { gap: 7px; } }
</style>
