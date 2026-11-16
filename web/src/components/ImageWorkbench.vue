<script setup lang="ts">
import ImageResultPreview from './ImageResultPreview.vue'
import ImageWatermarkSettings from './ImageWatermarkSettings.vue'
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useExamStore } from '../stores/exam'
import { useAuthStore } from '../stores/auth'
import { captureWorkspaceGuard, fetchScope } from '../api'
import { TYPE_GROUPS_BY_GRADE, TYPE_GROUPS_DEFAULT, TYPE_NAME } from '../constants'
import { gradeNumOf } from '../utils'
import type { Difficulty, ScopeData } from '../types'
import { textbookGroups } from '../knowledge-points'
import { fetchImageOptions, imageWorksheetTitle, plannedImageQuestionCount, previewImagePrompt, type ImageWorksheetParams, type WorksheetImage } from '../image-generation'
import { useImageWatermark } from '../use-image-watermark'
import { useImageExports } from '../use-image-exports'
import { useImageDraft, validImageDraft } from '../use-image-draft'
import { MAX_WORKSHEET_IMAGES, useImageBatch } from '../image-batch'
import { MAX_IMAGE_CONCURRENCY, MAX_WORKSHEET_PDF_PAGES } from '../generation-limits'
import { publicationUrl, type ImagePublication } from '../image-publication'

const emit = defineEmits<{ library: [] }>()
const store = useExamStore()
const auth = useAuthStore()
const ImagePublicationDialog = defineAsyncComponent(() => import('./ImagePublicationDialog.vue'))
const ImageCloudSaveDialog = defineAsyncComponent(() => import('./ImageCloudSaveDialog.vue'))
const publicationOpen = ref(false)
const cloudOpen = ref(false)
const cloudSave = shallowRef<{ key: string; images: WorksheetImage[]; params: ImageWorksheetParams } | null>(null)
const dialogOpen = computed(() => publicationOpen.value || cloudOpen.value)
const publication = shallowRef<{ key: string; images: WorksheetImage[]; params: ImageWorksheetParams } | null>(null)
const publishedDrafts = ref<Record<string, ImagePublication>>({})
const owner = store.ownerId
const storageKey = 'lc_u' + owner + '_image_request'
const grade = ref(store.grade), subject = ref(store.subject), keyword = ref(store.keyword)
const gradeSelection = computed({ get: () => grade.value, set: chooseGrade })
const subjectSelection = computed({ get: () => subject.value, set: chooseSubject })
const difficulty = ref<Difficulty>(store.difficulty)
const selected = ref<string[]>([]), counts = ref<Record<string, number | null>>({})
const style = ref<ImageWorksheetParams['style']>('playful'), requirements = ref('')
const scope = ref<ScopeData | null>(null), scopeLoading = ref(false), scopeError = ref('')
const ready = ref(false), configured = ref(false), configError = ref('')
const error = ref(''), imageCount = ref(1), selectedPage = ref(0)
const parallelCount = ref(1), maxParallel = ref(1)
const parallelKey = storageKey + '_concurrency'
const prompt = ref(''), promptOpen = ref(false), promptBusy = ref(false)
const zoomOpen = ref(false)
const mobilePanel = ref<'settings' | 'preview'>('settings')
const followLatest = ref(true), historyOpen = ref(false)
const publishedKey = storageKey + '_published'
const knowledgeSearch = ref('')
const customOpen = ref(true)
const advancedOpen = ref(false)
const catalogPoints = computed(() => textbookGroups(scope.value).flatMap(group => group.items.map(item => item.value)))
const knowledgePoints = computed(() => catalogPoints.value.filter(point => point.includes(knowledgeSearch.value.trim())))
const suggestedKnowledge = computed(() => catalogPoints.value.slice(0, 4))
const chosenKnowledge = computed(() => keyword.value.split('、').map(point => point.trim()).filter(Boolean))
const activeStyle = computed(() => styles.find(item => item.value === style.value)!)
const difficulties = [{ value: 'easy' as const, label: '基础', description: '巩固知识' }, { value: 'medium' as const, label: '标准', description: '日常练习' }, { value: 'hard' as const, label: '提升', description: '进阶挑战' }]
const settingsFields = ref<HTMLElement | null>(null)
const previewScroll = ref<HTMLElement | null>(null)
let alive = true, scopeVersion = 0, promptVersion = 0
const ownerGuard = captureWorkspaceGuard()
const current = () => alive && store.ownerId === owner && !store.accountChanged
const batch = useImageBatch(storageKey, current, index => {
  if (followLatest.value) selectedPage.value = index
}, () => Math.min(parallelCount.value, maxParallel.value))
const busy = computed(() => batch.state.busy || batch.cacheBusy), checking = computed(() => batch.state.checking)
const generatingCount = computed(() => batch.state.pages.filter(page => page.state === 'running').length)
const result = computed(() => batch.state.pages[selectedPage.value]?.image)
const rangeStart = ref(1), rangeEnd = ref(1)
watch(() => batch.state.pages, pages => { rangeStart.value = 1; rangeEnd.value = pages.length || 1 }, { flush: 'sync' })
const rangeValid = computed(() => Number.isInteger(rangeStart.value) && Number.isInteger(rangeEnd.value)
  && rangeStart.value >= 1 && rangeEnd.value >= rangeStart.value && rangeEnd.value <= batch.state.pages.length)
// Retain original indexes in ZIP filenames even when exporting a middle range.
const rangePages = computed(() => batch.state.pages.map((page, index) =>
  rangeValid.value && index >= rangeStart.value - 1 && index < rangeEnd.value ? page.image : null))
const rangeImages = computed(() => rangePages.value.filter((image): image is WorksheetImage => !!image))
const exportCount = computed(() => rangeImages.value.length)
const completedKey = computed(() => rangeImages.value.map(image => image.request_id).join(','))
const savedDraft = computed(() => publishedDrafts.value[completedKey.value])
const imageUrl = computed(() => batch.state.pages[selectedPage.value]?.url || '')
const { watermarkEnabled, watermarkLabel, watermarkPosition, watermarkLayout, watermarkTransparency, watermarkIssue, downloadWatermark, watermarkPreview, watermarkPreviewBusy, watermarkPreviewError } = useImageWatermark(result, storageKey, current)
const { pdfBusy, pdfProgress, imagesBusy, imagesProgress, singleBusy, exportBusy, download, downloadImages, downloadPdf } = useImageExports({ imageUrl, result, selectedPage, rangePages, rangeImages, exportCount, busy, checking, dialogOpen, watermarkIssue, downloadWatermark, error, current, ownerGuard })

const previewImageUrl = computed(() => watermarkPreview.value || imageUrl.value)
const batchParams = computed(() => {
  const value = batch.parameters()
  return validImageDraft(value) ? value : null
})
const batchSummary = computed(() => {
  const value = batchParams.value
  if (!value) return ''
  return `${value.grade} · ${value.subject} · ${styles.find(item => item.value === value.style)?.label || ''} · ${quantitySummary(value.items)}`
})
const settingsChanged = computed(() => {
  const saved = batchParams.value, draft = params.value
  if (!saved) return false
  return (['grade', 'subject', 'keyword', 'difficulty', 'style', 'requirements'] as const).some(key => saved[key] !== draft[key])
    || batch.state.pages.length !== imageCount.value || saved.items.length !== draft.items.length
    || saved.items.some((item, index) => item.game_type !== draft.items[index]?.game_type || (item.question_count ?? null) !== draft.items[index]?.question_count)
})
const status = computed(() => {
  if (checking.value) return '正在查询生成结果'
  if (busy.value) {
    if (batch.state.paused) return generatingCount.value > 1 ? '进行中的图片完成后暂停' : '本张完成后暂停'
    if (batch.state.dispatchStopped) return '正在完成已发出的图片'
    if (batch.state.error) return '单张出错，正在继续生成其他图片'
    return generatingCount.value > 1 ? `正在同时生成 ${generatingCount.value} 张` : `正在生成第 ${Math.max(0, batch.state.pages.findIndex(page => page.state === 'running')) + 1} / ${batch.state.pages.length} 张`
  }
  if (batch.unresolved) return '生成结果待确认'
  if (!batch.remaining) return '本批图片已全部完成'
  if (retrying.value) return '部分图片未完成'
  if (batch.state.paused) return '本批次已暂停'
  return '还有图片等待生成'
})
const statusHint = computed(() => checking.value ? '正在找回已有图片，不会发起新的生成。'
  : busy.value ? batch.state.paused ? '已发出的图片会继续完成并保留，后续图片等你继续。'
    : batch.state.dispatchStopped ? '已暂停后续图片；正在收取已发出请求的结果，已生成的图片会保留。'
      : batch.state.error ? '失败图片已记录，其他图片会继续生成；完成后可查询未确认结果或重试失败图片。'
        : '完成一张就接着生成下一张；图片按原序号保存，可查看和下载已完成的图片。'
  : batch.unresolved ? '只查询原请求结果，不会重复生成；也可点击下方手动查询。'
  : !batch.remaining ? '可下载单张图片、批量下载图片，或合并为 PDF 打印。'
  : !batchParams.value ? '原批次设置无法读取，请重新设置并新建批次，已完成的图片仍可下载。'
  : retrying.value ? '继续生成会重试未完成的图片，可能产生新的费用；已完成的图片会保留。'
  : '点击继续即可完成剩余图片，已完成的图片会保留。')
const retrying = computed(() => batch.state.pages.some(page => page.state === 'failed' || page.state === 'expired'))
const subjects = computed(() => store.available[grade.value] || [])
const types = computed(() => (TYPE_GROUPS_BY_GRADE[subject.value]?.[gradeNumOf(grade.value)] || TYPE_GROUPS_DEFAULT).flatMap(group => group[1]))
const minimumTotal = computed(() => selected.value.reduce((sum, type) => sum + (counts.value[type] ?? 1), 0))
const issue = computed(() => !grade.value || !subject.value ? '请先选择年级和科目' : selected.value.length > 5 ? '每张图片最多选择 5 种题型' : minimumTotal.value > 24 ? '每张图片最多安排 24 道题，请减少题量' : '')
const disabled = computed(() => busy.value || checking.value || batch.unresolved || exportBusy.value || dialogOpen.value || !current())
const rangeDisabled = computed(() => busy.value || checking.value || exportBusy.value || dialogOpen.value || !current())
const hasSettings = computed(() => !!(grade.value || subject.value || keyword.value || selected.value.length ||
  requirements.value || difficulty.value !== 'medium' || imageCount.value !== 1))
const params = computed<ImageWorksheetParams>(() => ({ grade: grade.value, subject: subject.value, keyword: keyword.value.trim(), difficulty: difficulty.value,
  items: selected.value.map(game_type => ({ game_type, question_count: counts.value[game_type] ?? null })), style: style.value, requirements: requirements.value.trim(), image_count: imageCount.value, image_index: 1 }))
const plannedCount = computed(() => plannedImageQuestionCount(params.value.items))
const { draftLoaded, draftStatus } = useImageDraft(params, storageKey, current, applyParams)
function quantitySummary(items: ImageWorksheetParams['items']) {
  if (!items.length) return '题型、题量自动安排'
  const count = plannedImageQuestionCount(items)
  if (count !== undefined) return `${count} 题 / 张`
  const specified = items.reduce((sum, item) => sum + (item.question_count ?? 0), 0)
  return specified ? `已指定 ${specified} 题，其余自动` : '题量自动安排'
}
const styles = [{ value: 'playful' as const, label: '童趣彩色', icon: 'i-lucide-palette' }, { value: 'clean' as const, label: '简洁清爽', icon: 'i-lucide-sparkles' }, { value: 'black_white' as const, label: '黑白打印', icon: 'i-lucide-printer' }]
const arrangements = computed(() => [
  { label: '轻量练习', description: '选择 + 填空', items: [{ game_type: 'quiz', question_count: null }, { game_type: 'fill_blank', question_count: null }] },
  { label: '综合练习', description: types.value.includes('true_false') ? '选择 + 填空 + 判断' : '选择 + 填空 + 配对', items: [
    { game_type: 'quiz', question_count: null }, { game_type: 'fill_blank', question_count: null },
    { game_type: types.value.includes('true_false') ? 'true_false' : 'match_pair', question_count: null },
  ] },
])
const arrangementSelected = (items: ImageWorksheetParams['items']) => selected.value.length === items.length && items.every(item => selected.value.includes(item.game_type) && counts.value[item.game_type] === item.question_count)
const typeSummary = computed(() => selected.value.map(type => `${TYPE_NAME[type]} ${counts.value[type] == null ? '自动' : counts.value[type] + ' 题'}`).join(' · '))
function applyArrangement(items: ImageWorksheetParams['items']) {
  if (disabled.value || !subject.value) return
  selected.value = items.map(item => item.game_type)
  counts.value = Object.fromEntries(items.map(item => [item.game_type, item.question_count ?? null]))
}
function editSettings() {
  mobilePanel.value = 'settings'
  void nextTick(() => {
    if (!current()) return
    settingsFields.value?.scrollTo?.({ top: 0 })
    settingsFields.value?.querySelector<HTMLSelectElement>('select')?.focus({ preventScroll: true })
  })
}
function showResults() {
  mobilePanel.value = 'preview'
  void nextTick(() => { if (current()) previewScroll.value?.scrollTo?.({ top: 0 }) })
}
function reuseSettings() {
  if (disabled.value || !batchParams.value) return
  applyParams({ ...batchParams.value, image_count: batch.state.pages.length })
  editSettings()
}
function clearSettings() {
  if (disabled.value || !draftLoaded.value || !hasSettings.value ||
    !window.confirm('清空年级、科目、知识点、题型题量和补充要求，并恢复默认难度与张数？画面风格、已生成的图片和历史批次会保留。')) return
  applyParams({ grade: '', subject: '', keyword: '', difficulty: 'medium', items: [], style: style.value,
    requirements: '', image_count: 1 })
  scopeVersion++; scope.value = null; scopeLoading.value = false; scopeError.value = ''
  knowledgeSearch.value = ''; error.value = ''; promptVersion++; prompt.value = ''; promptOpen.value = false
  customOpen.value = true; advancedOpen.value = false
  editSettings()
}
async function continueBatch() {
  if (!batch.canContinue || !batchParams.value || !configured.value || exportBusy.value || dialogOpen.value || !current()) return
  error.value = ''; showResults(); followLatest.value = true
  selectedPage.value = Math.max(0, batch.state.pages.findIndex(page => page.state !== 'ready'))
  await batch.run()
}
async function recoverBatch() {
  if (busy.value || checking.value || exportBusy.value || dialogOpen.value || !current()) return
  error.value = ''; showResults()
  await batch.recover()
}
async function regenerateCurrent() {
  const index = selectedPage.value
  if (busy.value || checking.value || exportBusy.value || dialogOpen.value || !current() || !batch.state.pages[index]?.image) return
  if (!window.confirm(`重新生成第 ${index + 1} 张图片？这会产生新的生图请求费用，其他图片不会改变。`)) return
  error.value = ''; followLatest.value = false; showResults()
  await batch.regenerate(index)
}

function chooseGrade(value: string) {
  if (grade.value === value) return
  grade.value = value; subject.value = ''; keyword.value = ''; selected.value = []
}
function chooseSubject(value: string) { if (subject.value === value) return; subject.value = value; keyword.value = ''; selected.value = [] }
function toggleType(type: string) {
  if (selected.value.includes(type)) selected.value = selected.value.filter(item => item !== type)
  else if (selected.value.length < 5 && minimumTotal.value < 24) { counts.value[type] = null; selected.value.push(type) }
}
function chooseKnowledge(value: string) {
  const values = keyword.value.split('、').map(item => item.trim()).filter(Boolean)
  const next = values.includes(value) ? values.filter(item => item !== value) : [...values, value]
  if (next.join('、').length <= 100) keyword.value = next.join('、')
}
async function loadScope() {
  const revision = ++scopeVersion
  scope.value = null; scopeError.value = ''
  if (!grade.value || !subject.value) { scopeLoading.value = false; return }
  scopeLoading.value = true
  try { const value = await fetchScope(grade.value, subject.value); if (current() && revision === scopeVersion) scope.value = value }
  catch (e) { if (current() && revision === scopeVersion) scopeError.value = e instanceof Error ? e.message : '知识点加载失败' }
  finally { if (current() && revision === scopeVersion) scopeLoading.value = false }
}
watch([grade, subject], () => { knowledgeSearch.value = ''; void loadScope() }, { immediate: true })
watch(params, () => { prompt.value = ''; promptVersion++ }, { flush: 'sync' })
function applyParams(saved: ImageWorksheetParams) {
  grade.value = saved.grade; subject.value = saved.subject; keyword.value = saved.keyword
  difficulty.value = saved.difficulty; style.value = saved.style; requirements.value = saved.requirements
  selected.value = saved.items.map(item => item.game_type)
  counts.value = Object.fromEntries(saved.items.map(item => [item.game_type, item.question_count ?? null]))
  imageCount.value = saved.image_count || 1
}
async function openHistory(id: string) {
  if (disabled.value) return
  followLatest.value = false; selectedPage.value = 0
  await batch.selectHistory(id)
  historyOpen.value = false; showResults()
}
function choosePage(index: number) { followLatest.value = false; selectedPage.value = index }
function updateCount(type: string, value: number | undefined) {
  counts.value[type] = value == null || !Number.isFinite(Number(value)) || String(value) === '' ? null
    : Math.max(1, Math.min(Math.floor(value), maxCount(type)))
}
function maxCount(type: string) {
  return Math.max(1, Math.min(20, 24 - minimumTotal.value + (counts.value[type] ?? 1)))
}
function specifyCount(type: string, checked: boolean | 'indeterminate') {
  counts.value[type] = checked === true ? Math.min(4, maxCount(type)) : null
}
async function loadOptions() {
  configError.value = ''; ready.value = false
  try {
    const value = await fetchImageOptions(); ownerGuard()
    if (current()) {
      maxParallel.value = Number.isInteger(value.max_concurrency) ? Math.max(1, Math.min(MAX_IMAGE_CONCURRENCY, value.max_concurrency!)) : 1
      let preferred = value.default_concurrency ?? 1
      try {
        const saved = Number(localStorage.getItem(parallelKey))
        if (Number.isInteger(saved) && saved >= 1) preferred = saved
      } catch { /* A saved preference is optional. */ }
      parallelCount.value = Number.isInteger(preferred) ? Math.max(1, Math.min(maxParallel.value, preferred)) : 1
      configured.value = value.configured; ready.value = true
    }
  }
  catch (e) { if (current()) configError.value = e instanceof Error ? e.message : '生图服务状态加载失败' }
}
watch(parallelCount, value => {
  if (!current()) return
  try { localStorage.setItem(parallelKey, String(value)) } catch { /* Does not affect request persistence. */ }
})
async function previewPrompt() {
  if (issue.value || promptBusy.value || !current()) return
  promptBusy.value = true; error.value = ''
  const revision = ++promptVersion
  try {
    const value = await previewImagePrompt(params.value); ownerGuard()
    if (current() && revision === promptVersion) { prompt.value = value.prompt; promptOpen.value = true }
  } catch (e) { if (current() && revision === promptVersion) error.value = e instanceof Error ? e.message : '提示词加载失败' }
  finally { if (current()) promptBusy.value = false }
}
async function generate() {
  if (disabled.value || issue.value || !ready.value || !configured.value) return
  ownerGuard(); error.value = ''; selectedPage.value = 0; followLatest.value = true; showResults()
  try { await batch.start(params.value, imageCount.value) }
  catch (cause) { if (current()) error.value = cause instanceof Error ? cause.message : '生成失败' }
}
async function clearHistoryImages() {
  if (window.confirm('清理当前账号的历史图片缓存？当前批次保留，历史图片若云端缓存也已过期将无法找回，请先下载重要图片。')) await batch.clearHistoryCache()
}
function openCloudSave() {
  if (busy.value || checking.value || exportBusy.value || dialogOpen.value || !current() || !exportCount.value || !batchParams.value) return
  if (exportCount.value > MAX_WORKSHEET_PDF_PAGES) { error.value = `一份云端 PDF 最多 ${MAX_WORKSHEET_PDF_PAGES} 页，请缩小保存范围`; return }
  if (cloudSave.value?.key !== completedKey.value) {
    cloudSave.value = { key: completedKey.value,
      images: [...rangeImages.value],
      params: JSON.parse(JSON.stringify(batchParams.value)) }
  }
  cloudOpen.value = true
}
function openCloudLibrary() { cloudOpen.value = false; emit('library') }
function openPublication() {
  if (disabled.value || auth.user?.role !== 'admin' || !exportCount.value) return
  if (exportCount.value > MAX_WORKSHEET_PDF_PAGES) { error.value = `一份 PDF 最多 ${MAX_WORKSHEET_PDF_PAGES} 页，请缩小保存范围`; return }
  if (publication.value?.key !== completedKey.value) {
    publication.value = { key: completedKey.value,
      images: [...rangeImages.value],
      params: batch.parameters() || JSON.parse(JSON.stringify(params.value)) }
  }
  publicationOpen.value = true
}
function publicationSaved(paper: ImagePublication) {
  if (current() && publication.value) {
    publishedDrafts.value[publication.value.key] = paper
    try { localStorage.setItem(publishedKey, JSON.stringify(publishedDrafts.value)) } catch { error.value = '草稿已保存到后台，但本机未能记住链接。' }
  }
}
onMounted(() => {
  void loadOptions()
  try {
    const saved = JSON.parse(localStorage.getItem(publishedKey) || '{}')
    if (saved && typeof saved === 'object' && !Array.isArray(saved)) publishedDrafts.value = Object.fromEntries(Object.entries(saved).filter(([, paper]) => typeof (paper as ImagePublication)?.id === 'string')) as Record<string, ImagePublication>
  } catch { /* Ignore malformed saved links. */ }
  void batch.restore().then(() => { if (current() && batch.state.pages.length) showResults() })

})
onBeforeUnmount(() => { alive = false; scopeVersion++; promptVersion++; batch.dispose() })
</script>

<template>
  <section class="image-workbench" :data-mobile-panel="mobilePanel" aria-label="图片出题">
    <nav class="image-mobile-tabs" aria-label="工作区切换">
      <button type="button" :aria-pressed="mobilePanel === 'settings'" @click="mobilePanel = 'settings'">出题设置</button>
      <button type="button" :aria-pressed="mobilePanel === 'preview'" @click="mobilePanel = 'preview'">
        {{ batch.state.pages.length ? '生成结果' : '效果预览' }} <span v-if="batch.completed">{{ batch.completed }}</span>
        <UIcon v-if="busy || checking" name="i-lucide-loader-circle" class="size-3 animate-spin" />
      </button>
    </nav>
    <div v-if="error || batch.storageError || configError || (ready && !configured)" class="image-notices">
      <UAlert v-if="configError" :title="configError" color="error" :actions="[{ label: '重新检查', onClick: loadOptions }]" />
      <UAlert v-else-if="ready && !configured" title="生图服务尚未配置" description="请在后台模型配置中设置图片生成接口。" color="warning" :actions="[{ label: '重新检查', onClick: loadOptions }]" />
      <p v-if="error" role="alert" class="text-sm text-error">{{ error }}</p>
      <p v-if="batch.storageError" role="alert" class="text-xs text-warning">{{ batch.storageError }}</p>
    </div>

    <div class="image-controls">
      <div class="image-panel-heading">
        <div><h2>设计一份习题图</h2><p class="image-service" :class="{ online: ready && configured }">{{ configError ? '连接异常' : !ready ? '检查中' : configured ? '服务就绪' : '待配置' }}</p></div>
        <UButton type="button" label="清空设置" icon="i-lucide-eraser" color="neutral" variant="outline" size="sm" class="shrink-0" :disabled="disabled || !draftLoaded || !hasSettings" @click="clearSettings" />
      </div>
      <form class="image-form" @submit.prevent="generate">
        <fieldset ref="settingsFields" :disabled="disabled" class="image-fields">
          <section class="image-setting-section">
            <div class="image-section-title"><span>1</span><h3>练什么</h3></div>
            <div v-if="store.availableLoading" role="status">正在加载年级…</div>
            <UAlert v-else-if="store.availableError" :title="store.availableError" color="error" :actions="[{ label: '重试', onClick: () => store.init() }]" />
            <div v-else class="image-select-row">
              <label class="image-select-field">年级
                <select v-model="gradeSelection" aria-label="图片年级">
                  <option value="" disabled>选择年级</option>
                  <option v-for="value in Object.keys(store.available)" :key="value" :value="value">{{ value }}</option>
                </select>
              </label>
              <label class="image-select-field">科目
                <select v-model="subjectSelection" aria-label="图片科目" :disabled="!grade || disabled">
                  <option value="" disabled>{{ grade ? '选择科目' : '先选年级' }}</option>
                  <option v-for="value in subjects" :key="value" :value="value">{{ value }}</option>
                </select>
              </label>
            </div>
            <div>
              <label for="image-keyword" class="image-label">知识点 <small>选填</small></label>
              <UTextarea id="image-keyword" v-model="keyword" aria-label="图片知识点" placeholder="自动选择本年级、本科目的知识点" :rows="2" maxlength="100" :disabled="!subject || disabled" class="w-full" />
              <p class="image-field-hint"><span>可输入多个知识点，用「、」分隔</span><span>{{ keyword.length }}/100</span></p>
              <p v-if="scopeLoading" role="status" class="image-field-hint">正在加载课程知识点…</p>
              <div v-else-if="suggestedKnowledge.length" class="image-suggestions" aria-label="推荐知识点">
                <button v-for="point in suggestedKnowledge" :key="point" type="button" :aria-pressed="chosenKnowledge.includes(point)" :class="{ selected: chosenKnowledge.includes(point) }" @click="chooseKnowledge(point)">{{ point }}</button>
              </div>
              <details v-if="subject" class="image-knowledge" :open="!!scopeError || undefined">
                <summary>查找更多知识点</summary>
                <UAlert v-if="scopeError" :title="scopeError" color="error" :actions="[{ label: '重试', onClick: loadScope }]" />
                <div v-else>
                  <UInput v-model="knowledgeSearch" aria-label="搜索知识点" placeholder="搜索课程知识点" icon="i-lucide-search" class="w-full mt-3" />
                  <div class="image-knowledge-list">
                    <button v-for="point in knowledgePoints" :key="point" type="button" :aria-pressed="chosenKnowledge.includes(point)" :class="{ selected: chosenKnowledge.includes(point) }" @click="chooseKnowledge(point)">{{ point }}</button>
                    <p v-if="!knowledgePoints.length" class="image-field-hint">{{ knowledgeSearch ? '没有匹配项，可直接在上方输入' : '暂无推荐知识点，请在上方输入' }}</p>
                  </div>
                </div>
              </details>
            </div>
          </section>

          <section class="image-setting-section">
            <div class="image-section-title"><span>2</span><h3>怎么练</h3><small>每张最多 24 题</small></div>
            <div class="image-arrangements" role="group" aria-label="快速选择题型">
              <button v-for="item in arrangements" :key="item.label" type="button" :disabled="!subject" :aria-pressed="arrangementSelected(item.items)" :class="{ selected: arrangementSelected(item.items) }" @click="applyArrangement(item.items)">
                <strong>{{ item.label }} <b>{{ item.items.length }} 类</b></strong>
                <small>{{ item.description }}</small>
              </button>
            </div>
            <details class="image-custom" :open="customOpen" @toggle="customOpen = ($event.target as HTMLDetailsElement).open">
              <summary><span>题型与题量 <small class="image-optional">选填</small></span><small>{{ selected.length ? typeSummary : '题型、题量自动安排' }}</small></summary>
              <div class="image-custom-body">
                <div class="image-type-grid" role="group" aria-label="题型">
                  <button v-for="type in types" :key="type" type="button" :disabled="!subject || ((selected.length >= 5 || minimumTotal >= 24) && !selected.includes(type))" :aria-pressed="selected.includes(type)" :class="{ selected: selected.includes(type) }" @click="toggleType(type)">
                    <UIcon :name="selected.includes(type) ? 'i-lucide-circle-check' : 'i-lucide-circle-plus'" class="size-3.5" />{{ TYPE_NAME[type] }}
                  </button>
                </div>
                <UButton v-if="selected.length" type="button" label="恢复自动题型" icon="i-lucide-rotate-ccw" variant="ghost" color="neutral" size="sm" :disabled="disabled" @click="selected = []" />
                <div v-if="selected.length" class="image-counts">
                  <div v-for="type in selected" :key="type" class="image-count-row">
                    <span>{{ TYPE_NAME[type] }}</span>
                    <UCheckbox :model-value="counts[type] != null" :aria-label="TYPE_NAME[type] + '指定题量'" label="指定题量" :disabled="disabled" size="sm" @update:model-value="specifyCount(type, $event)" />
                    <UInputNumber v-if="counts[type] != null" :model-value="counts[type]!" :aria-label="TYPE_NAME[type] + '题量'" :min="1" :max="maxCount(type)" :disabled="disabled" size="sm" class="image-count-value" @update:model-value="updateCount(type, $event)" />
                    <small v-else class="image-count-auto">自动安排</small>
                  </div>
                </div>
                <p class="image-field-hint">已选 {{ selected.length }}/5 种题型 · {{ quantitySummary(params.items) }}</p>
              </div>
            </details>
            <label class="image-select-field">难度
              <select v-model="difficulty" aria-label="图片难度"><option v-for="item in difficulties" :key="item.value" :value="item.value">{{ item.label }} · {{ item.description }}</option></select>
            </label>
            <div>
              <label class="image-label" id="image-style-label">画面风格</label>
              <div class="image-style-grid" role="group" aria-labelledby="image-style-label">
                <button v-for="item in styles" :key="item.value" type="button" :aria-pressed="style === item.value" :class="{ selected: style === item.value }" @click="style = item.value">
                  <span class="image-style-sample" :data-style="item.value" aria-hidden="true"><UIcon :name="item.icon" class="size-5" /><i></i><i></i></span><strong>{{ item.label }}</strong>
                </button>
              </div>
            </div>
            <details class="image-advanced" :open="advancedOpen" @toggle="advancedOpen = ($event.target as HTMLDetailsElement).open">
              <summary>补充要求与生成说明 <small>选填</small></summary>
              <div class="image-custom-body">
                <UTextarea v-model="requirements" aria-label="补充要求" :rows="3" maxlength="600" placeholder="例如：用小动物插画，每题多留一点书写空间" :disabled="disabled" class="w-full" />
                <UButton type="button" label="查看生成说明" icon="i-lucide-text-search" variant="ghost" color="neutral" :disabled="!!issue || disabled" :loading="promptBusy" @click="previewPrompt" />
              </div>
            </details>
          </section>
        </fieldset>
        <div class="image-generate-actions">
          <template v-if="busy || checking || batch.unresolved">
            <p class="image-field-hint">{{ busy ? '本批次生成中，完成后可调整设置' : '确认本批次结果后，可开始新的生成' }}</p>
            <UButton type="button" label="查看生成进度" icon="i-lucide-arrow-right" block size="lg" @click="showResults" />
          </template>
          <template v-else>
            <div class="image-action-row"><span class="image-order-summary">{{ imageCount }} 张{{ plannedCount === undefined ? ' · ' + quantitySummary(params.items) : ' × ' + plannedCount + ' 题' }}</span><span v-if="draftStatus" class="image-draft-status" :title="draftStatus">{{ draftStatus.includes('未能') ? draftStatus : '设置已保存' }}</span></div>
            <p v-if="issue" class="image-field-hint">{{ issue }}</p>
            <p v-else-if="batch.state.pages.length" class="image-field-hint">{{ settingsChanged ? '设置已调整，生成后将创建新批次' : '会创建新批次，当前图片保留在历史中' }}</p>
            <label class="image-parallel-setting">同时生成
              <select v-model.number="parallelCount" aria-label="同时生成图片数" :disabled="disabled || !ready">
                <option v-for="count in maxParallel" :key="count" :value="count">{{ count }} 张</option>
              </select>
              <span>完成一张后自动接着生成</span>
            </label>
            <div class="image-generate-row">
              <div class="image-generate-count"><label for="image-generation-count" class="image-label">生成张数</label><UInputNumber id="image-generation-count" v-model="imageCount" aria-label="生成张数" :min="1" :max="MAX_WORKSHEET_IMAGES" :disabled="disabled" size="lg" class="w-full" /></div>
              <UButton type="submit" :label="batch.state.pages.length ? `按当前设置新建 ${imageCount} 张` : `生成 ${imageCount} 张图片`" icon="i-lucide-image-plus" class="image-generate-button" block size="lg" :disabled="disabled || !!issue || !ready || !configured" />
            </div>
          </template>
        </div>
      </form>
    </div>

    <div class="image-preview-panel">
      <header class="image-preview-heading">
        <div><h2>{{ batch.state.pages.length ? '生成结果' : '效果预览' }}</h2><p>{{ batch.state.pages.length ? '查看本批图片，下载后即可打印' : '随设置更新，生成前先看看安排' }}</p></div>
        <div class="image-library-actions"><UButton label="云端试卷" icon="i-lucide-cloud" color="neutral" variant="ghost" :disabled="exportBusy || dialogOpen || !current()" @click="openCloudLibrary" /><UButton label="历史批次" icon="i-lucide-history" color="neutral" variant="ghost" :disabled="disabled || !batch.history.length" @click="historyOpen = true" /></div>
      </header>
      <div ref="previewScroll" class="image-preview-scroll">
        <div v-if="batch.state.pages.length" class="image-batch-card">
          <div class="image-batch-title"><div><h3>{{ batchParams ? batchParams.keyword || imageWorksheetTitle(batchParams) : '习题图片' }}</h3><p>{{ batchSummary }}</p></div><UButton v-if="batchParams" label="复用设置" icon="i-lucide-copy" color="neutral" variant="ghost" size="sm" :disabled="disabled" @click="reuseSettings" /></div>
          <div class="image-batch-status" role="status" aria-live="polite">
            <div><UIcon :name="busy || checking ? 'i-lucide-loader-circle' : batch.unresolved || retrying ? 'i-lucide-circle-alert' : batch.remaining ? 'i-lucide-pause' : 'i-lucide-circle-check'" class="size-4" :class="{ 'animate-spin': busy || checking }" /><strong>{{ status }}</strong><span>已完成 {{ batch.completed }} / {{ batch.state.pages.length }} 张</span></div>
            <progress :value="batch.completed" :max="batch.state.pages.length" aria-label="图片生成进度" />
            <p>{{ statusHint }}</p>
          </div>
          <p v-if="batch.state.error" role="alert" class="image-batch-error">{{ batch.state.error }}</p>
          <div v-if="batch.state.pages.length > 1" class="image-export-range">
            <span>下载和保存范围</span>
            <UInputNumber :model-value="rangeStart" aria-label="范围起始张数" :min="1" :max="batch.state.pages.length" :disabled="rangeDisabled" @update:model-value="rangeStart = Number($event)" />
            <span>至</span>
            <UInputNumber :model-value="rangeEnd" aria-label="范围结束张数" :min="1" :max="batch.state.pages.length" :disabled="rangeDisabled" @update:model-value="rangeEnd = Number($event)" />
            <UButton label="全部图片" color="neutral" variant="ghost" :disabled="rangeDisabled" @click="rangeStart = 1; rangeEnd = batch.state.pages.length" />
            <p v-if="!rangeValid" role="alert">请选择有效范围，结束张数不能小于起始张数。</p>
            <p v-else>已选 {{ exportCount }} 张成品；未完成的图片会跳过。PDF 每份最多 {{ MAX_WORKSHEET_PDF_PAGES }} 页、32 MB，可分段保存。</p>
          </div>
          <ImageWatermarkSettings v-if="batch.completed" v-model:enabled="watermarkEnabled" v-model:text="watermarkLabel" v-model:position="watermarkPosition" v-model:layout="watermarkLayout" v-model:transparency="watermarkTransparency" :disabled="exportBusy || dialogOpen || !current()" :watermark-issue="watermarkIssue" :watermark-preview-error="watermarkPreviewError" :watermark-preview-busy="watermarkPreviewBusy" :watermark-preview="watermarkPreview" />
          <div class="image-batch-actions">
            <UButton v-if="busy && batch.remaining > 1" :label="batch.state.paused ? generatingCount > 1 ? '等待进行中的图片完成' : '等待本张完成' : '暂停后续生成'" icon="i-lucide-pause" color="neutral" variant="outline" :disabled="batch.state.paused" @click="batch.pause" />
            <UButton v-if="!busy && (checking || batch.unresolved)" label="查询本次结果" icon="i-lucide-refresh-cw" :loading="checking" :disabled="checking || exportBusy || dialogOpen || !current()" @click="recoverBatch" />
            <UButton v-else-if="batch.canContinue" :label="`继续生成剩余 ${batch.remaining} 张`" icon="i-lucide-play" :disabled="!batchParams || !configured || exportBusy || dialogOpen || !current()" @click="continueBatch" />
            <UButton v-if="batch.completed" :label="`批量下载图片（${exportCount} 张）`" icon="i-lucide-images" :color="batch.remaining ? 'neutral' : 'primary'" :variant="batch.remaining ? 'outline' : 'solid'" :loading="imagesBusy" :disabled="busy || checking || exportBusy || dialogOpen || !current() || !exportCount || !!watermarkIssue" @click="downloadImages" />
            <UButton v-if="batch.completed" label="保存到云端" icon="i-lucide-cloud-upload" color="neutral" variant="outline" :disabled="busy || checking || exportBusy || dialogOpen || !current() || !batchParams || !exportCount" @click="openCloudSave" />
            <UButton v-if="batch.completed" :label="`下载 PDF（${exportCount} 页）`" icon="i-lucide-file-down" color="neutral" variant="outline" :loading="pdfBusy" :disabled="busy || checking || exportBusy || dialogOpen || !current() || !exportCount || !!watermarkIssue" @click="downloadPdf" />
            <UButton v-if="!busy && !checking && !batch.remaining" label="调整设置，再出一组" color="neutral" variant="outline" @click="editSettings" />
          </div>
          <p v-if="pdfProgress" role="status" class="image-field-hint">{{ pdfProgress }}</p>
          <p v-if="imagesProgress" role="status" class="image-field-hint">{{ imagesProgress }}</p>
          <p v-else-if="batch.completed" class="image-field-hint">批量下载会将已完成的图片打包为 ZIP，解压后可获得每张{{ watermarkEnabled ? '带水印的 PNG 图片' : ' PNG 原图' }}。</p>
          <details class="image-cache-settings"><summary>本机图片缓存：{{ (batch.cacheUsage.bytes / 1024 / 1024).toFixed(1) }} / {{ batch.cacheUsage.limit / 1024 / 1024 }} MiB</summary>
            <p class="image-field-hint">优先清理较早批次，当前批次受保护。缓存被清理后仅能尝试从云端找回，重要图片请及时下载或保存到云端。</p>
            <UButton label="清理历史图片缓存" size="sm" variant="outline" :loading="batch.cacheBusy" :disabled="busy || checking || exportBusy || dialogOpen" @click="clearHistoryImages" />
          </details>
          <p v-if="batch.cacheNotice" role="status" class="image-field-hint">{{ batch.cacheNotice }}</p>
        </div>

        <template v-if="batch.state.pages.length">
          <ImageResultPreview :pages="batch.state.pages" :selected-page="selectedPage" :busy="busy" :checking="checking" :export-busy="exportBusy" :single-busy="singleBusy" :active="current()" :follow-latest="followLatest" :image-url="imageUrl" :preview-image-url="previewImageUrl" :watermark-preview="watermarkPreview" :watermark-issue="watermarkIssue" :result="result" @select="choosePage" @zoom="zoomOpen = true" @regenerate="regenerateCurrent" @download="download" @follow="followLatest = true; selectedPage = Math.max(0, batch.state.pages.map(page => !!page.image).lastIndexOf(true))" />
          <div v-if="batch.completed && auth.user?.role === 'admin'" class="image-admin-actions">
            <UButton v-if="savedDraft" label="查看后台草稿" icon="i-lucide-arrow-up-right" :href="publicationUrl(savedDraft.id)" target="_blank" color="neutral" variant="ghost" />
            <UButton v-else label="添加到后台" color="neutral" variant="ghost" icon="i-lucide-library-big" :disabled="disabled" @click="openPublication" />
          </div>
        </template>
        <div v-else class="image-design-preview">
          <div class="image-preview-intro"><span class="image-eyebrow"><UIcon name="i-lucide-notebook-pen" class="size-4" /> 你的下一份练习</span><h3>习题预览</h3><p>{{ selected.length ? typeSummary : '题型、题量自动安排' }}</p></div>
          <div class="image-paper" :data-style="style">
            <div class="image-paper-top"><span>{{ grade || '选择年级' }} · {{ subject || '选择科目' }}</span><UIcon :name="activeStyle.icon" class="size-6" /></div>
            <h4>{{ keyword.trim() || (grade && subject ? imageWorksheetTitle(params) : '我的专属练习') }}</h4><p class="image-paper-meta">姓名 __________　日期 __________</p><div class="image-paper-rule"></div>
            <div v-if="!selected.length" class="image-paper-placeholder"><UIcon name="i-lucide-sparkles" class="size-6" /><p>题型自动安排</p><span>题量自动安排</span></div>
            <div v-for="(type, index) in selected" :key="type" class="image-paper-exercise"><div><span>{{ String(index + 1).padStart(2, '0') }}</span><strong>{{ TYPE_NAME[type] }}</strong><small>{{ counts[type] == null ? '自动安排' : counts[type] + ' 题' }}</small></div><div class="image-paper-lines"><i></i><i></i></div></div>
            <div class="image-paper-bottom"><span>{{ activeStyle.label }}</span><span>{{ quantitySummary(params.items) }} · {{ imageCount }} 张</span></div>
          </div>
          <p class="image-preview-disclaimer"><UIcon name="i-lucide-info" class="size-3.5" /> 配置示意，实际题目与版面将在生成后呈现</p>
          <UButton class="image-back-settings" label="返回设置，开始出题" icon="i-lucide-arrow-left" color="neutral" variant="outline" @click="editSettings" />
        </div>
      </div>
      <div class="image-mobile-result-footer" v-if="batch.state.pages.length"><UButton label="返回出题设置" icon="i-lucide-sliders-horizontal" color="neutral" variant="ghost" block @click="editSettings" /></div>
    </div>

    <UModal v-model:open="historyOpen" title="历史批次" description="保留本机最近 10 个历史批次；清理浏览器数据会移除记录，请及时下载重要图片。"><template #body><div class="image-history-list"><button v-for="entry in batch.history" :key="entry.id" type="button" :disabled="disabled" @click="openHistory(entry.id)"><strong>{{ entry.title || '习题图片' }}</strong><span>{{ new Date(entry.savedAt).toLocaleString() }}</span><UIcon name="i-lucide-chevron-right" class="size-4" /></button></div></template></UModal>
    <ImagePublicationDialog v-if="publication" :key="publication.key" :open="publicationOpen" :images="publication.images" :params="publication.params" @close="publicationOpen = false" @saved="publicationSaved" />
    <ImageCloudSaveDialog v-if="cloudSave" :key="cloudSave.key" :open="cloudOpen" :images="cloudSave.images" :params="cloudSave.params" @close="cloudOpen = false" @library="openCloudLibrary" />
    <UModal v-model:open="promptOpen" title="生成说明" description="根据当前设置整理的出题要求，可关闭后继续调整。" :ui="{ content: 'max-w-2xl' }"><template #body><pre class="image-prompt-text">{{ prompt }}</pre></template></UModal>
    <UModal v-model:open="zoomOpen" :title="`习题图片 · 第 ${selectedPage + 1} 张`" :ui="{ content: 'max-w-5xl' }"><template #body><img v-if="imageUrl" :src="previewImageUrl" :alt="watermarkPreview ? '放大的习题图片，含水印预览' : '放大的习题图片'" class="w-full" /></template><template #footer><UButton label="下载图片" icon="i-lucide-download" :loading="singleBusy" :disabled="!imageUrl || !current() || exportBusy || !!watermarkIssue" @click="download" /></template></UModal>
  </section>
</template>

<style src="../styles/image-workbench.css"></style>
