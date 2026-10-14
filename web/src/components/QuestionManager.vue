<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useExamStore } from '../stores/exam'
import { TYPE_NAME } from '../constants'
import { answerOf } from '../utils'
import { confirmQuestionReview, invalidateQuestionReview, isManuallyReviewed, paperQuality, questionConcerns } from '../question-quality'
import type { Question } from '../types'
const props = defineProps<{ sectionId?: string; paperIndex?: number }>()
const emit = defineEmits<{ close: [] }>()
const store = useExamStore()
const selected = ref(props.sectionId || '')
const error = ref(''), notice = ref(''), confirming = ref('')
const options = computed(() => props.paperIndex === undefined
  ? store.sections.map(item => ({ value: item.id, label: item.name || TYPE_NAME[item.type] || item.type }))
  : (store.papers[props.paperIndex]?.sections || []).map((item, index) => ({ value: item._sid || String(index), label: item.name || TYPE_NAME[item.type] || item.type })))
watch(options, items => { if (!items.some(item => item.value === selected.value)) selected.value = items[0]?.value || '' }, { immediate: true })
const section = computed(() => store.questionSection(selected.value, props.paperIndex))
const concernsOnly = ref(false)
const editing = ref(''), answerDraft = ref(''), analysisDraft = ref('')
const rows = computed(() => {
  const paper = props.paperIndex === undefined ? undefined : store.papers[props.paperIndex]
  const quality = paper ? paperQuality(paper).find(item => item.sectionId === selected.value) : undefined
  return (section.value?.data?.questions || []).map((question, index) => ({ question, index,
    manual: isManuallyReviewed(question, section.value?.data?.passage),
    issues: quality?.questions.find(item => item.index === index)?.issues || questionConcerns(question, section.value?.data?.passage) }))
    .filter(row => !concernsOnly.value || row.issues.length)
})
watch(() => props.sectionId, value => { if (value) selected.value = value })
watch(selected, () => { editing.value = ''; error.value = ''; notice.value = '' })
function lockVisible(locked: boolean) {
  if (store.generating || section.value?.type === 'reading') return
  const questions = rows.value.map(row => row.question).filter(question => !question._replacement && !!question._locked !== locked)
  if (!questions.length) return
  store.recordEdit()
  questions.forEach(question => { question._locked = locked })
}
function editAnswer(question: Question) {
  editing.value = question._qid || ''
  answerDraft.value = Array.isArray(question.answer) ? JSON.stringify(question.answer) : String(question.answer ?? '')
  analysisDraft.value = question.analysis || ''
  error.value = ''
}
function reviewQuestion(question: Question) {
  if (store.generating || store.layoutMode || question._replacement || editing.value) return
  error.value = ''; notice.value = ''
  const manual = isManuallyReviewed(question, section.value?.data?.passage)
  try {
    // 先校验副本，再记录撤销，避免无效确认产生空历史。
    const candidate = { ...question }
    if (!manual) confirmQuestionReview(candidate, section.value?.data?.passage)
    store.recordEdit()
    if (manual) delete question._manualReview
    else question._manualReview = candidate._manualReview
    notice.value = manual ? '已撤销人工确认' : '已记录人工核对结果'
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '确认失败' }
}
function saveAnswer(question: Question) {
  const text = answerDraft.value.trim()
  if (!text) { error.value = '请填写答案'; return }
  let answer: Question['answer'] = text
  if (question.options) {
    answer = /^[A-Ha-h]$/.test(text) ? text.toUpperCase().charCodeAt(0) - 65 : Number(text)
    if (!Number.isInteger(answer) || answer < 0 || answer >= question.options.length) { error.value = '选择题请填写选项字母或从 0 开始的索引'; return }
  } else if (question.left_items) {
    try {
      const pairs: unknown = JSON.parse(text)
      const count = question.left_items.length
      if (!Array.isArray(pairs) || pairs.length !== count || pairs.some(pair => !Array.isArray(pair) || pair.length !== 2 || pair.some(i => !Number.isInteger(i) || i < 0 || i >= count)) || new Set(pairs.map(pair => pair[0])).size !== count || new Set(pairs.map(pair => pair[1])).size !== count) throw new Error()
      answer = pairs as [number, number][]
    } catch { error.value = '配对答案请填写不重复、不越界的索引对，例如 [[0,1],[1,0]]'; return }
  }
  store.recordEdit()
  question.answer = answer
  question.analysis = analysisDraft.value.trim()
  invalidateQuestionReview(question)
  editing.value = ''; error.value = ''; notice.value = '已保存答案和解析，请核对修改后的题目；可撤销恢复'
}
async function replace() {
  const qid = confirming.value; confirming.value = ''; error.value = ''; notice.value = ''
  try { await store.replaceQuestion(selected.value, qid, props.paperIndex); notice.value = '已替换此题，可通过撤销恢复原题' }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '替换失败，原题已保留' }
}
</script>
<template>
  <UModal :open="true" title="管理题目" :dismissible="!store.generating" :close="!store.generating" :ui="{ content: 'max-w-2xl' }" @update:open="value => { if (!value) emit('close') }">
    <template #body>
      <USelect v-model="selected" :items="options" aria-label="选择要管理的大题" :disabled="store.generating" class="w-full mb-4" />
      <p class="text-sm text-muted mb-4">锁定的题目会在重新生成时保留。换题包含生成与复核，可能产生费用。模型复核通过后仍可人工核对。</p>
      <p v-if="section?.data?.passage" class="whitespace-pre-wrap rounded bg-elevated p-3 mb-4 text-sm">{{ section.data.passage }}</p>
      <div class="flex flex-wrap gap-3 items-center mb-4">
        <UCheckbox v-model="concernsOnly" label="仅看待核对题目" />
        <UButton label="锁定显示的题目" size="xs" variant="outline" :disabled="store.generating || section?.type === 'reading'" @click="lockVisible(true)" />
        <UButton label="解锁显示的题目" size="xs" variant="ghost" :disabled="store.generating || section?.type === 'reading'" @click="lockVisible(false)" />
      </div>
      <UAlert v-if="section?.type === 'reading'" title="阅读理解与文章关联，请从大题菜单整体重新生成" color="info" class="mb-4" />
      <UAlert v-if="error" :title="error" color="error" class="mb-4" /><UAlert v-if="notice" :title="notice" color="success" class="mb-4" />
      <p v-if="!rows.length" role="status" class="text-sm text-muted">{{ concernsOnly ? '当前大题没有待核对题目' : '当前大题暂无题目' }}</p>
      <div v-for="{ question, index, issues, manual } in rows" :key="question._qid" class="border-b border-default py-3">
        <p class="text-sm whitespace-pre-wrap">{{ index + 1 }}. {{ question.stem || [question.left_expr, question.right_expr].filter(Boolean).join(' ○ ') || [question.top, question.left, question.right].filter(value => value != null).join(' / ') || '配对题' }}</p>
        <ol v-if="question.options" class="text-sm mt-2 space-y-1"><li v-for="(option, optionIndex) in question.options" :key="optionIndex">{{ String.fromCharCode(65 + optionIndex) }}. {{ option }}</li></ol>
        <div v-if="question.left_items" class="grid grid-cols-2 gap-4 text-sm mt-2"><div><p v-for="(item, i) in question.left_items" :key="i">{{ i + 1 }}. {{ item }}</p></div><div><p v-for="(item, i) in question.right_items" :key="i">{{ i + 1 }}. {{ item }}</p></div></div>
        <p class="text-sm mt-2">答案：{{ answerOf(question) }}</p>
        <p v-if="question.acceptable_answers?.length" class="text-xs text-muted mt-1">其他可接受答案：{{ question.acceptable_answers.join('；') }}</p>
        <p class="text-sm whitespace-pre-wrap mt-2">解析：{{ question.analysis || '暂无解析' }}</p>
        <ul v-if="issues.length" class="text-xs text-warning mt-2"><li v-for="issue in issues" :key="issue">{{ issue }}</li></ul>
        <p v-if="manual" class="text-xs text-primary mt-2">人工核对完成</p>
        <p v-else-if="!issues.length" class="text-xs text-primary mt-2">模型复核通过</p>
        <div v-if="editing === question._qid" class="space-y-3 mt-3">
          <UFormField label="答案" :description="question.options ? '填写选项字母，或从 0 开始的索引' : undefined"><UTextarea v-model="answerDraft" aria-label="修改答案" class="w-full" :disabled="store.generating" /></UFormField>
          <UFormField label="解析"><UTextarea v-model="analysisDraft" aria-label="修改解析" class="w-full" :disabled="store.generating" /></UFormField>
          <UButton label="保存修改" size="xs" :disabled="store.generating" @click="saveAnswer(question)" /><UButton label="取消修改" size="xs" variant="ghost" @click="editing = ''" />
        </div>
        <div class="flex flex-wrap gap-2 mt-2">
          <UButton :label="manual ? '撤销人工确认' : '确认已核对'" :icon="manual ? 'i-lucide-undo-2' : 'i-lucide-check-check'" size="xs" variant="soft" :disabled="store.generating || store.layoutMode || !!question._replacement || !!editing" @click="reviewQuestion(question)" />
          <UButton label="修改答案与解析" size="xs" variant="ghost" :disabled="store.generating" @click="editAnswer(question)" />
          <UButton :label="question._locked ? '已锁定 · 点击解锁' : '锁定此题'" :icon="question._locked ? 'i-lucide-lock-keyhole' : 'i-lucide-lock-keyhole-open'" size="xs" variant="soft" :disabled="store.generating || section?.type === 'reading' || !!question._replacement" @click="store.toggleQuestionLock(selected, question._qid!, paperIndex)" />
          <UButton :label="question._replacement ? '查询并重试换题' : '换一道题'" icon="i-lucide-refresh-cw" size="xs" variant="outline" :disabled="store.generating || question._locked || section?.type === 'reading'" @click="confirming = question._qid!" />
        </div>
      </div>
    </template>
    <template #footer><UButton label="完成" :disabled="store.generating" @click="emit('close')" /></template>
  </UModal>
  <UModal :open="!!confirming" title="替换这道题？" description="仅替换此题，其他题目保持不变。请求可能产生费用；失败时保留原题，仍在处理的请求不会重复发送。" @update:open="value => { if (!value) confirming = '' }"><template #footer><UButton label="取消" variant="outline" @click="confirming = ''" /><UButton label="确认换题" @click="replace" /></template></UModal>
</template>
