<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onHide, onLoad, onPullDownRefresh, onShow, onUnload } from '@dcloudio/uni-app'
import AuthGate from '../../components/AuthGate.vue'
import PageChrome from '../../components/PageChrome.vue'
import PrivateImage from '../../components/PrivateImage.vue'
import MembershipSheet from '../../components/MembershipSheet.vue'
import { ApiError, errorMessage, favoriteCatalogPaper, fetchCatalogPaper, requestCatalogDownload } from '../../services/api'
import { ensureSession, session } from '../../services/session'
import { clearAssetCache, openPdf } from '../../services/assets'
import { createLatestRequest } from '../../services/latest-request'
import { fileSize, fileStatus, formatDate } from '../../content'
import { difficultyLabel, exerciseText, exerciseTitle } from '../../presentation'
import type { PaperDetail } from '../../types'

const id = ref('')
const paper = ref<PaperDetail | null>(null)
const loading = ref(false)
const error = ref('')
const downloading = ref(false)
const changing = ref(false)
const previewOpen = ref(false)
const membershipOpen = ref(false)
const visiblePages = ref(4)
const requests = createLatestRequest()
let active = true
let actionRevision = 0
const pdf = computed(() => paper.value?.assets.find(asset => asset.kind === 'pdf'))
const pages = computed(() => paper.value?.assets.filter(asset => asset.kind === 'page') || [])
const cover = computed(() => pages.value[0]?.url || paper.value?.thumbnail_url || null)
let pdfLabel = '下载 PDF'
// #ifdef MP-WEIXIN
pdfLabel = '打开 PDF'
// #endif

watch(() => session.user?.id, () => {
  actionRevision++; requests.invalidate(); paper.value = null; error.value = ''; loading.value = false
  previewOpen.value = false; membershipOpen.value = false
}, { flush: 'sync' })
async function load() {
  if (!session.user || !id.value || !active || changing.value) { uni.stopPullDownRefresh(); return }
  const current = requests.begin()
  loading.value = true; error.value = ''; paper.value = null
  previewOpen.value = false; visiblePages.value = 4
  try {
    const result = await fetchCatalogPaper(id.value)
    if (current()) {
      if (!result.can_view || !result.can_download) clearAssetCache()
      paper.value = result
    }
  } catch (cause) {
    if (current()) {
      error.value = errorMessage(cause)
      if (cause instanceof ApiError && cause.status === 404) paper.value = null
    }
  } finally { if (current()) { loading.value = false; uni.stopPullDownRefresh() } }
}
async function favorite() {
  if (!paper.value || changing.value) return
  const current = requests.begin()
  loading.value = false; changing.value = true
  try {
    const result = await favoriteCatalogPaper(id.value, !paper.value.favorite)
    if (current() && paper.value) paper.value.favorite = result.favorite
  } catch (cause) { if (current()) error.value = errorMessage(cause) }
  finally { changing.value = false; if (active && !current()) void load() }
}
async function download() {
  if (!paper.value || downloading.value) return
  if (!paper.value.can_download) { membershipOpen.value = true; return }
  if (!pdf.value) return
  const revision = actionRevision
  downloading.value = true; error.value = ''
  try {
    const title = exerciseText(paper.value.title)
    const asset = await requestCatalogDownload(id.value)
    if (!active || revision !== actionRevision) return
    await openPdf(asset, title)
  } catch (cause) {
    if (!active || revision !== actionRevision) return
    if (cause instanceof ApiError && cause.code === 'vip_required') { clearAssetCache(); await load() }
    if (!active || revision !== actionRevision) return
    error.value = errorMessage(cause)
    if (cause instanceof ApiError && cause.status === 404) paper.value = null
  } finally { downloading.value = false }
}
function preview() {
  if (paper.value?.can_view && pages.value.length) { visiblePages.value = 4; previewOpen.value = true }
}
onLoad(options => { id.value = typeof options?.id === 'string' ? options.id : '' })
onShow(async () => { active = true; if (await ensureSession() && active) void load() })
function leave() {
  active = false; actionRevision++; requests.invalidate(); loading.value = false; paper.value = null
  previewOpen.value = false; membershipOpen.value = false; uni.stopPullDownRefresh()
}
onHide(leave)
onUnload(leave)
onPullDownRefresh(() => { void load() })
</script>

<template>
  <view class="detail-page">
    <view class="detail-hero">
      <PageChrome back fallback="/pages/library/index" />
      <view v-if="paper" class="paper-stage">
        <view v-if="!paper.can_view" class="preview-sheet locked-sheet"><wd-icon name="lock" size="31px" /><text>VIP 专享习题</text></view>
        <button v-else class="preview-sheet preview-entry" :disabled="!pages.length" role="button" aria-label="查看完整习题预览" @click="preview"><PrivateImage :src="cover" label="习题原稿封面" /></button>
        <button v-if="paper.can_view && pages.length" class="preview-pill" role="button" @click="preview"><wd-icon name="fullscreen" size="16px" /><text>预览 {{ pages.length }} 页</text></button>
        <view v-else-if="!paper.can_view" class="preview-access access-badge"><wd-icon name="lock" size="12px" /><text>VIP 专享</text></view>
      </view>
    </view>
    <AuthGate v-if="!session.user" />
    <template v-else>
      <view v-if="error" class="content-width"><view class="error-strip"><text class="grow">{{ error }}</text><wd-button icon="refresh" type="danger" variant="text" role="button" aria-label="重试" @click="load" /></view></view>
      <view v-if="loading && !paper" class="state-block"><wd-loading /></view>
      <template v-if="paper">
        <view class="content-width detail-content">
          <view class="detail-tags"><text>{{ paper.subject }}</text><text>{{ paper.grade }}</text><view v-if="paper.required_download === 'vip'" class="access-badge">{{ paper.required_view === 'vip' ? 'VIP 专享' : 'VIP 下载' }}</view></view>
          <text class="detail-title">{{ exerciseTitle(paper) }}</text>
          <view class="detail-meta"><text>{{ paper.question_count }} 道题</text><text>{{ paper.page_count }} 页</text><text v-if="paper.snapshot">{{ difficultyLabel(paper.snapshot.paper.difficulty) }}</text></view>
          <text v-if="paper.description || paper.keyword" class="detail-description">{{ exerciseText(paper.description || paper.keyword) }}</text>
          <view class="detail-facts">
            <view><wd-icon name="folder" size="17px" /><text>分类</text><text class="fact-value">{{ exerciseText(paper.category || '公共习题') }}</text></view>
            <view><wd-icon name="file-pdf" size="17px" /><text>文件</text><text class="fact-value">{{ pdf ? 'PDF · ' + fileSize(pdf.byte_size) : !paper.can_download ? 'VIP 会员可下载' : fileStatus(paper.file_status) }}</text></view>
            <view><wd-icon name="time-line" size="17px" /><text>发布</text><text class="fact-value">{{ formatDate(paper.created_at) }}</text></view>
          </view>
          <view v-if="paper.file_status !== 'ready'" class="notice-strip">{{ exerciseText(paper.file_error) || fileStatus(paper.file_status) }}</view>
          <view v-if="!paper.can_view" class="vip-locked"><text>完整内容仅对有效 VIP 会员开放</text><wd-button variant="text" icon="star" role="button" @click="membershipOpen = true">查看会员状态</wd-button></view>
          <view v-else-if="!pages.length" class="preview-empty"><wd-empty icon="file-pdf" :tip="pdf ? '暂无预览图' : '习题文件暂未就绪'"><template #bottom><view class="empty-actions"><wd-button variant="plain" icon="refresh" role="button" @click="load">刷新状态</wd-button></view></template></wd-empty></view>
        </view>
        <view class="detail-dock"><button class="bare-icon detail-favorite" :class="{ selected: paper.favorite }" role="button" :disabled="changing" :aria-pressed="paper.favorite" :aria-label="paper.favorite ? '取消收藏' : '收藏习题'" :title="paper.favorite ? '取消收藏' : '收藏习题'" @click="favorite"><wd-icon :name="paper.favorite ? 'heart-fill' : 'heart'" size="23px" /></button><view class="download-button"><wd-button role="button" block :icon="paper.can_download ? 'download' : 'lock'" :loading="downloading" :disabled="(paper.can_download && !pdf) || downloading" @click="download">{{ paper.can_download ? pdfLabel : 'VIP 会员专享' }}</wd-button></view></view>
      </template>
      <view v-else-if="!loading && !error" class="state-block"><wd-empty icon="no-content" tip="未找到习题" /></view>
    </template>
    <wd-popup v-model="previewOpen" position="bottom" :z-index="1200" root-portal safe-area-inset-bottom custom-style="border-radius:8px 8px 0 0">
      <view v-if="paper?.can_view && previewOpen" class="preview-dialog" role="dialog" aria-modal="true" aria-label="习题原稿预览">
        <view class="sheet preview-header"><view class="sheet-handle" /><view class="sheet-head"><text class="sheet-title">原稿预览 <text class="preview-total">{{ pages.length }} 页</text></text><button class="bare-icon" role="button" aria-label="关闭原稿预览" @click="previewOpen = false"><wd-icon name="close" size="20px" /></button></view></view>
        <scroll-view scroll-y class="preview-scroll">
          <view class="original-pages"><view v-for="page in pages.slice(0, visiblePages)" :key="page.id" class="original-page"><PrivateImage :src="page.url" :label="'放大第 ' + page.page_number + ' 页习题'" preview /><text class="page-number">{{ page.page_number }} / {{ pages.length }}</text></view><view v-if="visiblePages < pages.length" class="loading-line"><wd-button variant="plain" icon="down" role="button" @click="visiblePages += 4">加载更多页面</wd-button></view></view>
        </scroll-view>
      </view>
    </wd-popup>
    <MembershipSheet :open="membershipOpen" @close="membershipOpen = false" @refreshed="load" />
  </view>
</template>

<style scoped>
.detail-page { padding-bottom: calc(96px + env(safe-area-inset-bottom)); }
.detail-hero { background-color: #e9effb; background-image: radial-gradient(58% 60% at 92% -8%, #ffffff75 0%, #ffffff00 68%), radial-gradient(44% 48% at 4% 108%, #ffffff3d 0%, #ffffff00 70%), linear-gradient(168deg, #eef3fd 0%, #e2e9f8 100%); border-radius: 0 0 44% 6% / 0 0 5% 2%; }
.paper-stage { display: flex; align-items: center; justify-content: center; position: relative; min-height: 250px; padding: 15px 30px 28px; }
.preview-sheet { width: 148px; flex: none; transform: rotate(-5deg); box-shadow: 5px 7px 0 #ffffff80, 0 9px 28px #5261831f; border-radius: 2px; background: #fff; }
.preview-entry { display: block; padding: 0; margin: 0; line-height: 1.5; }
.preview-entry:active { transform: rotate(-2deg); }
.locked-sheet { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 15px; height: 209px; color: var(--lc-warning); font-size: 13px; }
.preview-pill { position: absolute; bottom: 16px; right: 22px; display: flex; align-items: center; gap: 6px; min-height: 44px; padding: 6px 13px; margin: 0; border-radius: 999px; background: #fff; color: var(--lc-secondary); font-size: 12px; line-height: 1.5; box-shadow: 0 2px 9px #52618308; }
.preview-access { position: absolute; bottom: 24px; right: 22px; }
.detail-content { padding-top: 25px; padding-bottom: 22px; }
.detail-tags { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; color: var(--lc-primary); font-size: 12px; }
.detail-title { display: block; font-size: 23px; line-height: 1.5; font-weight: 650; margin-top: 10px; overflow-wrap: anywhere; }
.detail-meta { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; color: var(--lc-muted); font-size: 12px; margin-top: 9px; }
.detail-description { display: block; margin-top: 19px; color: var(--lc-secondary); font-size: 13px; line-height: 1.9; overflow-wrap: anywhere; white-space: pre-wrap; }
.detail-facts { display: flex; flex-direction: column; gap: 16px; margin-top: 23px; }
.detail-facts > view { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--lc-muted); }
.detail-facts :deep(.wd-icon) { flex: none; }
.fact-value { margin-left: auto; min-width: 0; max-width: 70%; overflow-wrap: anywhere; color: var(--lc-text); text-align: right; }
.vip-locked { display: flex; flex-direction: column; align-items: flex-start; gap: 5px; color: var(--lc-muted); font-size: 12px; margin-top: 25px; }
.preview-empty { padding-top: 22px; }
.detail-dock { position: fixed; z-index: 20; left: 50%; bottom: 0; transform: translateX(-50%); width: 100%; max-width: 520px; display: flex; align-items: center; gap: 12px; padding: 12px 22px calc(16px + env(safe-area-inset-bottom)); background: #ffffffed; }
.detail-favorite { width: 49px; height: 49px; background: var(--lc-background); }
.detail-favorite.selected { color: var(--lc-coral); background: #fbeae2; }
.download-button { flex: 1; min-width: 0; --wot-button-height-medium: 49px; }
.preview-dialog { width: 100%; max-width: 520px; margin: 0 auto; }
.preview-header { padding-bottom: 0; }
.preview-total { color: var(--lc-muted); font-size: 12px; font-weight: 400; margin-left: 6px; }
.preview-scroll { height: 68vh; }
.original-pages { padding: 6px 20px 24px; background: var(--lc-background); }
.original-page { padding-top: 15px; }
.page-number { display: block; text-align: center; padding: 12px 0; color: var(--lc-muted); font-size: 11px; font-variant-numeric: tabular-nums; }
@media (max-width: 359px) { .detail-title { font-size: 21px; } .detail-dock { padding-left: 17px; padding-right: 17px; } }
</style>
