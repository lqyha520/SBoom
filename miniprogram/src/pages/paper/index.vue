<script setup lang="ts">
import { copyWithPrivacy } from '../../services/privacy'
import { computed, nextTick, ref, watch } from 'vue'
import { onHide, onLoad, onPullDownRefresh, onShow, onUnload, onShareAppMessage } from '@dcloudio/uni-app'
import PageChrome from '../../components/PageChrome.vue'
import PrivateImage from '../../components/PrivateImage.vue'
import PaperPreview from '../../components/PaperPreview.vue'
import PaperAccessBadge from '../../components/PaperAccessBadge.vue'
import MembershipSheet from '../../components/MembershipSheet.vue'
import { ApiError, errorMessage, favoriteCatalogPaper, fetchCatalogPaper, requestCatalogDownload } from '../../services/api'
import { ensureSession, requireLogin, session } from '../../services/session'
import { cancelPdfDownload, clearAssetCache, openPdf } from '../../services/assets'
import { createLatestRequest } from '../../services/latest-request'
import { fileSize, fileStatus, formatDate } from '../../content'
import { difficultyLabel, exerciseText, exerciseTitle, downloadAccessHint, subjectTone } from '../../presentation'
import { assignGroup, createGroup, fetchGroups, openSupport, recordEvent, recordView, type FavoriteGroup } from '../../services/experience'
import type { ExternalDownload, PaperDetail, PrintEdition } from '../../types'
import { captureScroll } from '../../services/page-lifecycle'
import { shareCard } from '../../services/return-route'

const id = ref('')
const edition = ref<PrintEdition['kind']>('original')
const paper = ref<PaperDetail | null>(null)
const verified = ref(false)
let scrollTop = 0
let viewedBy = ''
const groupReads = createLatestRequest()
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
const groupName = ref('')
const requests = createLatestRequest()
let active = true
let actionRevision = 0
const pdf = computed(() => paper.value?.assets.find(asset => asset.kind === 'pdf'))
const external = computed(() => paper.value?.download_mode === 'external')
const selectedEdition = computed(() => paper.value?.editions?.find(item => item.kind === edition.value))
const pages = computed(() => verified.value ? paper.value?.assets.filter(asset => asset.kind === 'page') || [] : [])
const cover = computed(() => verified.value ? paper.value?.thumbnail_url || pages.value[0]?.url || null : null)
let pdfLabel = '下载 PDF'
let pdfGuide = '下载后可在浏览器下载记录中查看文件'
// #ifdef MP-WEIXIN
pdfLabel = '打开 PDF'
pdfGuide = '打开后，点右上角菜单保存或转发文件'
// #endif

const hasEditions = computed(() => !external.value && (paper.value?.editions?.length || 0) > 1)
const actionLabel = computed(() => {
  if (!paper.value) return pdfLabel
  if (!session.user) return paper.value.required_download === 'vip' ? '登录查看会员权益' : external.value ? '登录获取链接' : '登录后免费下载'
  if (!paper.value.can_download) return '查看会员权益'
  if (retryDownload.value) return external.value ? '重新获取链接' : '重试下载'
  return external.value ? '获取网盘链接' : pdfLabel
})
watch(() => session.user?.id, (owner, previous) => {
  actionRevision++; requests.invalidate(); paper.value = null; error.value = ''; loading.value = false
  edition.value = 'original'; retryDownload.value = false; downloadProgress.value = null
  previewOpen.value = false; membershipOpen.value = false
  clearLink()
  groupOpen.value = false; groupBusy.value = false; groupError.value = ''; groupItems.value = []; groupName.value = ''
  if (active && previous && !owner) void load()
}, { flush: 'sync' })
async function load() {
  if (!id.value || !active || changing.value) { uni.stopPullDownRefresh(); return }
  const current = requests.begin()
  const restoring = !!paper.value
  loading.value = true; verified.value = false; error.value = ''; retryDownload.value = false
  previewOpen.value = false
  clearLink()
  try {
    const result = await fetchCatalogPaper(id.value, { scope: current })
    if (current()) {
      if (!result.can_view || !result.can_download) clearAssetCache()
      paper.value = result
      verified.value = true
      if (restoring) { await nextTick(); if (current()) uni.pageScrollTo?.({ scrollTop, duration: 0 }) }
      if (!result.editions?.some(item => item.kind === edition.value)) edition.value = 'original'
      if (current() && session.user && viewedBy !== session.user.id) {
        const owner = session.user.id; viewedBy = owner
        void recordView(result.id).catch(() => { if (viewedBy === owner) viewedBy = '' })
      }
    }
  } catch (cause) {
    if (current()) {
      error.value = errorMessage(cause)
      if (cause instanceof ApiError && [401, 403, 404].includes(cause.status)) { paper.value = null; clearAssetCache() }
    }
  } finally { if (current()) { loading.value = false; uni.stopPullDownRefresh() } }
}
async function favorite() {
  if (!paper.value || !verified.value || loading.value || changing.value) return
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
  if (!paper.value || !verified.value || loading.value || downloading.value) return
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
  copyWithPrivacy({
    data: target.url + (target.extraction_code ? '\n提取码：' + target.extraction_code : ''),
    success: () => { if (active && revision === actionRevision) uni.showToast({ title: '链接已复制', icon: 'success' }) },
    fail: () => { if (active && revision === actionRevision) linkError.value = '复制失败，请重试或长按上方链接手动复制' },
    complete: () => { if (revision === actionRevision) copyingLink.value = false },
  })
}
async function chooseGroup() {
  if (!paper.value?.favorite || groupBusy.value || changing.value) return
  const revision = actionRevision
  groupBusy.value = true; groupError.value = ''; groupName.value = ''; groupOpen.value = true
  try {
    const { items } = await fetchGroups({ scope: groupReads.begin() })
    if (!active || revision !== actionRevision) return
    groupItems.value = items; groupOpen.value = true
  } catch (cause) { if (active && revision === actionRevision) groupError.value = errorMessage(cause) }
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
  if (verified.value && paper.value?.can_view && pages.value.length) previewOpen.value = true
}
async function createAndAssignGroup() {
  const name = groupName.value.trim()
  if (!paper.value?.favorite || !groupOpen.value || groupBusy.value || !name) return
  if (name.length > 40) { groupError.value = '分组名称最多 40 个字'; return }
  const revision = actionRevision, paperId = paper.value.id
  groupBusy.value = true; groupError.value = ''
  let created = false
  try {
    const group = await createGroup(name)
    if (!active || revision !== actionRevision) return
    created = true; groupItems.value.push(group); groupName.value = ''
    await assignGroup(paperId, group.id)
    if (!active || revision !== actionRevision) return
    groupOpen.value = false
    uni.showToast({ title: '已收藏到“' + group.name + '”', icon: 'none' })
  } catch (cause) {
    if (active && revision === actionRevision) groupError.value = (created ? '分组已创建，归组失败，请点选下方分组重试。' : '') + errorMessage(cause)
  } finally { if (revision === actionRevision) groupBusy.value = false }
}
function viewMembership() { if (requireLogin()) membershipOpen.value = true }
// #ifdef H5
function sharePaper() {
  if (!paper.value) return
  const card = shareCard('paper', paper.value.id, paper.value.title)
  copyWithPrivacy({
    data: window.location.origin + window.location.pathname + '#' + card.path,
    success: () => uni.showToast({ title: '资料链接已复制，可发送给好友', icon: 'none' }),
    fail: () => uni.showToast({ title: '复制失败，请重试', icon: 'none' }),
  })
}
// #endif
onLoad(options => { id.value = typeof options?.id === 'string' ? options.id : '' })
onShareAppMessage(() => shareCard('paper', id.value, paper.value?.title))
onShow(async () => { active = true; await ensureSession(); if (active) void load() })
function leave() {
  active = false; groupReads.invalidate(); actionRevision++; requests.invalidate(); loading.value = false; verified.value = false
  if (paper.value) paper.value = { ...paper.value, assets: [], snapshot: null, thumbnail_url: null, editions: paper.value.editions?.map(({ url: _url, ...item }) => item) }
  cancelPdfDownload()
  previewOpen.value = false; membershipOpen.value = false; uni.stopPullDownRefresh()
  clearLink()
  groupOpen.value = false; groupBusy.value = false; groupError.value = ''; groupItems.value = []; groupName.value = ''
}
onHide(() => { captureScroll(top => { scrollTop = top }); leave() })
function reconnect() { if (active && !changing.value && !downloading.value) void load() }
uni.$on?.('lc-network-restored', reconnect)
onUnload(() => { leave(); paper.value = null; uni.$off?.('lc-network-restored', reconnect) })
onPullDownRefresh(() => { void load() })
</script>

<template>
  <view class="detail-page" :class="{ 'has-editions': hasEditions }">
    <view class="page-navigation-sticky"><PageChrome back fallback="/pages/library/index" /></view>
    <view v-if="paper" class="content-width detail-heading">
      <view class="detail-tags"><text>{{ paper.subject }}</text><text>{{ paper.grade }}</text><PaperAccessBadge :paper="paper" /></view>
      <text class="detail-title">{{ exerciseTitle(paper) }}</text>
    </view>
    <view class="detail-hero" :class="subjectTone(paper?.subject || '')">
      <view v-if="paper" class="paper-stage">
        <view v-if="!verified" class="preview-sheet locked-sheet"><wd-loading v-if="loading" /><text>{{ loading ? '正在核验访问权限' : '请重试加载资料' }}</text></view>
        <view v-else-if="!paper.can_view" class="preview-sheet locked-sheet"><wd-icon name="lock" size="31px" /><text>VIP 专享习题</text></view>
        <view v-else-if="external && !pages.length" class="preview-sheet locked-sheet"><wd-icon name="folder" size="31px" /><text>网盘资料</text></view><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-else class="preview-sheet preview-entry" :disabled="!pages.length" role="button" aria-label="查看完整习题预览" @click="preview"><PrivateImage :src="cover" label="习题原稿封面" /></button>
        <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-if="paper.can_view && pages.length" class="preview-pill" role="button" @click="preview"><wd-icon name="fullscreen" size="16px" /><text>预览 {{ pages.length }} 页</text></button>
        <view v-else-if="!paper.can_view" class="preview-access access-badge"><wd-icon name="lock" size="12px" /><text>VIP 专享</text></view>
      </view>
    </view>
    <template v-if="session.ready">
      <view v-if="error" class="content-width"><view class="error-strip"><text class="grow">{{ error }}</text><wd-button icon="refresh" type="danger" variant="text" role="button" :aria-label="retryDownload ? (external ? '重新获取链接' : '重新下载') : '重试加载'" :disabled="downloading" @click="retryDownload ? download() : load()" /></view></view>
      <view v-if="loading && !paper" class="state-block"><wd-loading /></view>
      <template v-if="paper">
        <view class="content-width detail-content">
          <view v-if="paper.tags?.length" class="detail-tags curriculum-tags"><wd-tag v-for="tag in paper.tags" :key="tag.id" variant="light">{{ tag.name }}</wd-tag></view>
          <view class="detail-meta"><text v-if="paper.question_count">{{ paper.question_count }} 道题</text><text v-if="paper.page_count">{{ paper.page_count }} 页</text><text v-if="external">网盘下载</text><text v-if="paper.snapshot?.paper.difficulty">{{ difficultyLabel(paper.snapshot.paper.difficulty) }}</text></view>
          <text v-if="paper.description || paper.keyword" class="detail-description">{{ exerciseText(paper.description || paper.keyword) }}</text>
          <view v-if="paper.update_note" class="notice-strip"><text>第 {{ paper.release_number }} 版 · {{ paper.update_note }}</text></view>
          <view v-if="paper.versions && paper.versions.length > 1" class="version-notes"><text v-for="version in paper.versions" :key="version.release_number">第 {{ version.release_number }} 版 · {{ formatDate(version.created_at) }} · {{ version.note || '首次发布' }}</text></view>
          <view class="detail-facts">
            <view><wd-icon name="folder" size="17px" /><text>分类</text><text class="fact-value">{{ exerciseText(paper.category || '公共习题') }}</text></view>
            <view><wd-icon name="file-pdf" size="17px" /><text>文件</text><text class="fact-value">{{ external ? '网盘链接' : pdf ? 'PDF · ' + fileSize(pdf.byte_size) : paper.required_download === 'vip' && !paper.can_download ? 'VIP 会员可下载' : !session.user ? '登录后免费下载' : fileStatus(paper.file_status) }}</text></view>
            <view><wd-icon name="time-line" size="17px" /><text>发布</text><text class="fact-value">{{ formatDate(paper.created_at) }}</text></view>
          </view>
          <view class="detail-service"><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" v-if="paper.favorite" class="section-link" :disabled="groupBusy || changing" @click="chooseGroup">收藏分组</button><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" class="section-link" @click="openSupport('correction', paper.id)">资料纠错</button><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" role="button" class="section-link" @click="openSupport('download', paper.id)">下载遇到问题</button></view>
          <view v-if="!external && paper.file_status !== 'ready'" class="notice-strip">{{ exerciseText(paper.file_error) || fileStatus(paper.file_status) }}</view>

          <view v-if="verified && !paper.can_view" class="vip-locked"><text>完整内容仅对有效 VIP 会员开放</text><wd-button variant="text" icon="star" role="button" @click="viewMembership">{{ session.user ? '查看会员状态' : '登录查看会员权益' }}</wd-button></view>
          <view v-else-if="verified && !pages.length" class="preview-empty"><wd-empty icon="file-pdf" :tip="external ? '文件由网盘提供，获取链接后可前往查看' : pdf ? '暂无预览图' : '习题文件暂未就绪'"><template #bottom><view class="empty-actions"><wd-button variant="plain" icon="refresh" role="button" @click="load">刷新状态</wd-button></view></template></wd-empty></view>
        </view>
        <view class="detail-dock">
          <text class="download-hint">{{ downloadAccessHint(paper) }}</text>
          <view v-if="hasEditions && paper.editions" class="edition-choice"><view class="edition-segments" role="radiogroup" aria-label="文件版本"><button v-for="item in paper.editions" :key="item.kind" role="radio" hover-class="control-pressed" :aria-checked="edition === item.kind" :class="{ selected: edition === item.kind }" :disabled="downloading || loading || !verified" @click="edition = item.kind"><text>{{ item.label }}</text><text class="edition-size">{{ fileSize(item.byte_size) }}</text></button></view></view>
          <text v-if="downloading" class="transfer-status" role="status">{{ external ? '正在获取网盘链接…' : downloadProgress === null ? '正在准备文件…' : downloadProgress < 100 ? '正在下载 ' + downloadProgress + '%' : '下载完成，正在打开 PDF…' }}</text>
          <text v-if="retryDownload && error" class="download-error" role="alert">{{ error }}</text>
          <view class="detail-actions">
            <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="detail-utility detail-favorite" :class="{ selected: paper.favorite }" role="button" :disabled="changing || loading || !verified" :aria-pressed="paper.favorite" :aria-label="paper.favorite ? '取消收藏' : '收藏习题'" @click="favorite"><wd-icon :name="paper.favorite ? 'heart-fill' : 'heart'" size="22px" /><text>{{ paper.favorite ? '已收藏' : '收藏' }}</text></button>
            <!-- #ifdef MP-WEIXIN -->
            <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="detail-utility detail-share" role="button" aria-label="分享这份资料给好友" open-type="share"><wd-icon name="share-external" size="22px" /><text>分享</text></button>
            <!-- #endif -->
            <!-- #ifdef H5 -->
            <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="detail-utility detail-share" role="button" aria-label="复制资料分享链接" @click="sharePaper"><wd-icon name="share-external" size="22px" /><text>分享</text></button>
            <!-- #endif -->
            <view class="download-button"><wd-button role="button" block :icon="paper.can_download ? 'download' : 'lock'" :loading="downloading" :disabled="!verified || loading || (!!session.user && paper.can_download && !external && !pdf) || downloading" @click="download">{{ actionLabel }}</wd-button></view>
          </view>
          <text v-if="!external && paper.can_download" class="download-guide">{{ pdfGuide }}</text>
        </view>
      </template>
      <view v-else-if="!loading && !error" class="state-block"><wd-empty icon="no-content" tip="未找到习题" /></view>
    </template>
    <wd-popup v-model="previewOpen" position="bottom" :z-index="1200" root-portal custom-style="width:100%;height:100%;border-radius:0">
      <PaperPreview v-if="paper?.can_view && previewOpen" :pages="pages" :paper-id="paper.id" :release="paper.release_number || 1" @close="previewOpen = false" />
    </wd-popup>
    <wd-popup v-model="groupOpen" position="bottom" :z-index="1200" :close-on-click-modal="!groupBusy" root-portal safe-area-inset-bottom custom-style="border-radius:22px 22px 0 0">
      <view class="sheet group-sheet" role="dialog" aria-modal="true" aria-label="选择收藏分组">
        <view class="sheet-handle" />
        <view class="sheet-head"><text class="sheet-title">选择收藏分组</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="bare-icon" role="button" aria-label="关闭收藏分组" :disabled="groupBusy" @click="groupOpen = false"><wd-icon name="close" size="20px" /></button></view>
        <view v-if="groupError" class="error-strip" role="alert">{{ groupError }}<wd-button variant="text" :disabled="groupBusy" @click="chooseGroup">刷新分组</wd-button></view><view class="group-create"><input v-model="groupName" class="group-name-input" maxlength="40" :disabled="groupBusy" placeholder="新分组名称，例如：期末复习" aria-label="新分组名称" confirm-type="done" @confirm="createAndAssignGroup" /><wd-button :loading="groupBusy" :disabled="groupBusy || !groupName.trim()" @click="createAndAssignGroup">新建并归组</wd-button></view><text v-if="!groupItems.length && !groupBusy" class="group-empty">还没有分组，可在这里创建并收藏这份资料</text>
        <scroll-view scroll-y class="group-options">
          <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="group-option" role="button" :disabled="groupBusy" @click="selectGroup(null)">移至未分组</button>
          <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-for="group in groupItems" :key="group.id" class="group-option" role="button" :disabled="groupBusy" @click="selectGroup(group.id)">{{ group.name }}</button>
        </scroll-view>
        <view v-if="groupBusy" class="loading-line"><wd-loading /><text>正在更新分组</text></view>
      </view>
    </wd-popup>
    <MembershipSheet :open="membershipOpen" @close="membershipOpen = false" @refreshed="load" />
    <wd-popup v-model="linkOpen" position="bottom" :z-index="1200" root-portal safe-area-inset-bottom custom-style="border-radius:22px 22px 0 0" @close="clearLink">
      <view v-if="linkOpen && linkTarget" class="sheet link-sheet" role="dialog" aria-modal="true" aria-label="网盘下载链接">
        <view class="sheet-handle" /><view class="sheet-head"><text class="sheet-title">网盘下载</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="bare-icon" role="button" aria-label="关闭网盘链接" @click="clearLink"><wd-icon name="close" size="20px" /></button></view>
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
.curriculum-tags { margin-top:14px; }.edition-choice { margin:0;font-size:13px;color:var(--lc-secondary); }.edition-picker { display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:48px;padding:10px 14px;margin-top:8px;background:var(--lc-background);border:1px solid var(--lc-border);border-radius:10px; }
.detail-service { display:flex;gap:16px;flex-wrap:wrap;margin:14px 0; }.version-notes text { display:block;font-size:12px;color:var(--lc-muted);margin:8px 0; }
.edition-segments { display:flex;gap:6px; }.edition-segments button { flex:1;min-width:0;min-height:54px;margin:0;padding:6px;border:1px solid var(--lc-border);border-radius:6px;background:var(--lc-surface);color:var(--lc-secondary);font-size:13px;line-height:1.5;overflow-wrap:anywhere; }.edition-segments button.selected { border-color:var(--lc-primary);background:var(--lc-primary-soft);color:var(--lc-primary); }.edition-size { display:block;font-size:12px;margin-top:2px; }
.group-create { display:flex;flex-direction:column;gap:12px;margin:14px 0; }.group-name-input { height:46px;padding:0 12px;background:var(--lc-background);border-radius:8px;font-size:14px; }.group-empty { display:block;font-size:13px;color:var(--lc-secondary);line-height:1.7;margin:12px 0; }.group-sheet { max-width:520px;margin:0 auto; }.group-options { height:32vh; }.group-option { width:100%;margin:0;padding:14px 0;background:transparent;color:var(--lc-text);font-size:15px;line-height:1.5;text-align:left;overflow-wrap:anywhere;border-bottom:1px solid var(--lc-card-line); }
.detail-page { padding-bottom: calc(180px + env(safe-area-inset-bottom)); }
.detail-page.has-editions { padding-bottom: calc(270px + env(safe-area-inset-bottom)); }
.detail-hero { background-color:var(--subject-tint);background-image:linear-gradient(160deg,#ffffff60,transparent);border-radius:0 0 24px 24px; }
.paper-stage { display: flex; align-items: center; justify-content: center; position: relative; min-height: 240px; padding: 16px 24px 60px; }
.preview-sheet { width: 192px; max-width: 72%; flex: none; box-shadow: 0 4px 16px #5261831f; border-radius: 2px; background: #fff; }
.preview-entry { display: block; padding: 0; margin: 0; line-height: 1.5; }
.preview-entry:active { opacity:.9; }
.locked-sheet { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 15px; height: 209px; color: var(--lc-warning); font-size: 13px; }
.preview-pill { position: absolute; bottom: 16px; right: 22px; display: flex; align-items: center; gap: 6px; min-height: 44px; padding: 6px 13px; margin: 0; border-radius: 999px; background: #fff; color: var(--lc-secondary); font-size: 12px; line-height: 1.5; box-shadow: 0 2px 9px #52618308; }
.preview-access { position: absolute; bottom: 24px; right: 22px; }
.detail-content { padding-top: 25px; padding-bottom: 22px; }
.detail-heading { padding-top:10px;padding-bottom:14px;background:var(--lc-surface); }.detail-heading .detail-title { margin-top:5px;font-size:21px; }
.detail-tags { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; color: var(--lc-primary); font-size: 12px; }
.detail-title { display: block; font-size: 23px; line-height: 1.5; font-weight: 650; margin-top: 10px; overflow-wrap: anywhere; }
.detail-meta { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; color: var(--lc-muted); font-size: 12px; margin-top: 9px; }
.detail-description { display: block; margin-top: 19px; color: var(--lc-secondary); font-size: 14px; line-height: 1.9; overflow-wrap: anywhere; white-space: pre-wrap; }
.detail-facts { display:flex;flex-direction:column;gap:16px;margin-top:20px;padding:16px;border:1px solid var(--lc-card-line);border-radius:var(--lc-radius-card);background:var(--lc-surface); }
.detail-facts > view { display: flex; align-items: center; gap: 10px; font-size: 13px; color: var(--lc-muted); }
.detail-facts :deep(.wd-icon) { flex: none; }
.fact-value { margin-left: auto; min-width: 0; max-width: 70%; overflow-wrap: anywhere; color: var(--lc-text); text-align: right; }
.vip-locked { display: flex; flex-direction: column; align-items: flex-start; gap: 5px; color: var(--lc-muted); font-size: 12px; margin-top: 25px; }
.preview-empty { padding-top: 22px; }
.detail-dock { position: fixed; z-index: 20; left: 50%; bottom: 0; transform: translateX(-50%); width: 100%; max-width: 520px; display: flex; flex-direction:column;gap:8px;padding:12px 22px calc(12px + env(safe-area-inset-bottom));background:#fff;border-top:1px solid var(--lc-card-line); }
.detail-actions { display:flex;align-items:center;gap:8px; }
.detail-utility { display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;flex:none;width:48px;min-height:49px;margin:0;padding:2px 0;background:transparent;border-radius:var(--lc-radius-control);color:var(--lc-secondary);font-size:12px;line-height:1.3; }
.detail-utility[disabled] { opacity:.5; }
.download-hint,.download-guide,.transfer-status,.download-error { display:block;font-size:12px;line-height:1.6;color:var(--lc-secondary); }
.download-guide { text-align:center; }
.download-error { color:#a34040; }
.transfer-status { color:var(--lc-primary); }
.detail-favorite.selected { color:var(--lc-coral); }
.download-button { flex: 1; min-width: 0; --wot-button-height-medium: 49px; }
@media (max-width: 359px) { .detail-title { font-size: 21px; } .detail-dock { padding-left: 17px; padding-right: 17px; } }
@media (max-height:680px) { .preview-sheet { width:152px; }.paper-stage { min-height:0;padding-top:10px; } }
@media (max-height:600px) { .has-editions .preview-sheet { width:128px; } }
</style>
