<script setup lang="ts">
import { permissionDirective as vPermission, canPermission } from '../permissions'
import XhsParentPicker from './XhsParentPicker.vue'
import { computed, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { request, type UserInfo } from '../api'
import { adminRoute, navigateAdmin } from '../navigation'
import { downloadBlob } from '../../../shared/download'
import { cleanWorkflowData, goWorkflow, materialReviewFingerprint, newMaterial, nextWorkflow, useWorkflow, workflowError, type IdeaData, type MaterialData } from '../xhs-workflow'
import { generationGrade, useXhsGeneration } from '../xhs-generation'
import { exportMaterial, materialMarkdown } from '../xhs-content-export'
import XhsWorkflowFrame from './XhsWorkflowFrame.vue'
import XhsWorkflowLinks from './XhsWorkflowLinks.vue'
import XhsWorkflowVersions from './XhsWorkflowVersions.vue'
import XhsMaterialPreview from './XhsMaterialPreview.vue'
const props = defineProps<{ user: UserInfo }>()
const w = useWorkflow('materials', newMaterial, (parent, data) => {
  if (!parent) return
  const idea = parent.data as IdeaData
  Object.assign(data, { title: idea.title, grade: idea.grade, subject: idea.subject, keyword: idea.keyword, instructions: idea.problem })
}, props.user.id)
const { items,total,page,q,filter,record,data,parent,editing,busy,loading,error,notice,dirty } = w
const step = ref('setup'), exporting = ref(false), preparing = ref(false)
let preparationSequence = 0
function stopPreparing() { preparationSequence++; preparing.value = false }
const linked = computed(() => !!parent.value)
const completeQuestions = computed(() => data.value.questions.length > 0 && data.value.questions.every(item => item.stem.trim() && item.answer.trim() && item.analysis.trim()))
const needsReviewSave = computed(() => !record.value || materialReviewFingerprint(data.value) !== materialReviewFingerprint(record.value.data))
const existingDraft = computed(() => record.value?.children?.find(child => child.kind === 'drafts' && child.status !== 'archived'))
watch(w.editorSession, () => { step.value = 'setup'; stopPreparing() }, { flush: 'sync' })
onDeactivated(stopPreparing); onBeforeUnmount(stopPreparing)
watch(() => [data.value, materialReviewFingerprint(data.value)] as const, ([value, fingerprint], [previous, oldFingerprint]) => {
  if (value !== previous || fingerprint === oldFingerprint || loading.value) return
  Object.assign(value, { status: 'draft', accuracy_checked: false, scope_checked: false, layout_checked: false })
}, { flush: 'sync' })
interface Generated { questions: { stem: string; options?: string[] | null; answer: string | number; analysis?: string; quality_issues?: string[] }[]; request_id: string; quality_warnings?: string[] }
const generation = useXhsGeneration<Generated>(props.user.id, () => record.value?.id || '', 'material')
const { busy: generating, error: generationError, pending, result: generatedResult } = generation
const generationBusy = computed(() => preparing.value || generating.value)
const changedSinceGeneration = computed(() => !!pending.value && !generation.matches(record.value?.revision || 0, data.value))
async function accept(output: Generated | null, target: string, explicit = false) {
  if (!output || record.value?.id !== target || adminRoute.tab !== 'xhsMaterials') return
  if (dirty.value) { error.value = '生成结果已保留。当前有未保存的编辑，请保存后再查询取回。'; return }
  if (changedSinceGeneration.value) {
    if (!explicit) { notice.value = '生成期间资料已有修改，结果已保留。请核对题目与当前年级、知识点和题型后再应用。'; return }
    if (!window.confirm('请确认生成题目与当前年级、知识点、题型和题数相符。应用后会替换现有题目并重新要求复核，原题保留在历史版本中，是否继续？')) return
  }
  data.value.questions = output.questions.map(item => ({ stem: item.stem, options: item.options || [], answer: item.options?.length && typeof item.answer === 'number' ? `${String.fromCharCode(65 + item.answer)}（${item.options[item.answer] || ''}）` : String(item.answer), analysis: item.analysis || '', quality_issues: item.quality_issues || [] }))
  data.value.generation_request_id = output.request_id; data.value.status = 'draft'; data.value.accuracy_checked = false; data.value.scope_checked = false; data.value.layout_checked = false
  step.value = 'questions'
  if (await w.save()) { generation.finish(); notice.value = '生成结果已保存，请逐题检查答案和讲解。' }
}
async function generate() {
  if (generationBusy.value || pending.value || busy.value || loading.value || !parent.value) return
  if (!data.value.keyword.trim()) { error.value = '先填写具体知识点'; return }
  const key = ++preparationSequence, session = w.editorSession.value, fingerprint = materialReviewFingerprint(data.value)
  const current = () => key === preparationSequence && session === w.editorSession.value && adminRoute.tab === 'xhsMaterials'
  preparing.value = true; error.value = ''
  try {
    const { available } = await request<{ available: Record<string, string[]> }>('/api/v1/scope/available')
    if (!current()) return
    if (fingerprint !== materialReviewFingerprint(data.value)) { error.value = '出题设置或题目已修改，请重新点击生成。'; return }
    const grade = generationGrade(data.value.grade, data.value.subject, available)
    if (!grade) { error.value='当前年级和科目暂无已核实教材范围，可选择受支持的年级科目，或手动编写资料。';return }
    if (!(await w.save()) || !current()) return
    const value = cleanWorkflowData(data.value), target = record.value!.id
    preparing.value = false
    await accept(await generation.generate('/api/v1/generate', { grade, subject: value.subject, keyword: value.keyword, game_type: value.game_type, difficulty: value.difficulty, question_count: value.question_count }, record.value!.revision, value), target)
  } catch (cause) { if (current()) error.value = workflowError(cause) }
  finally { if (key === preparationSequence) preparing.value = false }
}
async function recover() { if (dirty.value) { error.value='请先保存当前编辑，再取回生成结果。';return };const target=record.value?.id || '';await accept(await generation.recover(),target) }
async function applyGenerated() { await accept(generatedResult.value, record.value?.id || '', true) }
function addQuestion() { data.value.questions.push({ stem: '', options: [], answer: '', analysis: '', quality_issues: [] }) }
async function exportPdf(answers: boolean) { if (exporting.value) return; exporting.value = true; error.value = ''; const session = w.editorSession.value; try { await exportMaterial(cleanWorkflowData(data.value), answers) } catch (cause) { if (session === w.editorSession.value) error.value = workflowError(cause) } finally { exporting.value = false } }
async function review() { if (await w.save()) step.value = 'review' }
async function createDraft(fresh = false) {
  if (!completeQuestions.value || !(await w.save())) return
  if (!fresh && existingDraft.value) goWorkflow('drafts', existingDraft.value.id)
  else nextWorkflow('drafts', record.value!.id)
}
function restore(value: object) { data.value = cleanWorkflowData(value as MaterialData); data.value.status = 'draft'; data.value.accuracy_checked = false; data.value.scope_checked = false; data.value.layout_checked = false }
function exportText() { downloadBlob(new Blob([materialMarkdown(data.value)],{type:'text/markdown;charset=utf-8'}),'练习资料.md') }
const statuses = ['draft','review','ready','archived']
</script>
<template><XhsWorkflowFrame title="资料制作" description="按选题生成原创练习，编辑题目与讲解，复核后导出学生卷和答案卷。" create-label="新建资料" v-bind="{items,total,page,editing,busy,loading,error,notice,dirty,statuses}" :backup="w.backup" :save-disabled="!linked" save-hint="请先选择关联选题" @reset="w.resetFilters" v-model:q="q" v-model:filter="filter" @open="w.open" @back="w.back" @save="w.save" @search="w.loadList" @page="page=$event"><template #guide><div class="workflow-step">每份资料关联一个选题。可以为同一选题制作不同难度或不同版本的练习。<UButton v-permission="'xhsIdeas:create'" label="去选题库创建" variant="link" @click="navigateAdmin('xhsIdeas', {new:'1'})" /></div></template><XhsWorkflowLinks :record="record" :parent="parent" /><XhsParentPicker v-if="!linked" kind="ideas" next="materials" /><template v-else><div class="workflow-tabs"><UButton v-for="tab in [{id:'setup',label:'1 · 出题设置'},{id:'questions',label:'2 · 题目与讲解'},{id:'review',label:'3 · 复核与导出'}]" :key="tab.id" :label="tab.label" :variant="step===tab.id?'solid':'ghost'" :aria-current="step===tab.id?'step':undefined" @click="step=tab.id" /></div><UAlert v-if="generationError" :title="generationError" color="error" /><div v-if="pending" class="workflow-step workflow-actions"><span>{{ generating ? '正在生成，可稍后查询原结果。' : '有一条生成请求可查询或取回。' }}</span><UButton v-permission="'xhsMaterials:run'" label="查询并取回结果" :loading="generating" @click="recover" /><UButton label="结束此请求" color="neutral" variant="ghost" :disabled="generating" @click="generation.abandon" /></div><details v-if="generatedResult && changedSinceGeneration" class="workflow-step"><summary>查看保留的生成题目</summary><div v-for="(item,index) in generatedResult.questions" :key="index" class="workflow-exercise"><strong>第 {{ index+1 }} 题：{{ item.stem }}</strong><p v-if="item.options?.length">{{ item.options.join(" / ") }}</p><p>答案：{{ item.answer }}</p><p>{{ item.analysis }}</p></div><UButton v-permission="'xhsMaterials:' + (record ? 'update' : 'create')" label="应用这份生成题目" variant="outline" :disabled="generating || busy || dirty" @click="applyGenerated" /></details><div v-if="step==='setup'" class="workflow-card workflow-grid"><label class="workflow-field workflow-wide"><span>资料名称</span><UInput :disabled="!canPermission('xhsMaterials:' + (record ? 'update' : 'create'))" v-model="data.title" aria-label="资料名称" maxlength="120" /></label><label class="workflow-field"><span>年级</span><UInput :disabled="!canPermission('xhsMaterials:' + (record ? 'update' : 'create'))" v-model="data.grade" maxlength="20" /></label><label class="workflow-field"><span>科目</span><UInput :disabled="!canPermission('xhsMaterials:' + (record ? 'update' : 'create'))" v-model="data.subject" maxlength="20" /></label><label class="workflow-field workflow-wide"><span>知识点</span><UInput :disabled="!canPermission('xhsMaterials:' + (record ? 'update' : 'create'))" v-model="data.keyword" aria-label="出题知识点" maxlength="100" /></label><label class="workflow-field"><span>题型</span><USelect :disabled="!canPermission('xhsMaterials:' + (record ? 'update' : 'create'))" v-model="data.game_type" :items="[{value:'fill_blank',label:'填空题'},{value:'quiz',label:'选择题'},{value:'oral_math',label:'口算题'},{value:'word_problem',label:'应用题'},{value:'true_false',label:'判断题'}]" /></label><label class="workflow-field"><span>难度</span><USelect :disabled="!canPermission('xhsMaterials:' + (record ? 'update' : 'create'))" v-model="data.difficulty" :items="[{value:'easy',label:'基础'},{value:'medium',label:'进阶'},{value:'hard',label:'挑战'}]" /></label><label class="workflow-field"><span>题数（1–30）</span><UInput v-model.number="data.question_count" type="number" min="1" max="30" /></label><label class="workflow-field workflow-wide"><span>学生使用说明</span><UTextarea :disabled="!canPermission('xhsMaterials:' + (record ? 'update' : 'create'))" v-model="data.instructions" :rows="3" maxlength="2000" /></label><div class="workflow-actions workflow-wide"><UButton v-permission="'xhsMaterials:run'" :label="preparing ? '正在核实教材范围…' : '生成题目与讲解'" :loading="generationBusy" :disabled="busy || !!pending" @click="generate" /><UButton v-permission="'xhsMaterials:' + (record ? 'update' : 'create')" label="手动编写" variant="outline" @click="step='questions';if(!data.questions.length)addQuestion()" /><small class="workflow-hint">使用后台已配置的出题模型，沿用现有知识范围检查和题目质检。</small></div></div><div v-else-if="step==='questions'" class="workflow-card"><div class="workflow-actions"><h3>题目与讲解 · {{ data.questions.length }} 道</h3><UButton v-permission="'xhsMaterials:' + (record ? 'update' : 'create')" label="添加题目" size="sm" :disabled="data.questions.length>=100" @click="addQuestion" /></div><p v-if="!data.questions.length" class="workflow-hint">还没有题目，可以生成或手动添加。</p><div v-for="(item,index) in data.questions" :key="index" class="workflow-exercise workflow-grid"><div class="workflow-wide workflow-actions"><strong>第 {{ index+1 }} 题</strong><UButton v-permission="'xhsMaterials:' + (record ? 'update' : 'create')" label="删除此题" color="error" variant="ghost" size="xs" @click="data.questions.splice(index,1)" /><span v-if="item.quality_issues.length" class="text-warning">{{ item.quality_issues.join('；') }}</span></div><label class="workflow-field workflow-wide"><span>题干</span><UTextarea v-model="item.stem" :aria-label="`第${index+1}题题干`" :rows="2" maxlength="3000" /></label><label v-if="data.game_type==='quiz' || item.options.length" class="workflow-field workflow-wide"><span>选项（每行一项）</span><UTextarea :model-value="item.options.join('\n')" :rows="4" @update:model-value="item.options=String($event).split('\n').filter(Boolean)" /></label><label class="workflow-field"><span>答案</span><UTextarea v-model="item.answer" :aria-label="`第${index+1}题答案`" :rows="2" maxlength="2000" /></label><label class="workflow-field"><span>讲解</span><UTextarea v-model="item.analysis" :aria-label="`第${index+1}题讲解`" :rows="3" maxlength="4000" /></label></div></div><div v-else class="workflow-card"><h3>复核与导出</h3><p class="workflow-hint">先保存题目，再完成下面的复核。修改出题设置、题目或使用说明后，需要重新复核。</p><div class="workflow-editor mt-4"><div v-if="needsReviewSave" class="workflow-step workflow-actions"><span>请先保存当前内容，再完成复核。</span><UButton v-permission="'xhsMaterials:' + (record ? 'update' : 'create')" label="保存当前内容" :disabled="busy" @click="w.save" /></div><UCheckbox :disabled="!canPermission('xhsMaterials:' + (record ? 'update' : 'create')) || (needsReviewSave)" v-model="data.accuracy_checked" label="已逐题核对答案与讲解" /><UCheckbox :disabled="!canPermission('xhsMaterials:' + (record ? 'update' : 'create')) || (needsReviewSave)" v-model="data.scope_checked" label="已检查适用年级与知识范围" /><UCheckbox :disabled="!canPermission('xhsMaterials:' + (record ? 'update' : 'create')) || (needsReviewSave)" v-model="data.layout_checked" label="已检查导出排版与留白" /><UTextarea :disabled="!canPermission('xhsMaterials:' + (record ? 'update' : 'create'))" v-model="data.review_notes" placeholder="复核备注" maxlength="4000" /><USelect :disabled="!canPermission('xhsMaterials:' + (record ? 'update' : 'create'))" v-model="data.status" :items="[{value:'draft',label:'草稿'},{value:'review',label:'待复核'},{value:'ready',label:'已复核，可使用'},{value:'archived',label:'归档'}]" aria-label="资料状态" /><div class="workflow-actions"><XhsMaterialPreview :data="data" :session="w.editorSession.value" /><UButton v-permission="'xhsMaterials:export'" label="导出学生卷 PDF" :loading="exporting" @click="exportPdf(false)" /><UButton v-permission="'xhsMaterials:export'" label="导出答案讲解 PDF" color="neutral" variant="outline" :loading="exporting" @click="exportPdf(true)" /><UButton v-permission="'xhsMaterials:export'" label="导出可编辑文本" color="neutral" variant="ghost" @click="exportText()" /></div></div></div><div class="workflow-actions"><XhsWorkflowVersions v-if="record" :record="record" :current="data" :dirty="dirty" :disabled="busy" @restore="restore" /><UButton v-permission="'xhsMaterials:create'" v-if="record" label="复制为新版本" color="neutral" variant="outline" :disabled="busy" @click="w.duplicate" /><UButton v-if="step==='setup' && data.questions.length" label="下一步：编辑题目" variant="outline" @click="step='questions'" /><UButton v-permission="'xhsMaterials:update'" v-if="step==='questions'" label="保存并复核资料" variant="outline" :disabled="busy || !completeQuestions" @click="review" /><UButton v-permission="'xhsDrafts:create'" :label="existingDraft ? '保存并继续笔记' : '保存并制作笔记'" :disabled="busy || !completeQuestions" @click="createDraft()" /><UButton v-permission="'xhsDrafts:create'" v-if="existingDraft" label="另建一篇笔记" variant="outline" :disabled="busy || !completeQuestions" @click="createDraft(true)" /><span v-if="!completeQuestions" class="workflow-hint">请补全题干、答案和讲解，再制作笔记。</span></div></template></XhsWorkflowFrame></template>
