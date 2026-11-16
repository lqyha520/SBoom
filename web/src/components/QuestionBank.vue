<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useExamStore } from '../stores/exam'
import { useAuthStore } from '../stores/auth'
import { TYPE_NAME } from '../constants'
import { answerOf } from '../utils'
import { assembleBankPaper, bankEdit, bankList, bankQuestionCount, bankRemove, bankSelect, bankSelectionIssue } from '../question-bank'
import type { BankItem } from '../../../shared/teaching'
import type { Difficulty, Question } from '../types'
const emit = defineEmits<{ close: []; assembled: []; generate: [] }>()
const bankAnswer = (question: BankItem['questions'][number]) => answerOf(question as Question)
const store = useExamStore(), auth = useAuthStore()
const items = ref<BankItem[]>([]), total = ref(0), bankTotal = ref(0), page = ref(1), selected = ref<BankItem[]>([])
const available = ref<Record<string, string[]>>({}), guidance = ref(false), selectionError = ref('')
const q = ref(''), grade = ref(store.grade), subject = ref(store.subject), type = ref(''), difficulty = ref('')
const busy = ref(false), loading = ref(false), error = ref(''), title = ref('题库组卷')
const editing = ref<BankItem | null>(null), editTitle = ref(''), editTopic = ref(''), editDifficulty = ref<Difficulty>('medium')
const count = computed(() => selected.value.length)
const questionCount = computed(() => bankQuestionCount(selected.value))
const selectionIssue = computed(() => bankSelectionIssue(selected.value))
const hasFilters = computed(() => !!(q.value || grade.value || subject.value || type.value || difficulty.value))
const gradeOptions = computed(() => [{ label: '全部年级', value: '' }, ...[...new Set([...Object.keys(store.available), ...Object.keys(available.value), grade.value].filter(Boolean))].map(value => ({ label: value, value }))])
const subjectOptions = computed(() => [{ label: '全部学科', value: '' }, ...[...new Set([...Object.entries(store.available), ...Object.entries(available.value)].filter(([key]) => !grade.value || key === grade.value).flatMap(([, values]) => values).concat(subject.value).filter(Boolean))].map(value => ({ label: value, value }))])
const isSelected = (item: BankItem) => selected.value.some(value => value.id === item.id)
const additionIssue = (item: BankItem) => isSelected(item) ? '' : bankSelectionIssue([...selected.value, item])
function deselect(id: string) { selected.value = selected.value.filter(item => item.id !== id); selectionError.value = '' }
function clearSelection() { selected.value = []; selectionError.value = '' }
let sequence = 0, controller: AbortController | undefined
function invalidate() { sequence++; controller?.abort() }
async function load() {
  invalidate(); controller = new AbortController(); const run = sequence
  loading.value = true; error.value = ''
  try {
    const result = await bankList({ q: q.value, grade: grade.value, subject: subject.value, section_type: type.value, difficulty: difficulty.value, limit: 20, offset: (page.value - 1) * 20 }, controller.signal)
    if (run === sequence) {
      total.value = result.total; bankTotal.value = result.bank_total ?? result.total; available.value = result.available || {}
      const lastPage = Math.max(1, Math.ceil(result.total / 20))
      if (page.value > lastPage) { page.value = lastPage; await load(); return }
      items.value = result.items
      selected.value = selected.value.map(item => result.items.find(value => value.id === item.id) || item)
    }
  } catch (cause) { if (run === sequence) error.value = cause instanceof Error ? cause.message : '加载失败' }
  finally { if (run === sequence) loading.value = false }
}
function search() { page.value = 1; void load() }
function clearFilters() { q.value = grade.value = subject.value = type.value = difficulty.value = ''; search() }
function toggle(item: BankItem) {
  if (busy.value || loading.value) return
  if (isSelected(item)) { deselect(item.id); return }
  selectionError.value = additionIssue(item)
  if (!selectionError.value) selected.value.push(item)
}
async function act(operation: () => Promise<void>) {
  if (busy.value || store.accountChanged) return
  const owner = auth.user?.id; busy.value = true; error.value = ''
  try { await operation() } catch (cause) { if (auth.user?.id === owner) error.value = cause instanceof Error ? cause.message : '操作失败' }
  finally { busy.value = false }
}
async function assemble() {
  if (store.generating || store.layoutMode || selectionIssue.value) return
  await act(async () => {
    const owner = auth.user?.id
    const result = await bankSelect(selected.value.map(item => item.id))
    if (owner !== auth.user?.id || store.accountChanged) return
    const paper = assembleBankPaper(result.items, title.value)
    store.recordEdit()
    store.papers.unshift(paper); store.view = 'result'
    if (!await store.flushDraft()) error.value = '试卷已组好，草稿保存失败，请及时导出保留'
    else { emit('assembled'); emit('close') }
  })
}
async function remove(item: BankItem) {
  if (!window.confirm('删除题库中的“' + item.title + '”？已组好的试卷会保留。')) return
  await act(async () => { await bankRemove(item); deselect(item.id); await load() })
}
function edit(item: BankItem) { editing.value = item; editTitle.value = item.title; editTopic.value = item.topic; editDifficulty.value = item.difficulty }
async function saveMetadata() {
  const item = editing.value; if (!item || !editTitle.value.trim()) return
  await act(async () => { await bankEdit(item, editTitle.value, editTopic.value, editDifficulty.value); editing.value = null; await load() })
}
watch(grade, value => { if (value && ![...(store.available[value] || []), ...(available.value[value] || [])].includes(subject.value)) subject.value = '' })
watch(() => auth.user?.id, () => { invalidate(); items.value = []; clearSelection(); available.value = {}; editing.value = null; error.value = ''; emit('close') })
onMounted(load); onBeforeUnmount(invalidate)
</script>
<template>
  <UModal :open="true" title="我的题库" description="保存好题，以后直接组卷。题目按账号保存，仅你自己可见；阅读题连同文章整篇复用。" :dismissible="!busy" :close="!busy" :ui="{ content: 'max-w-4xl' }" @update:open="value => { if (!value) emit('close') }">
    <template #body>
      <form class="bank-filters" @submit.prevent="search">
        <UInput v-model="q" :maxlength="120" placeholder="搜索题干、标题、知识点" aria-label="搜索个人题库" />
        <USelect v-model="grade" :items="gradeOptions" aria-label="题库年级" />
        <USelect v-model="subject" :items="subjectOptions" aria-label="题库学科" />
        <USelect v-model="type" :items="[{label:'全部题型',value:''}, ...Object.entries(TYPE_NAME).map(([value,label]) => ({value,label}))]" aria-label="题库题型" />
        <USelect v-model="difficulty" :items="[{label:'全部难度',value:''},{label:'简单',value:'easy'},{label:'适中',value:'medium'},{label:'较难',value:'hard'}]" aria-label="题库难度" />
        <UButton type="submit" label="筛选" :disabled="busy" :loading="loading" />
        <UButton label="清空筛选" variant="ghost" :disabled="busy || !hasFilters" @click="clearFilters" />
      </form>
      <UAlert v-if="error" :title="error" color="error" class="my-3" />
      <UAlert v-if="selectionError || selectionIssue" :title="selectionError || selectionIssue" color="warning" class="my-3" />
      <div class="bank-overview"><p>匹配 {{ total }} 条 · 题库共 {{ bankTotal }} 条</p><UButton label="如何保存题目" variant="ghost" size="xs" @click="guidance = !guidance" /></div>
      <ol v-if="guidance" class="bank-guide"><li>在工作台设置出题条件并生成试卷。</li><li>打开“管理题目”，找到满意的题目，点击“存入题库”。阅读理解会保存整篇文章和全部小题。</li><li>回到“我的题库”，勾选同年级、同学科的题目，即可组卷并导出。</li></ol>
      <section v-if="count" class="bank-selection" aria-label="已选题目清单">
        <div class="bank-overview"><strong>已选择 {{ count }} 条收藏，共 {{ questionCount }} 道题</strong><UButton label="清空已选" variant="ghost" size="xs" :disabled="busy" @click="clearSelection" /></div>
        <p class="text-xs text-muted">最多 100 条收藏、300 道题。翻页和筛选会保留已选题目；组卷后请核对答案和解析。</p>
        <details><summary>查看全部已选题目（含其他页面）</summary><div v-for="item in selected" :key="item.id" class="bank-selected-row"><span>{{ item.title }} · {{ item.grade }} {{ item.subject }} · {{ item.questions.length }} 道</span><UButton :aria-label="'移除已选：' + item.title" label="移除" variant="ghost" size="xs" :disabled="busy" @click="deselect(item.id)" /></div></details>
      </section>
      <div v-if="!loading && !error && !items.length" class="bank-empty">
        <strong>{{ bankTotal ? '没有符合筛选条件的题目' : '还没有保存题目' }}</strong>
        <p>{{ bankTotal ? '换个年级、学科或关键词试试，已选题目仍在清单中。' : '生成试卷后，在“管理题目”中点击“存入题库”，以后就能直接选题组卷。' }}</p>
        <UButton v-if="bankTotal" label="清空筛选查看全部" variant="outline" @click="clearFilters" />
        <UButton v-else label="去生成题目" :disabled="busy || store.generating || store.layoutMode" @click="emit('generate'); emit('close')" />
      </div>
      <article v-for="item in items" :key="item.id" class="bank-item">
        <UCheckbox :model-value="isSelected(item)" :label="item.title" :disabled="busy || loading || !!additionIssue(item)" @update:model-value="toggle(item)" />
        <p class="text-xs text-muted">{{ item.grade }} · {{ item.subject }} · {{ TYPE_NAME[item.section_type] || item.section_type }} · {{ item.topic || '未标注知识点' }}</p>
        <p v-if="additionIssue(item)" class="text-xs text-warning">{{ additionIssue(item) }}</p>
        <details><summary>查看题目、答案与解析（{{ item.questions.length }} 道）</summary><p v-if="item.passage" class="whitespace-pre-wrap">{{ item.passage }}</p><div v-for="(question,index) in item.questions" :key="index" class="py-2"><p>{{ question.stem || [question.top,question.left,question.right,question.left_expr,question.right_expr].filter(v => v != null).join(' / ') }}</p><p v-if="question.options">{{ question.options.join('；') }}</p><p v-if="question.left_items">{{ question.left_items.join('；') }} ↔ {{ question.right_items?.join('；') }}</p><p>答案：{{ bankAnswer(question) }}</p><p>解析：{{ question.analysis || '待补充' }}</p></div></details>
        <div class="flex gap-2"><UButton label="编辑标题与知识点" size="xs" variant="ghost" :disabled="busy" @click="edit(item)" /><UButton label="删除" size="xs" color="error" variant="ghost" :disabled="busy" @click="remove(item)" /></div>
      </article>
      <div class="flex items-center justify-between mt-4"><UButton label="上一页" variant="outline" :disabled="page <= 1 || loading || busy" @click="page--; load()" /><span>第 {{ page }} 页</span><UButton label="下一页" variant="outline" :disabled="page * 20 >= total || loading || busy" @click="page++; load()" /></div>
    </template>
    <template #footer><div class="bank-footer"><UInput v-model="title" :maxlength="240" aria-label="组卷标题" placeholder="组卷标题" /><span class="text-xs text-muted">{{ count }} 条收藏 · {{ questionCount }} / 300 道题</span><UButton label="取消" variant="outline" :disabled="busy" @click="emit('close')" /><UButton :label="'用所选题目组卷（' + questionCount + ' 道）'" :loading="busy" :disabled="!count || loading || !!selectionIssue || store.generating || store.layoutMode" @click="assemble" /></div></template>
  </UModal>
  <UModal :open="!!editing" title="整理题目" :dismissible="!busy" @update:open="value => { if (!value && !busy) editing = null }"><template #body><div class="space-y-3"><UFormField label="标题"><UInput v-model="editTitle" :maxlength="240" /></UFormField><UFormField label="知识点"><UInput v-model="editTopic" :maxlength="200" /></UFormField><UFormField label="难度"><USelect v-model="editDifficulty" :items="[{label:'简单',value:'easy'},{label:'适中',value:'medium'},{label:'较难',value:'hard'}]" /></UFormField><UAlert v-if="error" :title="error" color="error" /></div></template><template #footer><UButton label="取消" variant="outline" :disabled="busy" @click="editing = null" /><UButton label="保存" :loading="busy" :disabled="!editTitle.trim()" @click="saveMetadata" /></template></UModal>
</template>
<style scoped>
.bank-filters { display:grid;grid-template-columns:2fr 1fr 1fr;gap:10px; }.bank-item { padding:14px 0;border-bottom:1px solid var(--ui-border);display:grid;gap:8px; }.bank-item details,.bank-selection details { font-size:13px;line-height:1.8; }.bank-item summary,.bank-selection summary { cursor:pointer;color:var(--ui-primary); }.bank-overview,.bank-selected-row { display:flex;align-items:center;justify-content:space-between;gap:10px;margin:10px 0;font-size:13px; }.bank-selected-row span { min-width:0;overflow-wrap:anywhere; }.bank-selection { padding:12px;background:var(--ui-bg-elevated);border-radius:10px; }.bank-guide { padding:12px 12px 12px 30px;background:var(--ui-bg-elevated);line-height:1.8;font-size:13px; }.bank-empty { display:grid;justify-items:start;gap:12px;padding:24px 0;font-size:13px; }.bank-footer { display:flex;align-items:center;gap:10px;flex-wrap:wrap;width:100%; }.bank-footer > :first-child { flex:1;min-width:160px; }@media(max-width:600px) { .bank-filters { grid-template-columns:1fr 1fr; }.bank-filters > :first-child { grid-column:1 / -1; } }
</style>
