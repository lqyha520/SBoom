<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onHide, onLoad, onPullDownRefresh, onShow, onUnload, onShareAppMessage } from '@dcloudio/uni-app'
import PageChrome from '../../components/PageChrome.vue'
import PrivateImage from '../../components/PrivateImage.vue'
import MembershipSheet from '../../components/MembershipSheet.vue'
import { ApiError, errorMessage, favoriteCatalogPaper, fetchCatalogPaper, requestCatalogDownload } from '../../services/api'
import { ensureSession, requireLogin, session } from '../../services/session'
import { clearAssetCache, openPdf } from '../../services/assets'
import { createLatestRequest } from '../../services/latest-request'
import { fileSize, fileStatus, formatDate } from '../../content'
import { difficultyLabel, exerciseText, exerciseTitle } from '../../presentation'
import { assignGroup, fetchGroups, openSupport, recordEvent, recordView, type FavoriteGroup } from '../../services/experience'
import type { ExternalDownload, PaperDetail, PrintEdition } from '../../types'
import { shareCard } from '../../services/return-route'

const id = ref('')
const edition = ref<PrintEdition['kind']>('original')
const paper = ref<PaperDetail | null>(null)
const loading = ref(false)
const error = ref('')
const downloading = ref(false)
const downloadProgress = ref<number | null>(null)
const retryDownload = ref(false)
const changing = ref(false)
const previewOpen = ref(false)
const membershipOpen = ref(false)
const linkOpen = ref(false)
const linkTarget = ref<ExternalDownload | null>(null)
const copyingLink = ref(false)
const linkError = ref('')
const groupOpen = ref(false)
const groupBusy = ref(false)
const groupError = ref('')
const groupItems = ref<FavoriteGroup[]>([])
const visiblePages = ref(4)
const requests = createLatestRequest()
let active = true
let actionRevision = 0
const pdf = computed(() => paper.value?.assets.find(asset => asset.kind === 'pdf'))
const external = computed(() => paper.value?.download_mode === 'external')
const selectedEdition = computed(() => paper.value?.editions?.find(item => item.kind === edition.value))
const pages = computed(() => paper.value?.assets.filter(asset => asset.kind === 'page') || [])
const cover = computed(() => pages.value[0]?.url || paper.value?.thumbnail_url || null)
let pdfLabel = '下载 PDF'
// #ifdef MP-WEIXIN
pdfLabel = '打开 PDF'
// #endif

watch(() => session.user?.id, (owner, previous) => {
  actionRevision++; requests.invalidate(); paper.value = null; error.value = ''; loading.value = false
  edition.value = 'original'; retryDownload.value = false; downloadProgress.value = null
  previewOpen.value = false; membershipOpen.value = false
  clearLink()
  groupOpen.value = false; groupBusy.value = false; groupError.value = ''; groupItems.value = []
  if (active && previous && !owner) void load()
}, { flush: 'sync' })
async function load() {
  if (!id.value || !active || changing.value) { uni.stopPullDownRefresh(); return }
  const current = requests.begin()
  loading.value = true; error.value = ''; retryDownload.value = false; paper.value = null
  previewOpen.value = false; visiblePages.value = 4
  clearLink()
  try {
    const result = await fetchCatalogPaper(id.value)
    if (current()) {
      if (!result.can_view || !result.can_download) clearAssetCache()
      paper.value = result
      if (!result.editions?.some(item => item.kind === edition.value)) edition.value = 'original'
      if (session.user) void recordView(result.id).catch(() => {})
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
  if (!requireLogin()) return
  const current = requests.begin()
  loading.value = false; changing.value = true
  try {
    const result = await favoriteCatalogPaper(id.value, !paper.value.favorite)
    if (current() && paper.value) paper.value.favorite = result.favorite
  } catch (cause) { if (current()) { retryDownload.value = false; error.value = errorMessage(cause) } }
  finally { changing.value = false; if (active && !current()) void load() }
}
async function download() {
  if (!paper.value || downloading.value) return
  if (!requireLogin()) return
  if (!paper.value.can_download) { membershipOpen.value = true; return }
  if (!external.value && !pdf.value) return
  const revision = actionRevision
  let requested = false
  downloading.value = true; error.value = ''; retryDownload.value = false; downloadProgress.value = null
  try {
    const title = exerciseText(paper.value.title) + (selectedEdition.value ? ' · ' + selectedEdition.value.label : '')
    const asset = await requestCatalogDownload(id.value, edition.value)
    requested = true
    if (!active || revision !== actionRevision) return
    if (asset.kind === 'external') { linkTarget.value = asset; linkOpen.value = true; return }
    await openPdf(asset, title, percent => { if (active && revision === actionRevision) downloadProgress.value = percent })
    if (revision === actionRevision) void recordEvent('download_ok', id.value).catch(() => {})
  } catch (cause) {
    if (!active || revision !== actionRevision) return
    if (requested) void recordEvent('download_failed', id.value).catch(() => {})
    if (cause instanceof ApiError && cause.code === 'vip_required') { clearAssetCache(); await load() }
    if (!active || revision !== actionRevision) return
    error.value = errorMessage(cause)
    retryDownload.value = !(cause instanceof ApiError && [401, 403, 404].includes(cause.status))
    if (cause instanceof ApiError && cause.status === 404) paper.value = null
  } finally { downloading.value = false; downloadProgress.value = null }
}
function clearLink() { linkOpen.value = false; linkTarget.value = null; linkError.value = ''; copyingLink.value = false }
function copyLink() {
  if (!linkTarget.value || copyingLink.value) return
  const revision = actionRevision
  const target = linkTarget.value
  copyingLink.value = true; linkError.value = ''
  uni.setClipboardData({
    data: target.url + (target.extraction_code ? '\n提取码：' + target.extraction_code : ''),
    success: () => { if (active && revision === actionRevision) uni.showToast({ title: '链接已复制', icon: 'success' }) },
    fail: () => { if (active && revision === actionRevision) linkError.value = '复制失败，请重试或长按上方链接手动复制' },
    complete: () => { if (revision === actionRevision) copyingLink.value = false },
  })
}
async function chooseGroup() {
  if (!paper.value?.favorite || groupBusy.value || changing.value) return
  const revision = actionRevision
  groupBusy.value = true; groupError.value = ''
  try {
    const { items } = await fetchGroups()
    if (!active || revision !== actionRevision) return
    if (!items.length) { uni.showToast({ title: '请先在收藏页新建分组', icon: 'none' }); return }
    groupItems.value = items; groupOpen.value = true
  } catch (cause) { if (active && revision === actionRevision) { retryDownload.value = false; error.value = errorMessage(cause) } }
  finally { if (revision === actionRevision) groupBusy.value = false }
}
async function selectGroup(groupId: string | null) {
  if (!paper.value?.favorite || !groupOpen.value || groupBusy.value) return
  const revision = actionRevision
  groupBusy.value = true; groupError.value = ''
  try {
    await assignGroup(paper.value.id, groupId)
    if (!active || revision !== actionRevision) return
    groupOpen.value = false
    uni.showToast({ title: '分组已更新', icon: 'none' })
  } catch (cause) { if (active && revision === actionRevision) groupError.value = errorMessage(cause) }
  finally { if (revision === actionRevision) groupBusy.value = false }
}
function preview() {
  if (paper.value?.can_view && pages.value.length) { visiblePages.value = 4; previewOpen.value = true }
}
function viewMembership() { if (requireLogin()) membershipOpen.value = true }
onLoad(options => { id.value = typeof options?.id === 'string' ? options.id : '' })
onShareAppMessage(() => shareCard('paper', id.value, paper.value?.title))
onShow(async () => { active = true; await ensureSession(); if (active) void load() })
function leave() {
  active = false; actionRevision++; requests.invalidate(); loading.value = false; paper.value = null
  previewOpen.value = false; membershipOpen.value = false; uni.stopPullDownRefresh()
  clearLink()
  groupOpen.value = false; groupBusy.value = false; groupError.value = ''; groupItems.value = []
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
        <view v-else-if="external && !pages.length" class="preview-sheet locked-sheet"><wd-icon name="folder" size="31px" /><text>网盘资料</text></view><button v-else class="preview-sheet preview-entry" :disabled="!pages.length" role="button" aria-label="查看完整习题预览" @click="preview"><PrivateImage :src="cover" label="习题原稿封面" /></button>
        <button v-if="paper.can_view && pages.length" class="preview-pill" role="button" @click="preview"><wd-icon name="fullscreen" size="16px" /><text>预览 {{ pages.length }} 页</text></button>
        <view v-else-if="!paper.can_view" class="preview-access access-badge"><wd-icon name="lock" size="12px" /><text>VIP 专享</text></view>
      </view>
    </view>
    <template v-if="session.ready">
      <view v-if="error" class="content-width"><view class="error-strip"><text class="grow">{{ error }}</text><wd-button icon="refresh" type="danger" variant="text" role="button" :aria-label="retryDownload ? (external ? '重新获取链接' : '重新下载') : '重试加载'" :disabled="downloading" @click="retryDownload ? download() : load()" /></view></view>
      <view v-if="loading && !paper" class="state-block"><wd-loading /></view>
      <template v-if="paper">
        <view class="content-width detail-content">
          <view class="detail-tags"><text>{{ paper.subject }}</text><text>{{ paper.grade }}</text><view v-if="paper.required_download === 'vip'" class="access-badge">{{ paper.required_view === 'vip' ? 'VIP 专享' : 'VIP 下载' }}</view></view>
          <text class="detail-title">{{ exerciseTitle(paper) }}</text>
          <view v-if="paper.tags?.length" class="detail-tags curriculum-tags"><wd-tag v-for="tag in paper.tags" :key="tag.id" variant="light">{{ tag.name }}</wd-tag></view>
          <!-- #ifdef MP-WEIXIN -->
          <button class="section-link share-paper" open-type="share">分享这份资料</button>
          <!-- #endif -->
          <view class="detail-meta"><text v-if="paper.question_count">{{ paper.question_count }} 道题</text><text v-if="paper.page_count">{{ paper.page_count }} 页</text><text v-if="external">网盘下载</text><text v-if="paper.snapshot?.paper.difficulty">{{ difficultyLabel(paper.snapshot.paper.difficulty) }}</text></view>
          <text v-if="paper.description || paper.keyword" class="detail-description">{{ exerciseText(paper.description || paper.keyword) }}</text>
          <view v-if="paper.update_note" class="notice-strip"><text>第 {{ paper.release_number }} 版 · {{ paper.update_note }}</text></view>
          <view v-if="paper.versions && paper.versions.length > 1" class="version-notes"><text v-for="version in paper.versions" :key="version.release_number">第 {{ version.release_number }} 版 · {{ formatDate(version.created_at) }} · {{ version.note || '首次发布' }}</text></view>
          <view class="detail-service"><button role="button" v-if="paper.favorite" class="section-link" :disabled="groupBusy || changing" @click="chooseGroup">收藏分组</button><button role="button" class="section-link" @click="openSupport('correction', paper.id)">资料纠错</button><button role="button" class="section-link" @click="openSupport('download', paper.id)">下载遇到问题</button></view>
          <view class="detail-facts">
            <view><wd-icon name="folder" size="17px" /><text>分类</text><text class="fact-value">{{ exerciseText(paper.category || '公共习题') }}</text></view>
            <view><wd-icon name="file-pdf" size="17px" /><text>文件</text><text class="fact-value">{{ external ? '网盘链接' : pdf ? 'PDF · ' + fileSize(pdf.byte_size) : !session.user ? '登录后可下载' : !paper.can_download ? 'VIP 会员可下载' : fileStatus(paper.file_status) }}</text></view>
            <view><wd-icon name="time-line" size="17px" /><text>发布</text><text class="fact-value">{{ formatDate(paper.created_at) }}</text></view>
          </view>
          <view v-if="!external && paper.file_status !== 'ready'" class="notice-strip">{{ exerciseText(paper.file_error) || fileStatus(paper.file_status) }}</view>
          <view v-if="!external && paper.editions && paper.editions.length > 1" class="edition-choice"><text>打印版本</text><picker :range="paper.editions.map(item => item.label)" :value="Math.max(0, paper.editions.findIndex(item => item.kind === edition))" :disabled="downloading" @change="edition = paper.editions[Number($event.detail.value)]!.kind"><view class="edition-picker">{{ selectedEdition?.label }} · {{ fileSize(selectedEdition?.byte_size || 0) }}<wd-icon name="down" /></view></picker></view>
          <view v-if="!paper.can_view" class="vip-locked"><text>完整内容仅对有效 VIP 会员开放</text><wd-button variant="text" icon="star" role="button" @click="viewMembership">{{ session.user ? '查看会员状态' : '登录查看会员权益' }}</wd-button></view>
          <view v-else-if="!pages.length" class="preview-empty"><wd-empty icon="file-pdf" :tip="external ? '文件由网盘提供，获取链接后可前往查看' : pdf ? '暂无预览图' : '习题文件暂未就绪'"><template #bottom><view class="empty-actions"><wd-button variant="plain" icon="refresh" role="button" @click="load">刷新状态</wd-button></view></template></wd-empty></view>
        </view>
        <view v-if="downloading" class="content-width notice-strip" role="status">{{ external ? '正在获取网盘链接…' : downloadProgress === null ? '正在准备下载…' : downloadProgress < 100 ? '正在下载 ' + downloadProgress + '%' : '下载完成，正在打开 PDF…' }}</view><view class="detail-dock"><button class="bare-icon detail-favorite" :class="{ selected: paper.favorite }" role="button" :disabled="changing" :aria-pressed="paper.favorite" :aria-label="paper.favorite ? '取消收藏' : '收藏习题'" :title="paper.favorite ? '取消收藏' : '收藏习题'" @click="favorite"><wd-icon :name="paper.favorite ? 'heart-fill' : 'heart'" size="23px" /></button><view class="download-button"><wd-button role="button" block :icon="paper.can_download ? 'download' : 'lock'" :loading="downloading" :disabled="(!!session.user && paper.can_download && !external && !pdf) || downloading" @click="download">{{ !session.user ? (external ? '登录后获取链接' : '登录后下载') : paper.can_download ? (external ? '获取网盘链接' : pdfLabel) : 'VIP 会员专享' }}</wd-button></view></view>
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
    <wd-popup v-model="groupOpen" position="bottom" :z-index="1200" :close-on-click-modal="!groupBusy" root-portal safe-area-inset-bottom custom-style="border-radius:8px 8px 0 0">
      <view class="sheet group-sheet" role="dialog" aria-modal="true" aria-label="选择收藏分组">
        <view class="sheet-handle" />
        <view class="sheet-head"><text class="sheet-title">选择收藏分组</text><button class="bare-icon" role="button" aria-label="关闭收藏分组" :disabled="groupBusy" @click="groupOpen = false"><wd-icon name="close" size="20px" /></button></view>
        <view v-if="groupError" class="error-strip">{{ groupError }}</view>
        <scroll-view scroll-y class="group-options">
          <button class="group-option" role="button" :disabled="groupBusy" @click="selectGroup(null)">移至未分组</button>
          <button v-for="group in groupItems" :key="group.id" class="group-option" role="button" :disabled="groupBusy" @click="selectGroup(group.id)">{{ group.name }}</button>
        </scroll-view>
        <view v-if="groupBusy" class="loading-line"><wd-loading /><text>正在更新分组</text></view>
      </view>
    </wd-popup>
    <MembershipSheet :open="membershipOpen" @close="membershipOpen = false" @refreshed="load" />
    <wd-popup v-model="linkOpen" position="bottom" :z-index="1200" root-portal safe-area-inset-bottom custom-style="border-radius:8px 8px 0 0" @close="clearLink">
      <view v-if="linkOpen && linkTarget" class="sheet link-sheet" role="dialog" aria-modal="true" aria-label="网盘下载链接">
        <view class="sheet-handle" /><view class="sheet-head"><text class="sheet-title">网盘下载</text><button class="bare-icon" role="button" aria-label="关闭网盘链接" @click="clearLink"><wd-icon name="close" size="20px" /></button></view>
        <text class="link-tip">复制链接后，在浏览器或网盘 App 中打开并下载。</text>
        <text class="external-url" selectable>{{ linkTarget.url }}</text>
        <text v-if="linkTarget.extraction_code" class="external-code" selectable>提取码：{{ linkTarget.extraction_code }}</text>
        <view v-if="linkError" class="error-strip">{{ linkError }}</view>
        <wd-button block role="button" :loading="copyingLink" :disabled="copyingLink" @click="copyLink">{{ linkTarget.extraction_code ? '复制链接和提取码' : '复制网盘链接' }}</wd-button>
      </view>
    </wd-popup>
  </view>
</template>

<style scoped>
.link-sheet{max-width:520px;margin:0 auto}.link-tip{display:block;color:var(--lc-secondary);font-size:13px;line-height:1.8}.external-url{display:block;overflow-wrap:anywhere;word-break:break-all;padding:16px;margin:16px 0;background:var(--lc-background);border-radius:8px;color:var(--lc-primary);font-size:14px}.external-code{display:block;margin:0 0 20px;font-size:15px}
.curriculum-tags { margin-top:14px; }.share-paper { margin:12px 0 0; }.edition-choice { margin:22px 0;font-size:13px;color:var(--lc-secondary); }.edition-picker { display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:48px;padding:10px 14px;margin-top:8px;background:var(--lc-background);border:1px solid var(--lc-border);border-radius:10px; }
.detail-service { display:flex;gap:16px;flex-wrap:wrap;margin:14px 0; }.version-notes text { display:block;font-size:12px;color:var(--lc-muted);margin:8px 0; }
.group-sheet { max-width:520px;margin:0 auto; }.group-options { height:45vh; }.group-option { width:100%;margin:0;padding:14px 0;background:transparent;color:var(--lc-text);font-size:15px;line-height:1.5;text-align:left;overflow-wrap:anywhere;border-bottom:1px solid var(--lc-card-line); }
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
