<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useExamStore } from '../stores/exam'
import { useAuthStore } from '../stores/auth'
import { captureWorkspaceGuard, fetchScope } from '../api'
import { TYPE_GROUPS_BY_GRADE, TYPE_GROUPS_DEFAULT, TYPE_NAME } from '../constants'
import { gradeNumOf } from '../utils'
import type { Difficulty, ScopeData } from '../types'
import { fetchImageOptions, previewImagePrompt, type ImageWorksheetParams, type WorksheetImage } from '../image-generation'
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
const difficulty = ref<Difficulty>(store.difficulty)
const selected = ref<string[]>([]), counts = ref<Record<string, number>>({})
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
const knowledgePoints = computed(() => (scope.value?.allowed || []).filter(point => point.includes(knowledgeSearch.value.trim())))
const chosenKnowledge = computed(() => keyword.value.split('、').map(point => point.trim()).filter(Boolean))
const activeStyle = computed(() => styles.find(item => item.value === style.value)!)
const progress = computed(() => batch.state.pages.length ? Math.round(batch.completed / batch.state.pages.length * 100) : 0)
const difficulties = [{ value: 'easy' as const, label: '基础', description: '巩固知识' }, { value: 'medium' as const, label: '标准', description: '日常练习' }, { value: 'hard' as const, label: '提升', description: '进阶挑战' }]
const previewPanel = ref<HTMLElement | null>(null)
let alive = true, scopeVersion = 0, promptVersion = 0
const ownerGuard = captureWorkspaceGuard()
const current = () => alive && store.ownerId === owner && !store.accountChanged
const batch = useImageBatch(storageKey, current, index => {
  if (followLatest.value) selectedPage.value = index
  void nextTick(() => {
    if (current() && followLatest.value && batch.completed === 1 && window.matchMedia('(max-width: 767px)').matches) previewPanel.value?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  })
})
const busy = computed(() => batch.state.busy), checking = computed(() => batch.state.checking)
const result = computed(() => batch.state.pages[selectedPage.value]?.image)
const completedKey = computed(() => batch.state.pages.filter(page => page.image).map(page => page.id).join(','))
const savedDraft = computed(() => publishedDrafts.value[completedKey.value])
const imageUrl = computed(() => batch.state.pages[selectedPage.value]?.url || '')
const status = computed(() => busy.value ? `正在生成第 ${batch.state.pages.findIndex(page => page.state === 'running') + 1} / ${batch.state.pages.length} 张` : batch.state.pages.length ? `已完成 ${batch.completed} / ${batch.state.pages.length} 张` : '')
const retrying = computed(() => batch.state.pages.some(page => page.state === 'failed' || page.state === 'expired'))
const pageLabels = { queued: '待生成', running: '生成中', unknown: '待查询', failed: '未完成', ready: '已完成', expired: '已过期' }
const subjects = computed(() => store.available[grade.value] || [])
const types = computed(() => (TYPE_GROUPS_BY_GRADE[subject.value]?.[gradeNumOf(grade.value)] || TYPE_GROUPS_DEFAULT).flatMap(group => group[1]))
const total = computed(() => selected.value.reduce((sum, type) => sum + (counts.value[type] || 4), 0))
const issue = computed(() => !grade.value || !subject.value || !keyword.value.trim() ? '请先选择年级、科目并填写知识点' : !selected.value.length ? '请选择至少一种题型' : selected.value.length > 5 ? '每张图片最多选择 5 种题型' : total.value > 24 ? '每张图片最多安排 24 道题，请减少题量' : '')
const disabled = computed(() => busy.value || checking.value || batch.unresolved || pdfBusy.value || publicationOpen.value || !current())
const params = computed<ImageWorksheetParams>(() => ({ grade: grade.value, subject: subject.value, keyword: keyword.value.trim(), difficulty: difficulty.value,
  items: selected.value.map(game_type => ({ game_type, question_count: counts.value[game_type] || 4 })), style: style.value, requirements: requirements.value.trim(), image_count: imageCount.value, image_index: 1 }))
const styles = [{ value: 'playful' as const, label: '童趣彩色', icon: 'i-lucide-palette' }, { value: 'clean' as const, label: '简洁清爽', icon: 'i-lucide-sparkles' }, { value: 'black_white' as const, label: '黑白打印', icon: 'i-lucide-printer' }]

function chooseGrade(value: string) {
  if (grade.value === value) return
  grade.value = value; subject.value = ''; keyword.value = ''; selected.value = []
}
function chooseSubject(value: string) { if (subject.value === value) return; subject.value = value; keyword.value = ''; selected.value = [] }
function toggleType(type: string) {
  if (selected.value.includes(type)) selected.value = selected.value.filter(item => item !== type)
  else if (selected.value.length < 5 && total.value < 24) { counts.value[type] = Math.min(counts.value[type] || (type === 'reading' ? 1 : 4), 24 - total.value); selected.value.push(type) }
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
  counts.value = Object.fromEntries(saved.items.map(item => [item.game_type, item.question_count]))
  imageCount.value = saved.image_count || 1
}
function validDraft(value: unknown): value is ImageWorksheetParams {
  const v = value as ImageWorksheetParams | null
  return !!v && typeof v.grade === 'string' && typeof v.subject === 'string' && typeof v.keyword === 'string' && v.keyword.length <= 100
    && typeof v.requirements === 'string' && ['easy', 'medium', 'hard'].includes(v.difficulty) && ['playful', 'clean', 'black_white'].includes(v.style)
    && Array.isArray(v.items) && v.items.length <= 5 && v.items.every(item => item && typeof item.game_type === 'string' && !!TYPE_NAME[item.game_type] && Number.isInteger(item.question_count) && item.question_count >= 1 && item.question_count <= 20)
    && (v.image_count === undefined || Number.isInteger(v.image_count) && v.image_count >= 1 && v.image_count <= MAX_WORKSHEET_IMAGES)
}
async function openHistory(id: string) {
  if (disabled.value) return
  followLatest.value = false; selectedPage.value = 0
  await batch.selectHistory(id)
  historyOpen.value = false; mobilePanel.value = 'preview'
}
function choosePage(index: number) { followLatest.value = false; selectedPage.value = index }
function updateCount(type: string, value: number | undefined) {
  counts.value[type] = Math.max(1, Math.min(Math.floor(value || 1), 20, 24 - total.value + (counts.value[type] || 4)))
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
  } catch (e) { if (current()) error.value = e instanceof Error ? e.message : '提示词加载失败' }
  finally { if (current()) promptBusy.value = false }
}
async function generate() {
  if (disabled.value || issue.value || !ready.value || !configured.value) return
  ownerGuard(); error.value = ''; selectedPage.value = 0; followLatest.value = true; mobilePanel.value = 'preview'
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
  void batch.restore()

})
onBeforeUnmount(() => { alive = false; scopeVersion++; promptVersion++; batch.dispose() })
</script>

<template>
  <section class="image-workbench" :data-mobile-panel="mobilePanel" aria-label="图片出题">
    <nav class="image-mobile-tabs" aria-label="工作区切换"><button type="button" :aria-pressed="mobilePanel === 'settings'" @click="mobilePanel = 'settings'">出题设置</button><button type="button" :aria-pressed="mobilePanel === 'preview'" @click="mobilePanel = 'preview'">图片预览 <span v-if="batch.completed">{{ batch.completed }}</span></button></nav>
    <div class="image-controls">
      <div class="image-panel-heading"><div class="image-heading-icon"><UIcon name="i-lucide-wand-sparkles" class="size-5" /></div><div><h2>设计一份习题图</h2><p>选好内容，让练习更有趣</p></div><span class="image-service" :class="{ online: ready && configured }">{{ configError ? '连接异常' : !ready ? '检查中' : configured ? '服务就绪' : '待配置' }}</span></div>
      <form class="image-form" @submit.prevent="generate">
        <fieldset :disabled="disabled" class="image-fields"><section class="image-setting-section"><div class="image-section-title"><span>01</span><h3>学习内容</h3><small>练什么</small></div>
          <div><label class="image-label" id="image-grade-label">年级</label><div v-if="store.availableLoading" role="status">正在加载年级…</div><UAlert v-else-if="store.availableError" :title="store.availableError" color="error" :actions="[{ label: '重试', onClick: () => store.init() }]" /><div v-else class="image-grade-grid" role="group" aria-labelledby="image-grade-label"><button v-for="value in Object.keys(store.available)" :key="value" type="button" :aria-pressed="grade === value" :class="{ selected: grade === value }" @click="chooseGrade(value)">{{ value.replace('小学', '') }}</button></div></div>
          <div><label class="image-label" id="image-subject-label">科目</label><div class="image-choice-row" role="group" aria-labelledby="image-subject-label"><button v-for="value in subjects" :key="value" type="button" :aria-pressed="subject === value" :class="{ selected: subject === value }" @click="chooseSubject(value)">{{ value }}</button><span v-if="!grade" class="text-xs text-muted">选择年级后显示</span></div></div>
          <UFormField label="知识点" required><UTextarea v-model="keyword" aria-label="图片知识点" placeholder="例如：20 以内进位加法" :rows="2" maxlength="100" :disabled="!subject || disabled" class="w-full" /><div class="image-field-hint"><span>多个知识点用「、」分隔</span><span>{{ keyword.length }}/100</span></div><details v-if="subject" class="image-knowledge"><summary>从课程知识点中选择</summary><p v-if="scopeLoading" role="status" class="text-xs text-muted">正在加载…</p><UAlert v-else-if="scopeError" :title="scopeError" color="error" :actions="[{ label: '重试', onClick: loadScope }]" /><div v-else><UInput v-model="knowledgeSearch" aria-label="搜索知识点" placeholder="搜索课程知识点" icon="i-lucide-search" class="w-full mt-3" /><div class="image-knowledge-list"><button v-for="point in knowledgePoints" :key="point" type="button" :aria-pressed="chosenKnowledge.includes(point)" :class="{ selected: chosenKnowledge.includes(point) }" @click="chooseKnowledge(point)">{{ point }}</button><p v-if="!knowledgePoints.length" class="image-field-hint">{{ knowledgeSearch ? '没有匹配项，可直接在上方输入' : '暂无推荐知识点，请在上方输入' }}</p></div></div></details></UFormField>
          </section><section class="image-setting-section"><div class="image-section-title"><span>02</span><h3>练习安排</h3><small>怎么练</small></div><div><label class="image-label" id="image-type-label">题型 <small>已选 {{ selected.length }}/5</small></label><div class="image-type-grid" role="group" aria-labelledby="image-type-label"><button v-for="type in types" :key="type" type="button" :disabled="!subject || ((selected.length >= 5 || total >= 24) && !selected.includes(type))" :aria-pressed="selected.includes(type)" :class="{ selected: selected.includes(type) }" @click="toggleType(type)"><UIcon :name="selected.includes(type) ? 'i-lucide-circle-check' : 'i-lucide-circle-plus'" class="size-3.5" />{{ TYPE_NAME[type] }}</button></div><p class="image-field-hint">最多 5 种题型，每张不超过 24 题 · 还可添加 {{ Math.max(0, 24 - total) }} 题</p><div v-if="selected.length" class="image-counts"><div v-for="type in selected" :key="type" class="image-count-row"><span>{{ TYPE_NAME[type] }}</span><UInputNumber :model-value="counts[type] || 4" :aria-label="TYPE_NAME[type] + '题量'" :min="1" :max="Math.min(20, 24 - total + (counts[type] || 4))" :disabled="disabled" size="sm" class="w-28" @update:model-value="updateCount(type, $event)" /></div></div></div>
          <UFormField label="生成张数"><UInputNumber v-model="imageCount" aria-label="生成张数" :min="1" :max="MAX_WORKSHEET_IMAGES" :disabled="disabled" class="w-full" /></UFormField>
          <div><label id="image-difficulty-label" class="image-label">难度</label><div class="image-difficulty-grid" role="group" aria-labelledby="image-difficulty-label"><button v-for="item in difficulties" :key="item.value" type="button" :aria-pressed="difficulty === item.value" :class="{ selected: difficulty === item.value }" @click="difficulty = item.value"><strong>{{ item.label }}</strong><small>{{ item.description }}</small></button></div></div></section><section class="image-setting-section"><div class="image-section-title"><span>03</span><h3>画面设计</h3><small>什么样</small></div>
          <div><label class="image-label" id="image-style-label">画面风格</label><div class="image-style-grid" role="group" aria-labelledby="image-style-label"><button v-for="item in styles" :key="item.value" type="button" :aria-pressed="style === item.value" :class="{ selected: style === item.value }" @click="style = item.value"><span class="image-style-sample" :data-style="item.value" aria-hidden="true"><UIcon :name="item.icon" class="size-5" /><i></i><i></i><i></i></span><strong>{{ item.label }}</strong></button></div></div>
          <UFormField label="补充要求（选填）"><UTextarea v-model="requirements" :rows="2" maxlength="600" placeholder="例如：用小动物插画，给每题多留一点书写空间" :disabled="disabled" class="w-full" /></UFormField>
        </section></fieldset>
        <div class="image-generate-actions"><p v-if="draftStatus" class="image-draft-status" role="status">{{ draftStatus }}</p><p v-if="batch.storageError" role="alert" class="text-xs text-warning">{{ batch.storageError }}</p>
          <UAlert v-if="configError" :title="configError" color="error" :actions="[{ label: '重新检查', onClick: loadOptions }]" />
          <UAlert v-else-if="ready && !configured" title="生图服务尚未配置" description="请在后台模型配置中设置图片生成接口。" color="warning" :actions="[{ label: '重新检查', onClick: loadOptions }]" />
          <p v-if="error || batch.state.error" role="alert" class="text-sm text-error break-words">{{ error || batch.state.error }}</p>
          <p v-if="status" role="status" class="text-xs text-muted">{{ status }}</p>
          <p v-if="issue && !busy" class="text-xs text-muted">{{ issue }}</p>
          <div class="image-action-row"><UButton type="button" label="预览提示词" variant="ghost" color="neutral" :disabled="!!issue || disabled" :loading="promptBusy" @click="previewPrompt" /><span class="image-order-summary">{{ imageCount }} 张 × {{ total }} 题</span></div>
          <UButton type="submit" :label="busy ? '正在生成图片…' : batch.state.pages.length ? `重新生成 ${imageCount} 张` : `生成 ${imageCount} 张图片`" icon="i-lucide-image-plus" block size="lg" :loading="busy" :disabled="disabled || !!issue || !ready || !configured" />
          <UButton v-if="busy && batch.remaining > 1" type="button" :label="batch.state.paused ? '本张完成后暂停' : '暂停后续生成'" color="neutral" variant="outline" block :disabled="batch.state.paused" @click="batch.pause" />
          <UButton v-if="batch.canContinue" type="button" :label="`继续生成剩余 ${batch.remaining} 张`" color="primary" variant="outline" block :disabled="!configured || pdfBusy || !current()" @click="batch.run" />
          <p v-if="retrying && !busy" class="text-xs text-muted">继续生成会重试未完成的图片，可能产生新的费用；已完成的图片会保留。</p>
          <UButton v-if="batch.state.pages.length && !busy" type="button" label="查询本次结果" icon="i-lucide-refresh-cw" color="neutral" variant="ghost" block :loading="checking" :disabled="checking || pdfBusy || !current()" @click="batch.recover" />
        </div>
      </form>
    </div>
    <div ref="previewPanel" class="image-preview-panel">
      <div class="image-preview-heading"><UButton label="历史批次" icon="i-lucide-history" color="neutral" variant="ghost" :disabled="disabled || !batch.history.length" @click="historyOpen = true" /><div><h2>图片预览</h2><p>每张独立出题，PDF 一张图片一页</p></div><div v-if="batch.completed" class="flex flex-wrap gap-2"><UButton label="放大" icon="i-lucide-maximize" color="neutral" variant="outline" :disabled="!imageUrl" @click="zoomOpen = true" /><UButton label="下载本张" icon="i-lucide-image-down" color="neutral" variant="outline" :disabled="!imageUrl" @click="download" /><UButton :label="`下载 PDF（${batch.completed} 页）`" icon="i-lucide-file-down" :loading="pdfBusy" :disabled="busy || checking || pdfBusy" @click="downloadPdf" /><template v-if="auth.user?.role === 'admin'"><UButton v-if="savedDraft" label="查看后台草稿" icon="i-lucide-arrow-up-right" :href="publicationUrl(savedDraft.id)" target="_blank" color="neutral" variant="outline" /><UButton v-else label="添加到后台" color="neutral" variant="outline" icon="i-lucide-library-big" :disabled="disabled" @click="openPublication" /></template></div></div>
      <div v-if="batch.state.pages.length" class="image-batch-progress" role="status"><div><span>{{ checking ? '正在查询结果' : status }}</span><strong>{{ progress }}%</strong></div><progress :value="batch.completed" :max="batch.state.pages.length" aria-label="图片生成进度" /></div><div class="image-preview-scroll"><UButton v-if="busy && !followLatest" label="跟随最新图片" color="neutral" variant="ghost" @click="followLatest = true; selectedPage = Math.max(0, batch.state.pages.map(page => !!page.image).lastIndexOf(true))" />
        <p v-if="pdfProgress" role="status" class="image-progress">{{ pdfProgress }}</p>
        <div v-if="batch.state.pages.length > 1" class="image-pages" aria-label="图片列表"><button v-for="(page, index) in batch.state.pages" :key="page.id" type="button" :aria-label="`第 ${index + 1} 张 · ${pageLabels[page.state]}`" :aria-pressed="selectedPage === index" :class="{ selected: selectedPage === index }" @click="choosePage(index)"><img v-if="page.url" :src="page.url" alt="" /><UIcon v-else :name="page.state === 'running' ? 'i-lucide-loader-circle' : 'i-lucide-image'" class="size-5" :class="{ 'animate-spin': page.state === 'running' }" /><span>第 {{ index + 1 }} 张</span><small>{{ pageLabels[page.state] }}</small></button></div>
        <p v-if="batch.state.pages[selectedPage]?.error" role="alert" class="text-sm text-error mb-4">第 {{ selectedPage + 1 }} 张：{{ batch.state.pages[selectedPage]?.error }}</p>
        <template v-if="imageUrl"><div v-if="busy" class="image-progress" role="status"><UIcon name="i-lucide-loader-circle" class="size-4 animate-spin" />{{ status }}，已完成的图片可单独下载</div><img :src="imageUrl" :alt="`AI 生成的习题图片，第 ${selectedPage + 1} 张`" class="worksheet-image" /><div class="image-result-caption"><span>{{ result?.width }} × {{ result?.height }} · PNG</span><span>使用前请核对文字、题目与答案准确性</span></div><details class="image-result-prompt"><summary>本张图片的提示词</summary><pre>{{ result?.prompt }}</pre></details></template>
        <div v-else-if="!batch.state.pages.length && !checking" class="image-design-preview">
          <div class="image-preview-intro"><span class="image-eyebrow"><UIcon name="i-lucide-sparkles" class="size-4" /> 从知识点到一页好练习</span><h3>让练习，也有一点想象力</h3><p>内容、题量、风格由你决定，其余交给 AI。</p></div>
          <div class="image-paper" :data-style="style">
            <div class="image-paper-top"><span>{{ grade || '选择年级' }} · {{ subject || '选择科目' }}</span><UIcon :name="activeStyle.icon" class="size-6" /></div>
            <h4>{{ keyword.trim() || '我的专属练习' }}</h4><p class="image-paper-meta">姓名 __________　日期 __________</p><div class="image-paper-rule"></div>
            <div v-if="!selected.length" class="image-paper-placeholder"><UIcon name="i-lucide-list-plus" class="size-6" /><p>选好题型，练习就有了轮廓</p><span>在左侧选择题型，在这里查看配置</span></div>
            <div v-for="(type, index) in selected" :key="type" class="image-paper-exercise"><div><span>{{ String(index + 1).padStart(2, '0') }}</span><strong>{{ TYPE_NAME[type] }}</strong><small>{{ counts[type] || 4 }} 题</small></div><div class="image-paper-lines"><i></i><i></i></div></div>
            <div class="image-paper-bottom"><span>{{ activeStyle.label }}</span><span>{{ total }} 题 / 张 · {{ imageCount }} 张</span></div>
          </div>
          <p class="image-preview-disclaimer"><UIcon name="i-lucide-info" class="size-3.5" /> 配置示意，实际题目与版面将在生成后呈现</p>
          <div class="image-flow"><span><b>1</b> 设定练习</span><UIcon name="i-lucide-chevron-right" class="size-3.5" /><span><b>2</b> 生成图片</span><UIcon name="i-lucide-chevron-right" class="size-3.5" /><span><b>3</b> 下载打印</span></div>
        </div>
        <div v-else class="image-empty"><div class="image-empty-icon"><UIcon :name="busy || checking ? 'i-lucide-loader-circle' : 'i-lucide-image'" class="size-9" :class="{ 'animate-spin': busy || checking }" /></div><h3>{{ busy ? '正在绘制习题图片' : checking ? '正在恢复上次结果' : batch.state.pages.length ? `第 ${selectedPage + 1} 张 · ${pageLabels[batch.state.pages[selectedPage]?.state || 'queued']}` : '把知识点变成习题图' }}</h3><p>{{ busy ? '逐张生成，完成后可下载图片或合并为 PDF。' : batch.state.pages.length ? '已完成的图片会保留，可查询结果或继续生成。' : '选择年级、科目、知识点和题型，设置需要的张数。' }}</p><div v-if="!busy && !checking" class="image-empty-tags"><span>自主设计版面</span><span>完整习题内容</span><span>图片 / PDF 下载</span></div></div>
      </div>
    </div>
    <UModal v-model:open="historyOpen" title="历史批次" description="保留本机最近 10 个历史批次；清理浏览器数据会移除记录，请及时下载重要图片。"><template #body><div class="image-history-list"><button v-for="entry in batch.history" :key="entry.id" type="button" :disabled="disabled" @click="openHistory(entry.id)"><strong>{{ entry.title || '习题图片' }}</strong><span>{{ new Date(entry.savedAt).toLocaleString() }}</span><UIcon name="i-lucide-chevron-right" class="size-4" /></button></div></template></UModal>
    <ImagePublicationDialog v-if="publication" :key="publication.key" :open="publicationOpen" :images="publication.images" :params="publication.params" @close="publicationOpen = false" @saved="publicationSaved" />
    <UModal v-model:open="promptOpen" title="生图提示词" :ui="{ content: 'max-w-2xl' }"><template #body><pre class="image-prompt-text">{{ prompt }}</pre></template></UModal>
    <UModal v-model:open="zoomOpen" :title="`习题图片 · 第 ${selectedPage + 1} 张`" :ui="{ content: 'max-w-5xl' }"><template #body><img v-if="imageUrl" :src="imageUrl" alt="放大的习题图片" class="w-full" /></template><template #footer><UButton label="下载图片" icon="i-lucide-download" @click="download" /></template></UModal>
  </section>
</template>

<style scoped>
.image-workbench { height:100%;min-height:0;display:grid;grid-template-columns:360px minmax(0,1fr); }
.image-controls { min-height:0;overflow:auto;background:var(--ui-bg);border-right:1px solid var(--ui-border); }
.image-panel-heading { display:flex;align-items:center;gap:9px;padding:20px 24px;border-bottom:1px solid var(--ui-border);font-size:14px;font-weight:600; }
.image-form { padding:22px 24px; }.image-fields { display:flex;flex-direction:column;gap:24px;min-width:0;border:0;padding:0;margin:0; }
.image-label { display:block;margin-bottom:10px;font-size:13px;font-weight:600; }.image-grade-grid,.image-type-grid { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px; }.image-type-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
.image-grade-grid button,.image-choice-row button,.image-type-grid button,.image-style-grid button,.image-knowledge-list button { border:1px solid var(--ui-border);border-radius:8px;min-height:36px;padding:7px 9px;font-size:12px;line-height:1.5;background:var(--ui-bg);color:var(--ui-text-toned);cursor:pointer; }
button.selected { border-color:var(--ui-primary);background:color-mix(in srgb,var(--ui-primary) 8%,white);color:var(--ui-primary);font-weight:600; }
button:disabled,fieldset:disabled button { cursor:default;opacity:.55; }button:focus-visible { outline:2px solid var(--ui-primary);outline-offset:2px; }
.image-choice-row { display:flex;gap:8px; }.image-choice-row button { flex:1; }.image-style-grid { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px; }.image-style-grid button { display:flex;flex-direction:column;align-items:center;gap:7px;padding:12px 3px; }
.image-counts { display:flex;flex-direction:column;gap:10px;margin-top:12px; }.image-count-row { display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:12px;color:var(--ui-text-muted); }
.image-knowledge { margin-top:10px;font-size:12px; }.image-knowledge summary,.image-result-prompt summary { cursor:pointer;color:var(--ui-primary); }.image-knowledge-list { display:flex;flex-wrap:wrap;gap:6px;max-height:200px;overflow:auto;margin-top:10px; }.image-knowledge-list button { min-height:30px;text-align:left; }
.image-generate-actions { display:flex;flex-direction:column;gap:12px;margin-top:26px;padding-top:20px;border-top:1px solid var(--ui-border); }.image-action-row { display:flex;align-items:center;justify-content:space-between;gap:8px; }
.image-preview-panel { min-width:0;min-height:0;display:flex;flex-direction:column;background:#f5f7f8; }.image-preview-heading { display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;padding:20px 28px;border-bottom:1px solid var(--ui-border);background:var(--ui-bg); }.image-preview-heading h2 { font-size:14px;font-weight:600; }.image-preview-heading p { margin-top:4px;font-size:12px;color:var(--ui-text-muted); }
.image-preview-scroll { flex:1;min-height:0;overflow:auto;padding:28px; }.worksheet-image { display:block;max-width:100%;max-height:none;width:auto;margin:0 auto;background:white;box-shadow:0 6px 30px #173b3910;border-radius:4px; }.image-result-caption { display:flex;justify-content:center;gap:10px 24px;flex-wrap:wrap;margin:18px auto;font-size:12px;color:var(--ui-text-muted); }.image-result-prompt { max-width:900px;margin:0 auto;padding:16px;background:white;border:1px solid var(--ui-border);border-radius:10px;font-size:12px; }.image-result-prompt pre,.image-prompt-text { white-space:pre-wrap;overflow-wrap:anywhere;font-family:inherit;font-size:13px;line-height:1.85; }.image-result-prompt pre { margin-top:12px; }
.image-empty { display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:450px;height:100%;text-align:center; }.image-empty-icon { display:grid;place-items:center;width:88px;height:88px;border-radius:24px;margin-bottom:24px;background:#e5efec;color:#588c7b; }.image-empty h3 { font-size:20px;font-weight:600;color:var(--ui-text-highlighted); }.image-empty p { margin-top:10px;font-size:13px;line-height:1.8;color:var(--ui-text-muted); }.image-empty-tags { display:flex;justify-content:center;flex-wrap:wrap;gap:10px;margin-top:26px;font-size:11px;color:#698076; }.image-empty-tags span { padding:6px 10px;background:#edf2ef;border-radius:6px; }.image-progress { display:flex;align-items:center;justify-content:center;gap:8px;margin-bottom:20px;font-size:13px;color:var(--ui-primary); }
.image-pages { display:flex;gap:10px;overflow-x:auto;padding:2px 2px 16px;margin-bottom:12px; }.image-pages button { display:flex;flex-direction:column;align-items:center;justify-content:center;gap:5px;flex:0 0 84px;min-height:118px;padding:8px;border:1px solid var(--ui-border);border-radius:9px;background:var(--ui-bg);font-size:12px;cursor:pointer; }.image-pages button.selected { border-color:var(--ui-primary);background:color-mix(in srgb,var(--ui-primary) 8%,white); }.image-pages img { width:46px;height:60px;object-fit:contain; }.image-pages small { font-size:10px;color:var(--ui-text-muted); }
@media(max-width:767px) { .image-workbench { display:block;overflow:auto; }.image-controls { overflow:visible;border-right:0; }.image-preview-panel { min-height:440px; }.image-preview-scroll { overflow:visible;padding:20px; }.image-preview-heading { padding:20px; }.image-empty { min-height:320px; }.image-empty h3 { font-size:18px; } }

/* The form and canvas scroll independently; actions remain within reach. */
.image-workbench { grid-template-columns:minmax(340px,400px) minmax(0,1fr); }
.image-controls { display:flex;flex-direction:column;overflow:hidden; }
.image-panel-heading { padding:20px;flex-shrink:0;gap:12px; }
.image-heading-icon { display:grid;place-items:center;width:40px;height:40px;border-radius:12px;background:var(--ui-bg-elevated);color:var(--ui-primary); }
.image-panel-heading h2 { font-size:15px; }.image-panel-heading p { font-size:11px;color:var(--ui-text-muted);font-weight:400;margin-top:4px; }
.image-service { margin-left:auto;font-size:10px;color:var(--ui-text-muted);white-space:nowrap; }.image-service.online { color:var(--ui-primary); }.image-service.online::before { content:'';display:inline-block;width:6px;height:6px;border-radius:50%;background:currentColor;margin-right:5px; }
.image-form { flex:1;min-height:0;display:flex;flex-direction:column;padding:0; }
.image-fields { flex:1;overflow:auto;gap:0;scrollbar-width:thin; }
.image-setting-section { display:flex;flex-direction:column;gap:20px;padding:22px;border-bottom:1px solid var(--ui-border); }
.image-section-title { display:flex;align-items:center;gap:9px; }.image-section-title>span { display:grid;place-items:center;width:25px;height:25px;border-radius:8px;background:color-mix(in srgb,var(--ui-primary) 9%,var(--ui-bg));color:var(--ui-primary);font-size:11px;font-weight:700; }.image-section-title h3 { font-size:14px;font-weight:650; }.image-section-title small { margin-left:auto;color:var(--ui-text-muted);font-size:11px; }
.image-label small { float:right;color:var(--ui-text-muted);font-weight:400; }.image-field-hint { display:flex;justify-content:space-between;gap:8px;font-size:11px;line-height:1.7;color:var(--ui-text-muted);margin-top:8px; }
.image-type-grid button { display:flex;align-items:center;gap:7px; }.image-counts { background:var(--ui-bg-muted);padding:12px;border-radius:10px; }
.image-difficulty-grid { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px; }.image-difficulty-grid button { border:1px solid var(--ui-border);border-radius:9px;padding:10px 4px;cursor:pointer; }.image-difficulty-grid strong,.image-difficulty-grid small { display:block;font-size:12px; }.image-difficulty-grid small { margin-top:4px;font-size:10px;font-weight:400;color:var(--ui-text-muted); }
.image-knowledge { background:var(--ui-bg-muted);border-radius:8px;padding:10px; }.image-knowledge summary { font-size:11px; }
.image-style-grid { gap:7px; }.image-style-grid button { padding:7px 6px 10px;gap:9px; }.image-style-grid strong { font-size:11px;font-weight:500; }
.image-style-sample { display:flex;flex-direction:column;align-items:flex-start;gap:5px;width:100%;height:75px;border-radius:5px;padding:9px 10px;background:#fff6e8;color:#c59243; }.image-style-sample i { width:100%;height:3px;background:currentColor;opacity:.2;border-radius:2px; }.image-style-sample i:last-child { width:60%; }.image-style-sample[data-style=clean] { background:#edf5f2;color:#4c8678; }.image-style-sample[data-style=black_white] { background:#f1f1f1;color:#555; }
.image-generate-actions { flex-shrink:0;margin:0;padding:14px 20px;gap:8px;background:var(--ui-bg);box-shadow:0 -6px 20px #163b3505; }.image-order-summary { font-size:12px;font-weight:600;color:var(--ui-text-toned); }
.image-preview-panel { background:var(--ui-bg-muted); }.image-preview-heading { padding:19px 24px; }.image-preview-scroll { background-image:radial-gradient(color-mix(in srgb,var(--ui-text-muted) 15%,transparent) .8px,transparent .8px);background-size:20px 20px; }
.image-batch-progress { padding:14px 24px 0; }.image-batch-progress>div { display:flex;justify-content:space-between;font-size:12px;color:var(--ui-text-muted); }.image-batch-progress strong { color:var(--ui-primary); }.image-batch-progress progress { width:100%;height:5px;accent-color:var(--ui-primary);border:0;border-radius:10px;overflow:hidden; }.image-batch-progress progress::-webkit-progress-bar { background:var(--ui-border); }.image-batch-progress progress::-webkit-progress-value { background:var(--ui-primary);transition:width .3s; }
.image-design-preview { display:flex;flex-direction:column;align-items:center;max-width:720px;margin:4px auto 20px; }.image-preview-intro { text-align:center;margin-bottom:28px; }.image-eyebrow { display:inline-flex;align-items:center;gap:7px;color:var(--ui-primary);font-size:11px; }.image-preview-intro h3 { margin-top:10px;font-size:clamp(20px,2vw,27px);font-weight:650;letter-spacing:-.6px;color:var(--ui-text-highlighted); }.image-preview-intro p { margin-top:8px;font-size:12px;color:var(--ui-text-muted); }
.image-paper { --paper-accent:#af7e3b;--paper-wash:#fcf5e9;width:100%;max-width:440px;min-height:410px;background:#fff;color:#343b39;border:1px solid #e6e6df;border-radius:5px;padding:30px 32px 20px;box-shadow:0 16px 45px #25463a12,0 3px 8px #25463a08;position:relative;overflow:hidden; }
.image-paper::before { content:'';position:absolute;top:0;left:0;right:0;height:6px;background:var(--paper-accent);opacity:.65; }.image-paper[data-style=clean] { --paper-accent:#4c8678;--paper-wash:#edf5f2; }.image-paper[data-style=black_white] { --paper-accent:#555;--paper-wash:#f3f3f3; }
.image-paper-top { display:flex;align-items:center;justify-content:space-between;font-size:11px;color:var(--paper-accent); }.image-paper h4 { font-size:23px;line-height:1.5;font-weight:700;margin-top:18px;overflow-wrap:anywhere; }.image-paper-meta { color:#959c98;font-size:10px;margin-top:12px; }.image-paper-rule { height:1px;background:#e9ece8;margin:20px 0; }
.image-paper-placeholder { text-align:center;color:var(--paper-accent);background:var(--paper-wash);padding:35px 10px;border-radius:10px; }.image-paper-placeholder p { font-size:13px;margin-top:12px; }.image-paper-placeholder span { display:block;font-size:10px;margin-top:8px;opacity:.75; }
.image-paper-exercise { margin-bottom:18px; }.image-paper-exercise>div:first-child { display:flex;align-items:center;gap:8px;font-size:12px; }.image-paper-exercise span { font-size:10px;color:var(--paper-accent);padding:3px 6px;border-radius:4px;background:var(--paper-wash); }.image-paper-exercise small { margin-left:auto;color:#959c98;font-size:10px; }.image-paper-lines { display:flex;gap:16px;margin:18px 0 10px; }.image-paper-lines i { height:1px;background:#e5e9e5;flex:1; }.image-paper-bottom { display:flex;justify-content:space-between;font-size:10px;color:#959c98;margin-top:30px; }
.image-preview-disclaimer { display:flex;align-items:center;gap:5px;text-align:center;color:var(--ui-text-muted);font-size:11px;margin-top:17px; }.image-flow { display:flex;align-items:center;gap:16px;margin-top:28px;color:var(--ui-text-muted);font-size:11px; }.image-flow span { display:flex;align-items:center;gap:7px; }.image-flow b { display:grid;place-items:center;width:21px;height:21px;border:1px solid var(--ui-border);border-radius:50%;font-size:10px;background:var(--ui-bg);font-weight:500; }
.image-result-prompt { background:var(--ui-bg); }button { transition:background .15s,border-color .15s,box-shadow .15s; }button:not(:disabled):hover { border-color:var(--ui-primary); }button.selected { background:color-mix(in srgb,var(--ui-primary) 8%,var(--ui-bg)); }
@media (min-width:768px) and (max-width:1100px) { .image-workbench { grid-template-columns:340px minmax(0,1fr); }.image-preview-scroll { padding:22px 16px; }.image-paper { padding:24px 20px 18px; }.image-flow { gap:8px; } }
@media(max-width:767px) { .image-workbench { display:block; }.image-controls { overflow:visible; }.image-form,.image-fields { display:block;overflow:visible; }.image-generate-actions { position:sticky;bottom:0;z-index:5;border-top:1px solid var(--ui-border);padding:12px 20px; }.image-setting-section { padding:20px; }.image-preview-scroll { padding:24px 16px; }.image-preview-intro h3 { font-size:21px; }.image-paper { padding:24px;min-height:360px; }.image-flow { gap:9px; }.image-preview-disclaimer { font-size:10px; } }
@media(prefers-reduced-motion:reduce) { button,.image-batch-progress progress::-webkit-progress-value { transition:none; }.animate-spin { animation:none; } }
.image-mobile-tabs { display:none; }.image-draft-status { color:var(--ui-text-muted);font-size:10px; }.image-history-list { display:flex;flex-direction:column;gap:8px; }.image-history-list button { display:grid;grid-template-columns:1fr auto;gap:6px;text-align:left;padding:14px;border:1px solid var(--ui-border);border-radius:8px;background:var(--ui-bg); }.image-history-list strong { font-size:13px;overflow-wrap:anywhere; }.image-history-list span { grid-row:2;font-size:11px;color:var(--ui-text-muted); }
@media(max-width:767px) {
.image-workbench { display:flex;flex-direction:column;overflow:hidden; }.image-mobile-tabs { display:flex;flex-shrink:0;gap:6px;padding:8px 16px;background:var(--ui-bg);border-bottom:1px solid var(--ui-border); }.image-mobile-tabs button { flex:1;padding:10px;border-radius:8px;font-size:13px;color:var(--ui-text-muted); }.image-mobile-tabs button[aria-pressed=true] { color:var(--ui-primary);background:color-mix(in srgb,var(--ui-primary) 8%,var(--ui-bg));font-weight:600; }
.image-controls { flex:1;min-height:0;overflow:hidden; }.image-form { display:flex; }.image-fields { display:block;overflow:auto; }.image-generate-actions { position:static; }.image-preview-panel { flex:1;min-height:0; }.image-preview-scroll { overflow:auto; }.image-workbench[data-mobile-panel=preview] .image-controls { flex:0 0 auto;order:3; }.image-workbench[data-mobile-panel=preview] .image-panel-heading,.image-workbench[data-mobile-panel=preview] .image-fields { display:none; }.image-workbench[data-mobile-panel=settings] .image-preview-panel { display:none; }
}
</style>
