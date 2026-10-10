<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useExamStore } from '../stores/exam'
import { useAuthStore } from '../stores/auth'
import { captureWorkspaceGuard, fetchScope } from '../api'
import { TYPE_GROUPS_BY_GRADE, TYPE_GROUPS_DEFAULT, TYPE_NAME } from '../constants'
import { gradeNumOf } from '../utils'
import type { Difficulty, ScopeData } from '../types'
import { textbookGroups } from '../knowledge-points'
import { fetchImageOptions, imageWorksheetTitle, plannedImageQuestionCount, previewImagePrompt, type ImageWorksheetParams, type WorksheetImage } from '../image-generation'
import { MAX_WORKSHEET_IMAGES, useImageBatch } from '../image-batch'
import { publicationUrl, type ImagePublication } from '../image-publication'

const store = useExamStore()
const auth = useAuthStore()
const ImagePublicationDialog = defineAsyncComponent(() => import('./ImagePublicationDialog.vue'))
const publicationOpen = ref(false)
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
const pdfBusy = ref(false), pdfProgress = ref('')
const prompt = ref(''), promptOpen = ref(false), promptBusy = ref(false)
const zoomOpen = ref(false)
const mobilePanel = ref<'settings' | 'preview'>('settings')
const followLatest = ref(true), historyOpen = ref(false), draftLoaded = ref(false)
const draftStatus = ref('')
const draftKey = storageKey + '_draft', publishedKey = storageKey + '_published'
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
})
const busy = computed(() => batch.state.busy), checking = computed(() => batch.state.checking)
const result = computed(() => batch.state.pages[selectedPage.value]?.image)
const completedKey = computed(() => batch.state.pages.filter(page => page.image).map(page => page.id).join(','))
const savedDraft = computed(() => publishedDrafts.value[completedKey.value])
const imageUrl = computed(() => batch.state.pages[selectedPage.value]?.url || '')
const batchParams = computed(() => {
  const value = batch.parameters()
  return validDraft(value) ? value : null
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
  if (busy.value) return batch.state.paused ? '本张完成后暂停' : `正在生成第 ${Math.max(0, batch.state.pages.findIndex(page => page.state === 'running')) + 1} / ${batch.state.pages.length} 张`
  if (batch.unresolved) return '生成结果待确认'
  if (!batch.remaining) return '本批图片已全部完成'
  if (retrying.value) return '部分图片未完成'
  if (batch.state.paused) return '本批次已暂停'
  return '还有图片等待生成'
})
const statusHint = computed(() => checking.value ? '正在找回已有图片，不会发起新的生成。'
  : busy.value ? batch.state.paused ? '正在生成的这一张会保留，后续图片等你继续。' : '图片逐张完成，生成期间可查看和下载已完成的图片。'
  : batch.unresolved ? '先查询本次结果，确认后再继续，避免重复生成。'
  : !batch.remaining ? '可下载单张图片，或合并为 PDF 打印。'
  : !batchParams.value ? '原批次设置无法读取，请重新设置并新建批次，已完成的图片仍可下载。'
  : retrying.value ? '继续生成会重试未完成的图片，可能产生新的费用；已完成的图片会保留。'
  : '点击继续即可完成剩余图片，已完成的图片会保留。')
const retrying = computed(() => batch.state.pages.some(page => page.state === 'failed' || page.state === 'expired'))
const pageLabels = { queued: '待生成', running: '生成中', unknown: '待查询', failed: '未完成', ready: '已完成', expired: '已过期' }
const subjects = computed(() => store.available[grade.value] || [])
const types = computed(() => (TYPE_GROUPS_BY_GRADE[subject.value]?.[gradeNumOf(grade.value)] || TYPE_GROUPS_DEFAULT).flatMap(group => group[1]))
const minimumTotal = computed(() => selected.value.reduce((sum, type) => sum + (counts.value[type] ?? 1), 0))
const issue = computed(() => !grade.value || !subject.value ? '请先选择年级和科目' : selected.value.length > 5 ? '每张图片最多选择 5 种题型' : minimumTotal.value > 24 ? '每张图片最多安排 24 道题，请减少题量' : '')
const disabled = computed(() => busy.value || checking.value || batch.unresolved || pdfBusy.value || publicationOpen.value || !current())
const hasSettings = computed(() => !!(grade.value || subject.value || keyword.value || selected.value.length ||
  requirements.value || difficulty.value !== 'medium' || imageCount.value !== 1))
const params = computed<ImageWorksheetParams>(() => ({ grade: grade.value, subject: subject.value, keyword: keyword.value.trim(), difficulty: difficulty.value,
  items: selected.value.map(game_type => ({ game_type, question_count: counts.value[game_type] ?? null })), style: style.value, requirements: requirements.value.trim(), image_count: imageCount.value, image_index: 1 }))
const plannedCount = computed(() => plannedImageQuestionCount(params.value.items))
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
  if (!batch.canContinue || !batchParams.value || !configured.value || pdfBusy.value || publicationOpen.value || !current()) return
  error.value = ''; showResults(); followLatest.value = true
  selectedPage.value = Math.max(0, batch.state.pages.findIndex(page => page.state !== 'ready'))
  await batch.run()
}
async function recoverBatch() {
  if (busy.value || checking.value || pdfBusy.value || publicationOpen.value || !current()) return
  error.value = ''; showResults()
  await batch.recover()
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
watch(params, () => {
  prompt.value = ''; promptVersion++
  if (!draftLoaded.value || !current()) return
  try { localStorage.setItem(draftKey, JSON.stringify(params.value)); draftStatus.value = '配置已保存到本机' }
  catch { draftStatus.value = '配置未能保存，请勿刷新页面' }
}, { flush: 'sync' })
function applyParams(saved: ImageWorksheetParams) {
  grade.value = saved.grade; subject.value = saved.subject; keyword.value = saved.keyword
  difficulty.value = saved.difficulty; style.value = saved.style; requirements.value = saved.requirements
  selected.value = saved.items.map(item => item.game_type)
  counts.value = Object.fromEntries(saved.items.map(item => [item.game_type, item.question_count ?? null]))
  imageCount.value = saved.image_count || 1
}
function validDraft(value: unknown): value is ImageWorksheetParams {
  const v = value as ImageWorksheetParams | null
  return !!v && typeof v.grade === 'string' && typeof v.subject === 'string' && typeof v.keyword === 'string' && v.keyword.length <= 100
    && typeof v.requirements === 'string' && ['easy', 'medium', 'hard'].includes(v.difficulty) && ['playful', 'clean', 'black_white'].includes(v.style)
    && Array.isArray(v.items) && v.items.length <= 5 && v.items.every(item => item && typeof item.game_type === 'string' && !!TYPE_NAME[item.game_type] && (item.question_count == null || Number.isInteger(item.question_count) && item.question_count >= 1 && item.question_count <= 20))
    && (v.image_count === undefined || Number.isInteger(v.image_count) && v.image_count >= 1 && v.image_count <= MAX_WORKSHEET_IMAGES)
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
  try { const value = await fetchImageOptions(); ownerGuard(); if (current()) { configured.value = value.configured; ready.value = true } }
  catch (e) { if (current()) configError.value = e instanceof Error ? e.message : '生图服务状态加载失败' }
}
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
function downloadFile(url: string, name: string) {
  const link = document.createElement('a')
  link.href = url; link.download = name
  document.body.append(link); link.click(); link.remove()
}
function download() {
  if (!imageUrl.value || !result.value || !current()) return
  downloadFile(imageUrl.value, `习题图片-${result.value.request_id.slice(0, 8)}-第${selectedPage.value + 1}张.png`)
}
async function downloadPdf() {
  if (!current() || pdfBusy.value || busy.value || checking.value || !batch.completed) return
  const images = batch.state.pages.flatMap(page => page.image ? [page.image] : [])
  pdfBusy.value = true; error.value = ''; pdfProgress.value = `正在合并 0 / ${images.length} 页`
  try {
    const { buildWorksheetPdf } = await import('../worksheet-pdf')
    const blob = await buildWorksheetPdf(images, done => { if (current()) pdfProgress.value = `正在合并 ${done} / ${images.length} 页` }, () => !current())
    ownerGuard()
    if (!current()) return
    const url = URL.createObjectURL(blob)
    downloadFile(url, `习题图片-${images[0].request_id.slice(0, 8)}-${images.length}页.pdf`)
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (cause) { if (current()) error.value = cause instanceof Error ? cause.message : 'PDF 导出失败，图片已保留' }
  finally { pdfBusy.value = false; pdfProgress.value = '' }
}
function openPublication() {
  if (disabled.value || auth.user?.role !== 'admin' || !batch.completed) return
  if (publication.value?.key !== completedKey.value) {
    publication.value = { key: completedKey.value,
      images: batch.state.pages.flatMap(page => page.image ? [page.image] : []),
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
  let draft: unknown
  try { draft = JSON.parse(localStorage.getItem(draftKey) || 'null') } catch { /* Ignore malformed draft. */ }
  if (validDraft(draft)) { applyParams(draft); draftStatus.value = '已恢复本机配置' }
  else {
    try {
      const previous = JSON.parse(localStorage.getItem(storageKey) || 'null')
      if (validDraft(previous?.input)) applyParams({ ...previous.input, image_count: previous.pages?.length || 1 })
    } catch { /* Keep the current defaults. */ }
  }
  draftLoaded.value = true
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
        <UButton label="历史批次" icon="i-lucide-history" color="neutral" variant="ghost" :disabled="disabled || !batch.history.length" @click="historyOpen = true" />
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
          <div class="image-batch-actions">
            <UButton v-if="busy && batch.remaining > 1" :label="batch.state.paused ? '等待本张完成' : '暂停后续生成'" icon="i-lucide-pause" color="neutral" variant="outline" :disabled="batch.state.paused" @click="batch.pause" />
            <UButton v-if="!busy && (checking || batch.unresolved)" label="查询本次结果" icon="i-lucide-refresh-cw" :loading="checking" :disabled="checking || pdfBusy || publicationOpen || !current()" @click="recoverBatch" />
            <UButton v-else-if="batch.canContinue" :label="`继续生成剩余 ${batch.remaining} 张`" icon="i-lucide-play" :disabled="!batchParams || !configured || pdfBusy || publicationOpen || !current()" @click="continueBatch" />
            <UButton v-if="batch.completed" :label="`下载 PDF（${batch.completed} 页）`" icon="i-lucide-file-down" :color="batch.remaining ? 'neutral' : 'primary'" :variant="batch.remaining ? 'outline' : 'solid'" :loading="pdfBusy" :disabled="busy || checking || pdfBusy || publicationOpen || !current()" @click="downloadPdf" />
            <UButton v-if="!busy && !checking && !batch.remaining" label="调整设置，再出一组" color="neutral" variant="outline" @click="editSettings" />
          </div>
          <p v-if="pdfProgress" role="status" class="image-field-hint">{{ pdfProgress }}</p>
        </div>

        <template v-if="batch.state.pages.length">
          <div v-if="batch.state.pages.length > 1" class="image-pages" aria-label="图片列表">
            <button v-for="(page, index) in batch.state.pages" :key="page.id" type="button" :aria-label="`第 ${index + 1} 张 · ${pageLabels[page.state]}`" :aria-pressed="selectedPage === index" :class="{ selected: selectedPage === index }" @click="choosePage(index)">
              <img v-if="page.url" :src="page.url" alt="" /><UIcon v-else :name="page.state === 'running' ? 'i-lucide-loader-circle' : page.state === 'failed' || page.state === 'unknown' ? 'i-lucide-circle-alert' : 'i-lucide-image'" class="size-5" :class="{ 'animate-spin': page.state === 'running' }" />
              <span>第 {{ index + 1 }} 张<small>{{ pageLabels[page.state] }}</small></span>
            </button>
          </div>
          <div class="image-result-tools">
            <div class="image-page-navigation"><UButton icon="i-lucide-chevron-left" aria-label="上一张图片" color="neutral" variant="ghost" :disabled="selectedPage === 0" @click="choosePage(selectedPage - 1)" /><span>{{ selectedPage + 1 }} / {{ batch.state.pages.length }}</span><UButton icon="i-lucide-chevron-right" aria-label="下一张图片" color="neutral" variant="ghost" :disabled="selectedPage >= batch.state.pages.length - 1" @click="choosePage(selectedPage + 1)" /></div>
            <div class="image-result-actions"><UButton label="放大" icon="i-lucide-maximize" color="neutral" variant="ghost" :disabled="!imageUrl" @click="zoomOpen = true" /><UButton label="下载本张" icon="i-lucide-image-down" color="neutral" variant="outline" :disabled="!imageUrl || !current()" @click="download" /></div>
          </div>
          <UButton v-if="busy && !followLatest" label="跟随最新图片" color="neutral" variant="ghost" @click="followLatest = true; selectedPage = Math.max(0, batch.state.pages.map(page => !!page.image).lastIndexOf(true))" />
          <template v-if="imageUrl">
            <button class="image-zoom-target" type="button" aria-label="放大查看本张图片" @click="zoomOpen = true"><img :src="imageUrl" :alt="`AI 生成的习题图片，第 ${selectedPage + 1} 张`" class="worksheet-image" /></button>
            <div class="image-result-caption"><span>{{ result?.width }} × {{ result?.height }} · PNG</span><span>使用前请核对文字、题目与答案准确性</span></div>
            <details class="image-result-prompt"><summary>查看本张生成说明</summary><pre>{{ result?.prompt }}</pre></details>
          </template>
          <div v-else class="image-empty">
            <UIcon :name="checking || batch.state.pages[selectedPage]?.state === 'running' ? 'i-lucide-loader-circle' : 'i-lucide-image'" class="size-9" :class="{ 'animate-spin': checking || batch.state.pages[selectedPage]?.state === 'running' }" />
            <h3>第 {{ selectedPage + 1 }} 张 · {{ checking ? '正在查询' : pageLabels[batch.state.pages[selectedPage]?.state || 'queued'] }}</h3>
            <p>{{ batch.state.pages[selectedPage]?.state === 'queued' ? '按顺序生成，完成后会显示在这里。' : batch.state.pages[selectedPage]?.state === 'running' ? '图片正在生成，请稍候。' : '在上方确认生成状态后，即可继续。' }}</p>
            <p v-if="batch.state.pages[selectedPage]?.error" role="alert" class="image-batch-error">{{ batch.state.pages[selectedPage]?.error }}</p>
          </div>
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
    <UModal v-model:open="promptOpen" title="生成说明" description="根据当前设置整理的出题要求，可关闭后继续调整。" :ui="{ content: 'max-w-2xl' }"><template #body><pre class="image-prompt-text">{{ prompt }}</pre></template></UModal>
    <UModal v-model:open="zoomOpen" :title="`习题图片 · 第 ${selectedPage + 1} 张`" :ui="{ content: 'max-w-5xl' }"><template #body><img v-if="imageUrl" :src="imageUrl" alt="放大的习题图片" class="w-full" /></template><template #footer><UButton label="下载图片" icon="i-lucide-download" @click="download" /></template></UModal>
  </section>
</template>

<style scoped>
.image-workbench { height:100%;min-height:0;display:grid;grid-template-columns:minmax(330px,380px) minmax(0,1fr);grid-template-rows:minmax(0,1fr); }
.image-workbench:has(.image-notices) { grid-template-rows:auto minmax(0,1fr); }
.image-notices { grid-column:1/-1;display:grid;gap:8px;padding:10px 20px;max-height:25vh;overflow:auto;overflow-wrap:anywhere;border-bottom:1px solid var(--ui-border); }
.image-controls { min-height:0;display:flex;flex-direction:column;background:var(--ui-bg);border-right:1px solid var(--ui-border); }
.image-panel-heading,.image-preview-heading { display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 20px;border-bottom:1px solid var(--ui-border);flex-shrink:0; }
.image-panel-heading h2,.image-preview-heading h2 { font-size:14px;font-weight:650; }
.image-panel-heading p,.image-preview-heading p { margin-top:4px;font-size:11px;color:var(--ui-text-muted); }
.image-service { font-size:10px;color:var(--ui-text-muted);white-space:nowrap; }.image-service.online { color:var(--ui-primary); }
.image-service.online::before { content:'';display:inline-block;width:5px;height:5px;border-radius:50%;background:currentColor;margin-right:5px; }
.image-form { flex:1;min-height:0;display:flex;flex-direction:column; }
.image-fields { flex:1;min-width:0;min-height:0;overflow:auto;scrollbar-width:thin;border:0;padding:0;margin:0; }
.image-setting-section { display:flex;flex-direction:column;gap:16px;padding:18px 20px;border-bottom:1px solid var(--ui-border); }
.image-section-title { display:flex;align-items:center;gap:8px; }.image-section-title>span { display:grid;place-items:center;width:22px;height:22px;border-radius:7px;background:color-mix(in srgb,var(--ui-primary) 9%,var(--ui-bg));color:var(--ui-primary);font-size:11px;font-weight:700; }
.image-section-title h3 { font-size:13px;font-weight:650; }.image-section-title>small { margin-left:auto;color:var(--ui-text-muted);font-size:11px; }
.image-label { display:block;margin-bottom:7px;font-size:12px;font-weight:600; }.image-label small { font-size:10px;font-weight:400;color:var(--ui-text-muted);margin-left:4px; }
.image-select-row { display:grid;grid-template-columns:1fr 1fr;gap:12px; }.image-select-row>div { min-width:0; }
.image-select-field { display:flex;flex-direction:column;gap:7px;font-size:12px;font-weight:600;min-width:0; }
.image-select-field select { min-width:0;width:100%;height:36px;padding:0 10px;border:1px solid var(--ui-border);border-radius:6px;background:var(--ui-bg);color:var(--ui-text);font-size:12px;font-weight:400; }
.image-field-hint { display:flex;justify-content:space-between;gap:8px;font-size:11px;line-height:1.6;color:var(--ui-text-muted);margin-top:6px; }
.image-field-hint>span:last-child { flex-shrink:0; }
button { transition:background .15s,border-color .15s; }button:disabled,fieldset:disabled button { cursor:default;opacity:.55; }
button:focus-visible,select:focus-visible,summary:focus-visible { outline:2px solid var(--ui-primary);outline-offset:3px; }
.image-suggestions,.image-knowledge-list { display:flex;flex-wrap:wrap;gap:6px;margin-top:10px; }.image-knowledge-list { max-height:200px;overflow:auto; }
.image-suggestions button,.image-knowledge-list button { border:1px solid var(--ui-border);border-radius:6px;padding:5px 8px;font-size:11px;line-height:1.5;text-align:left;overflow-wrap:anywhere;background:var(--ui-bg);color:var(--ui-text-toned);cursor:pointer; }
summary { cursor:pointer;font-size:12px;color:var(--ui-text-toned);line-height:1.6; }
.image-knowledge { margin-top:10px; }.image-knowledge summary { font-size:11px;color:var(--ui-primary); }
.image-arrangements { display:grid;grid-template-columns:1fr 1fr;gap:8px; }
.image-arrangements button { border:1px solid var(--ui-border);border-radius:10px;padding:12px 10px;text-align:left;background:var(--ui-bg);cursor:pointer; }
.image-arrangements strong { display:flex;align-items:center;justify-content:space-between;gap:4px;font-size:12px;font-weight:600; }.image-arrangements b { font-size:12px;font-weight:600;white-space:nowrap; }
.image-arrangements small { display:block;margin-top:5px;font-size:10px;color:var(--ui-text-muted);font-weight:400; }
.image-custom,.image-advanced { border:1px solid var(--ui-border);border-radius:8px;padding:10px 12px; }
.image-custom summary>small { display:block;margin:4px 0 0 14px;font-size:11px;color:var(--ui-text-muted);font-weight:400;overflow-wrap:anywhere; }
.image-optional { margin-left:4px;font-size:10px;color:var(--ui-text-muted);font-weight:400; }
.image-custom-body { display:flex;flex-direction:column;gap:12px;margin-top:14px; }
.image-advanced summary small { float:right;font-size:10px;color:var(--ui-text-muted); }
.image-type-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px; }
.image-type-grid button { display:flex;align-items:center;gap:6px;min-height:36px;padding:7px 8px;border:1px solid var(--ui-border);border-radius:7px;background:var(--ui-bg);font-size:12px;cursor:pointer; }
.image-counts { display:flex;flex-direction:column;gap:10px;background:var(--ui-bg-muted);padding:10px;border-radius:8px; }
.image-count-row { display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px;font-size:12px;color:var(--ui-text-toned); }
.image-count-row>span { overflow-wrap:anywhere; }.image-count-value { grid-column:1/-1;width:100%; }.image-count-auto { grid-column:1/-1;color:var(--ui-text-muted);font-size:11px; }
.image-style-grid { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px; }
.image-style-grid button { display:flex;flex-direction:column;align-items:center;gap:7px;padding:6px 6px 9px;border:1px solid var(--ui-border);border-radius:8px;background:var(--ui-bg);cursor:pointer; }
.image-style-grid strong { font-size:11px;font-weight:500; }
.image-style-sample { display:flex;flex-direction:column;align-items:flex-start;gap:5px;width:100%;height:57px;border-radius:4px;padding:7px 10px;background:#fff6e8;color:#c59243; }
.image-style-sample i { width:100%;height:2px;background:currentColor;opacity:.25;border-radius:2px; }.image-style-sample i:last-child { width:60%; }.image-style-sample[data-style=clean] { background:#edf5f2;color:#4c8678; }.image-style-sample[data-style=black_white] { background:#f1f1f1;color:#555; }
button.selected { border-color:var(--ui-primary);background:color-mix(in srgb,var(--ui-primary) 7%,var(--ui-bg));color:var(--ui-primary); }
.image-arrangements button:not(:disabled):hover,.image-style-grid button:not(:disabled):hover,.image-type-grid button:not(:disabled):hover,.image-suggestions button:not(:disabled):hover { border-color:var(--ui-primary); }
.image-generate-actions { flex-shrink:0;display:flex;flex-direction:column;gap:9px;padding:12px 20px;border-top:1px solid var(--ui-border);background:var(--ui-bg);box-shadow:0 -6px 20px #163b3505; }
.image-generate-row { display:grid;grid-template-columns:112px minmax(0,1fr);align-items:end;gap:10px; }
.image-generate-count { min-width:0; }.image-generate-count .image-label { margin-bottom:6px; }.image-generate-count :deep(input) { min-width:0; }
.image-generate-button { min-height:40px;white-space:normal; }
.image-generate-actions .image-field-hint { margin-top:0; }.image-action-row { display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap; }.image-order-summary { font-size:12px;font-weight:600;color:var(--ui-text-toned); }.image-draft-status { color:var(--ui-text-muted);font-size:10px; }
.image-preview-panel { min-width:0;min-height:0;display:flex;flex-direction:column;background:var(--ui-bg-muted); }.image-preview-heading { background:var(--ui-bg);padding:16px 24px; }
.image-preview-scroll { flex:1;min-height:0;overflow:auto;padding:24px;scrollbar-width:thin;background-image:radial-gradient(color-mix(in srgb,var(--ui-text-muted) 14%,transparent) .8px,transparent .8px);background-size:20px 20px; }
.image-batch-card { max-width:960px;margin:0 auto 20px;padding:18px 20px;border:1px solid var(--ui-border);border-radius:12px;background:var(--ui-bg); }
.image-batch-title { display:flex;align-items:flex-start;justify-content:space-between;gap:12px; }.image-batch-title>div { min-width:0; }.image-batch-title h3 { font-size:16px;line-height:1.5;font-weight:650;overflow-wrap:anywhere; }.image-batch-title p { margin-top:5px;font-size:11px;line-height:1.6;color:var(--ui-text-muted); }.image-batch-title>button { flex-shrink:0; }
.image-batch-status { margin-top:18px; }.image-batch-status>div { display:flex;align-items:center;gap:7px;flex-wrap:wrap;font-size:12px;color:var(--ui-primary); }.image-batch-status strong { font-weight:600; }.image-batch-status span:last-child { margin-left:auto;color:var(--ui-text-muted);font-size:11px; }
.image-batch-status progress { display:block;margin:10px 0;width:100%;height:4px;accent-color:var(--ui-primary);border:0;border-radius:8px;overflow:hidden; }.image-batch-status progress::-webkit-progress-bar { background:var(--ui-border); }.image-batch-status progress::-webkit-progress-value { background:var(--ui-primary);transition:width .3s; }.image-batch-status p { color:var(--ui-text-muted);font-size:12px;line-height:1.7; }
.image-batch-error { color:var(--ui-error);font-size:12px;line-height:1.7;margin-top:8px;overflow-wrap:anywhere; }
.image-batch-actions { display:flex;flex-wrap:wrap;gap:8px;margin-top:14px; }.image-batch-actions:empty { display:none; }
.image-pages { display:flex;gap:8px;overflow-x:auto;padding:2px 2px 12px;max-width:960px;margin:0 auto; }
.image-pages button { display:flex;align-items:center;justify-content:center;gap:9px;flex:0 0 112px;min-height:62px;padding:8px;border:1px solid var(--ui-border);border-radius:8px;background:var(--ui-bg);font-size:12px;cursor:pointer; }.image-pages button.selected { border-color:var(--ui-primary);background:color-mix(in srgb,var(--ui-primary) 7%,var(--ui-bg)); }
.image-pages img { width:32px;height:42px;object-fit:contain; }.image-pages small { display:block;font-size:10px;color:var(--ui-text-muted);margin-top:4px; }
.image-result-tools { display:flex;justify-content:space-between;align-items:center;gap:8px;margin:0 auto 14px;max-width:960px; }.image-page-navigation,.image-result-actions { display:flex;align-items:center;gap:4px; }.image-page-navigation>span { font-size:12px;color:var(--ui-text-muted);white-space:nowrap; }
.image-zoom-target { display:block;width:fit-content;max-width:100%;margin:0 auto;cursor:zoom-in;border-radius:4px; }
.worksheet-image { display:block;max-width:100%;max-height:900px;width:auto;margin:0 auto;object-fit:contain;background:white;box-shadow:0 6px 30px #173b3910;border-radius:4px; }
.image-result-caption { display:flex;justify-content:center;gap:8px 20px;flex-wrap:wrap;margin:16px auto;font-size:11px;color:var(--ui-text-muted); }
.image-result-prompt { max-width:960px;margin:0 auto;font-size:12px;padding:12px 16px;border:1px solid var(--ui-border);border-radius:8px;background:var(--ui-bg); }
.image-result-prompt pre,.image-prompt-text { white-space:pre-wrap;overflow-wrap:anywhere;font-family:inherit;font-size:13px;line-height:1.85; }.image-result-prompt pre { margin-top:12px; }
.image-admin-actions { display:flex;justify-content:flex-end;max-width:960px;margin:12px auto 0; }
.image-empty { display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:260px;text-align:center;color:var(--ui-primary);padding:30px 20px; }
.image-empty h3 { font-size:17px;font-weight:600;color:var(--ui-text-highlighted);margin-top:20px; }.image-empty p { margin-top:10px;font-size:12px;line-height:1.8;color:var(--ui-text-muted); }
.image-design-preview { display:flex;flex-direction:column;align-items:center;max-width:720px;margin:4px auto 20px; }.image-preview-intro { text-align:center;margin-bottom:24px; }
.image-eyebrow { display:inline-flex;align-items:center;gap:7px;color:var(--ui-primary);font-size:11px; }.image-preview-intro h3 { margin-top:10px;font-size:clamp(20px,2vw,25px);font-weight:650;color:var(--ui-text-highlighted); }.image-preview-intro p { margin-top:8px;font-size:12px;line-height:1.8;color:var(--ui-text-muted); }
.image-paper { --paper-accent:#af7e3b;--paper-wash:#fcf5e9;width:100%;max-width:440px;min-height:410px;background:#fff;color:#343b39;border:1px solid #e6e6df;border-radius:5px;padding:30px 32px 20px;box-shadow:0 16px 45px #25463a12,0 3px 8px #25463a08;position:relative;overflow:hidden; }
.image-paper::before { content:'';position:absolute;top:0;left:0;right:0;height:6px;background:var(--paper-accent);opacity:.65; }.image-paper[data-style=clean] { --paper-accent:#4c8678;--paper-wash:#edf5f2; }.image-paper[data-style=black_white] { --paper-accent:#555;--paper-wash:#f3f3f3; }
.image-paper-top { display:flex;align-items:center;justify-content:space-between;font-size:11px;color:var(--paper-accent); }.image-paper h4 { font-size:23px;line-height:1.5;font-weight:700;margin-top:18px;overflow-wrap:anywhere; }.image-paper-meta { color:#959c98;font-size:10px;margin-top:12px; }.image-paper-rule { height:1px;background:#e9ece8;margin:20px 0; }
.image-paper-placeholder { text-align:center;color:var(--paper-accent);background:var(--paper-wash);padding:35px 10px;border-radius:10px; }.image-paper-placeholder p { font-size:13px;margin-top:12px; }.image-paper-placeholder span { display:block;font-size:10px;margin-top:8px;opacity:.75; }
.image-paper-exercise { margin-bottom:18px; }.image-paper-exercise>div:first-child { display:flex;align-items:center;gap:8px;font-size:12px; }.image-paper-exercise span { font-size:10px;color:var(--paper-accent);padding:3px 6px;border-radius:4px;background:var(--paper-wash); }.image-paper-exercise small { margin-left:auto;color:#959c98;font-size:10px; }.image-paper-lines { display:flex;gap:16px;margin:18px 0 10px; }.image-paper-lines i { height:1px;background:#e5e9e5;flex:1; }.image-paper-bottom { display:flex;justify-content:space-between;font-size:10px;color:#959c98;margin-top:30px; }
.image-preview-disclaimer { display:flex;align-items:center;gap:5px;text-align:center;color:var(--ui-text-muted);font-size:11px;margin-top:17px; }
.image-history-list { display:flex;flex-direction:column;gap:8px; }.image-history-list button { display:grid;grid-template-columns:1fr auto;gap:6px;text-align:left;padding:14px;border:1px solid var(--ui-border);border-radius:8px;background:var(--ui-bg); }.image-history-list strong { font-size:13px;overflow-wrap:anywhere; }.image-history-list span { grid-row:2;font-size:11px;color:var(--ui-text-muted); }
.image-mobile-tabs,.image-mobile-result-footer,.image-back-settings { display:none; }
@media (min-width:768px) and (max-width:1100px) { .image-workbench { grid-template-columns:330px minmax(0,1fr); }.image-preview-scroll { padding:18px 14px; }.image-batch-card { padding:16px; }.image-batch-status span:last-child { margin-left:0; }.image-result-tools { flex-wrap:wrap; } }
@media(max-width:767px) {
  .image-workbench { display:flex;flex-direction:column;overflow:hidden; }
  .image-mobile-tabs { display:flex;flex-shrink:0;gap:6px;padding:8px 16px;background:var(--ui-bg);border-bottom:1px solid var(--ui-border); }
  .image-mobile-tabs button { display:flex;justify-content:center;align-items:center;gap:6px;flex:1;padding:9px;border-radius:8px;font-size:13px;color:var(--ui-text-muted); }
  .image-mobile-tabs button[aria-pressed=true] { color:var(--ui-primary);background:color-mix(in srgb,var(--ui-primary) 8%,var(--ui-bg));font-weight:600; }
  .image-mobile-tabs button>span { font-size:10px;padding:1px 5px;border-radius:5px;background:var(--ui-bg); }
  .image-notices { flex-shrink:0;padding:8px 16px; }.image-controls { flex:1;min-height:0;border-right:0; }
  .image-panel-heading { padding:12px 16px; }.image-panel-heading p { display:none; }.image-setting-section { padding:16px;gap:14px; }.image-generate-actions { padding:10px 16px max(10px,env(safe-area-inset-bottom)); }
  .image-preview-panel { flex:1;min-height:0; }.image-preview-heading { padding:12px 16px; }.image-preview-heading p { display:none; }.image-preview-scroll { padding:16px 12px; }
  .image-workbench[data-mobile-panel=preview] .image-controls,.image-workbench[data-mobile-panel=settings] .image-preview-panel { display:none; }
  .image-batch-card { padding:14px;margin-bottom:14px; }.image-batch-title h3 { font-size:15px; }.image-batch-status { margin-top:14px; }.image-batch-status>div { gap:6px; }.image-batch-status span:last-child { margin-left:0; }
  .image-batch-actions>* { flex-grow:1;justify-content:center; }.image-batch-actions { gap:8px; }.image-result-tools { gap:4px; }.image-page-navigation { gap:0; }.image-result-actions { gap:2px; }
  .image-paper { padding:24px;min-height:340px; }.image-preview-intro h3 { font-size:20px; }.image-preview-disclaimer { font-size:10px; }.image-empty { min-height:200px; }
  .image-mobile-result-footer { display:block;flex-shrink:0;background:var(--ui-bg);border-top:1px solid var(--ui-border);padding:6px 16px max(6px,env(safe-area-inset-bottom)); }.image-back-settings { display:inline-flex;margin-top:20px; }
}
@media(prefers-reduced-motion:reduce) { button,.image-batch-status progress::-webkit-progress-value { transition:none; }.animate-spin { animation:none; } }
</style>
