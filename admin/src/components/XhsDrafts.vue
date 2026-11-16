<script setup lang="ts">
import { permissionDirective as vPermission, canPermission } from '../permissions'
import XhsAssets from './XhsAssets.vue'
import { assetDefaults, saveCoverTemplate, type Asset } from '../xhs-workspace'
import XhsProfilePicker from './XhsProfilePicker.vue'
import type { AccountSnapshot } from '../xhs-accounts'
import XhsParentPicker from './XhsParentPicker.vue'
import { computed, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import type { UserInfo } from '../api'
import { adminRoute, navigateAdmin } from '../navigation'
import { cleanWorkflowData, getWorkflow, newDraft, nextWorkflow, useWorkflow, workflowError, type DraftData, type MaterialData } from '../xhs-workflow'
import { useXhsGeneration } from '../xhs-generation'
import { draftImages, draftText, exportDraft } from '../xhs-content-export'
import { downloadBlob } from '../../../shared/download'
import XhsWorkflowFrame from './XhsWorkflowFrame.vue'
import XhsWorkflowLinks from './XhsWorkflowLinks.vue'
import XhsWorkflowVersions from './XhsWorkflowVersions.vue'
const props = defineProps<{ user: UserInfo }>()
const w = useWorkflow('drafts', newDraft, (parent, data) => {
  if (!parent) return
  const material = parent.data as MaterialData
  data.title = `${material.title} · 笔记`.slice(0,120); data.headline = material.title.slice(0,20); data.cover_title = material.title.slice(0,40)
  data.cover_subtitle = `${material.grade} · ${material.subject} · ${material.questions.length} 道练习`
}, props.user.id)
const { items,total,page,q,filter,record,data,parent,editing,busy,loading,error,notice,dirty } = w
const templateLibrary = ref(false)
const step = ref('copy'), exporting = ref(false), previewing = ref(false), applying = ref(false), refreshingSource = ref(false), preparing = ref(false), preview = ref<string[]>([])
interface GeneratedCopy { draft: DraftData; request_id: string; material_id: string; material_revision: number }
const generation = useXhsGeneration<GeneratedCopy>(props.user.id, () => record.value?.id || '', 'copy')
const { busy: generating, error: generationError, pending, result: generatedResult } = generation
const generationBusy = computed(() => preparing.value || generating.value || applying.value)
const material = computed(() => parent.value?.data as MaterialData | undefined)
const sourceQuestions = computed(() => material.value?.questions?.slice(0, 3) || [])
const exportReady = computed(() => !!data.value.headline.trim() && !!data.value.body.trim())
const changedSinceGeneration = computed(() => !!pending.value && !generation.matches(record.value?.revision || 0, data.value))
const sourceRevision = computed(() => data.value.source_material_revision || 0)
const sourceOutdated = computed(() => !!parent.value && sourceRevision.value > 0 && sourceRevision.value !== parent.value.revision)
const generatedSourceChanged = computed(() => !!generatedResult.value && !!parent.value &&
  (generatedResult.value.material_id !== parent.value.id || generatedResult.value.material_revision !== parent.value.revision))
const needsGeneratedReview = computed(() => changedSinceGeneration.value || generatedSourceChanged.value)
let previewSequence = 0
let preparationSequence = 0
function stopPreparing() { preparationSequence++; preparing.value = false }
const imageFingerprint = computed(() => JSON.stringify([data.value.headline, data.value.cover_title, data.value.cover_subtitle, data.value.theme, data.value.cards]))
function clearPreview() { previewSequence++; preview.value = []; previewing.value = false }
watch(imageFingerprint, clearPreview, { flush: 'sync' })
watch(w.editorSession, () => { step.value = 'copy'; templateLibrary.value = false; clearPreview(); stopPreparing() }, { flush: 'sync' })
function deactivate() { clearPreview(); stopPreparing() }
onDeactivated(deactivate); onBeforeUnmount(deactivate)
async function refreshSource() {
  if (!parent.value || refreshingSource.value) return
  const id = parent.value.id, session = w.editorSession.value
  refreshingSource.value = true
  try { const current = await getWorkflow<MaterialData>('materials', id); if (session === w.editorSession.value && parent.value?.id === id) parent.value = current }
  catch (cause) { if (session === w.editorSession.value) error.value = workflowError(cause) }
  finally { refreshingSource.value = false }
}
async function accept(result: GeneratedCopy | null, target: string, explicit = false) {
  if (!result || record.value?.id !== target || applying.value || adminRoute.tab !== 'xhsDrafts') return
  const session = w.editorSession.value, parentId = parent.value?.id
  applying.value = true
  try {
    if (!parentId || (result.material_id && result.material_id !== parentId)) { error.value = '生成文案的来源与当前关联资料不同，请结束原请求后重新生成。'; return }
    const current = await getWorkflow<MaterialData>('materials', parentId)
    if (record.value?.id !== target || session !== w.editorSession.value || adminRoute.tab !== 'xhsDrafts') return
    parent.value = current
    if (dirty.value) { error.value='文案结果已保留。当前有未保存编辑，请保存后再查询取回。';return }
    if (needsGeneratedReview.value) {
      if (!explicit) { notice.value = generatedSourceChanged.value ? '关联资料已变化或原结果缺少来源版本，文案已保留。请展开查看并核对后再应用。' : '生成期间笔记已有修改，结果已保留。请展开查看生成文案，核对后再应用。'; return }
      if (!window.confirm('应用这份生成文案会替换当前已保存的标题、正文、话题和配图文字。请核对文案与当前资料是否相符；现有内容仍保留在历史版本中，是否继续？')) return
    }
    const { headline, title_options, body, hashtags, cover_title, cover_subtitle, cards } = result.draft
    data.value = { ...data.value, headline, title_options, body, hashtags, cover_title, cover_subtitle, cards,
      status: 'draft', generation_request_id: result.request_id, source_material_revision: result.material_revision || 0 }
    if (await w.save()) { generation.finish(); notice.value = '文案草稿已保存，可以选择标题并调整配图。' }
  } catch (cause) {
    if (session === w.editorSession.value) error.value = workflowError(cause)
  } finally { applying.value = false }
}
function applyProfile(profile: AccountSnapshot) { data.value.account_profile = profile; data.value.audience = profile.audience || '家长'; data.value.angle = profile.direction; if (profile.topics) data.value.hashtags = profile.topics; notice.value = '已应用账号定位；生成文案时会带入保存的档案。' }
async function generate() {
  if (!parent.value || generationBusy.value || pending.value || busy.value || loading.value) return
  const key = ++preparationSequence, session = w.editorSession.value, fingerprint = JSON.stringify(data.value), parentId = parent.value.id
  const current = () => key === preparationSequence && session === w.editorSession.value && adminRoute.tab === 'xhsDrafts'
  preparing.value = true; error.value = ''
  try {
    const source = await getWorkflow<MaterialData>('materials', parentId)
    if (!current()) return
    if (fingerprint !== JSON.stringify(data.value)) { error.value = '笔记内容已修改，请重新点击生成。'; return }
    parent.value = source
    if (!source.data.questions?.length) { error.value = '关联资料还没有题目，请先制作资料再生成文案。'; return }
    if (!(await w.save()) || !current()) return
    const target = record.value!.id, value = cleanWorkflowData(data.value)
    preparing.value = false
    await accept(await generation.generate('/api/v1/admin/xhs-workflow/generate-copy', { material_id: source.id, material_revision: source.revision, audience: value.audience, angle: value.angle, account_profile: value.account_profile }, record.value!.revision, value), target)
  } catch (cause) { if (current()) error.value = workflowError(cause) }
  finally { if (key === preparationSequence) preparing.value = false }
}
async function recover() { if (dirty.value) { error.value='请先保存当前编辑，再取回生成文案。';return };const target=record.value?.id || '';await accept(await generation.recover(),target) }
async function applyGenerated() { await accept(generatedResult.value, record.value?.id || '', true) }
async function saveTemplate() {
  if (exporting.value) return
  const value = cleanWorkflowData(data.value), session = w.editorSession.value
  exporting.value = true; error.value = ''
  try { const result = await saveCoverTemplate({ ...assetDefaults(), title: (value.title || '封面') + ' · 模板' }, { theme: value.theme, cover_title: value.cover_title, cover_subtitle: value.cover_subtitle, cards: value.cards }); if (session === w.editorSession.value) notice.value = result.duplicate ? '模板已在素材库中，核实来源后即可复用。' : '封面与内页已保存到素材库，请在素材库补充来源信息后复用。' }
  catch (cause) { if (session === w.editorSession.value) error.value = workflowError(cause) } finally { exporting.value = false }
}
function applyTemplate(assets: Asset[]) {
  const template = assets[0]?.template
  if (!template || !window.confirm('使用此模板替换当前封面和内页？正文和发布标题会保留，保存前可放弃修改。')) return
  Object.assign(data.value, JSON.parse(JSON.stringify(template))); preview.value = []; templateLibrary.value = false
}
async function previewImages() {
  if (previewing.value) return
  const key = ++previewSequence, session = w.editorSession.value, fingerprint = imageFingerprint.value, value = cleanWorkflowData(data.value)
  previewing.value = true; error.value = ''
  try {
    const images = await draftImages(value)
    const urls = await Promise.all(images.map(blob => new Promise<string>((resolve,reject) => { const reader = new FileReader(); reader.onload=()=>resolve(String(reader.result));reader.onerror=reject;reader.readAsDataURL(blob) })))
    if (key === previewSequence && session === w.editorSession.value && fingerprint === imageFingerprint.value && adminRoute.tab === 'xhsDrafts') preview.value = urls
  } catch (cause) { if (key === previewSequence) error.value = workflowError(cause) }
  finally { if (key === previewSequence) previewing.value = false }
}
async function exportBundle() { if (exporting.value) return; const value = cleanWorkflowData(data.value), session = w.editorSession.value; exporting.value=true;error.value='';try { await exportDraft(value); if (session === w.editorSession.value) notice.value='已导出文案和全部 PNG 配图' } catch(cause){if (session === w.editorSession.value) error.value=workflowError(cause)} finally{exporting.value=false} }
async function copyText() {
  if (!exportReady.value) { error.value = '请先补全发布标题和正文，再复制文案。'; return }
  const text = draftText(cleanWorkflowData(data.value)), session = w.editorSession.value
  const current = () => session === w.editorSession.value && adminRoute.tab === 'xhsDrafts'
  try { await navigator.clipboard.writeText(text); if (current()) notice.value = '文案已复制' }
  catch { downloadBlob(new Blob([text], {type:'text/plain;charset=utf-8'}),'笔记文案.txt'); if (current()) notice.value = '浏览器无法复制，已下载文案文件。' }
}
async function plan() { if (await w.save()) nextWorkflow('publications',record.value!.id) }
function restore(value: object) { data.value=cleanWorkflowData(value as DraftData);data.value.status='draft';preview.value=[] }
const statuses=['draft','review','ready','archived']
</script>
<template><XhsWorkflowFrame title="笔记制作" description="围绕已有资料准备标题、正文、封面与内页，保存版本并导出发布素材。" create-label="新建笔记" v-bind="{items,total,page,editing,busy,loading,error,notice,dirty,statuses}" :backup="w.backup" :busy="busy || applying" :save-disabled="!parent" save-hint="请先选择关联资料" @reset="w.resetFilters" v-model:q="q" v-model:filter="filter" @open="w.open" @back="w.back" @save="w.save" @search="w.loadList" @page="page=$event"><template #guide><div class="workflow-step">从资料制作页点击“保存并制作笔记”，已做好的练习会自动关联到文案。<UButton v-permission="'xhsMaterials:view'" label="打开资料制作" variant="link" @click="navigateAdmin('xhsMaterials', {})" /></div></template><XhsWorkflowLinks :record="record" :parent="parent" /><XhsParentPicker v-if="!parent" kind="materials" next="drafts" /><template v-else><div class="workflow-step workflow-actions"><span>关联资料当前为第 {{ parent.revision }} 版<span v-if="sourceRevision">；文案来源为第 {{ sourceRevision }} 版</span>。</span><UButton label="刷新关联资料" variant="link" :loading="refreshingSource" :disabled="busy || generationBusy" @click="refreshSource" /></div><UAlert v-if="sourceOutdated" title="关联资料已有更新，当前文案仍基于旧版本。请核对题目与描述，或根据最新资料重新生成文案。" color="warning" /><p v-else-if="data.generation_request_id && !sourceRevision" class="workflow-hint">这份历史文案未记录资料版本，请核对后再使用。</p><details class="workflow-step workflow-source">
  <summary>查看当前关联资料 · {{ material?.questions?.length || 0 }} 道题</summary>
  <p>{{ material?.grade }} · {{ material?.subject }} · {{ material?.keyword }}</p>
  <p v-if="material?.instructions">使用说明：{{ material.instructions }}</p>
  <div v-for="(question,index) in sourceQuestions" :key="index" class="workflow-source-question">
    <strong>第 {{ index+1 }} 题：{{ question.stem.slice(0,300) || '题干待补全' }}</strong>
    <p v-if="question.options.length">{{ question.options.map((option,i)=>`${String.fromCharCode(65+i)}. ${option}`).join(' / ') }}</p>
    <p>答案：{{ question.answer.slice(0,300) || '待补全' }}</p>
    <p>讲解：{{ question.analysis.slice(0,300) || '待补全' }}</p>
  </div>
  <p v-if="!sourceQuestions.length">资料还没有题目，请先制作资料。</p>
  <p v-else-if="(material?.questions?.length || 0)>3" class="workflow-hint">这里展示前三题，完整内容请打开资料查看。</p>
  <UButton v-permission="'xhsMaterials:view'" label="打开资料完整内容" variant="link" @click="navigateAdmin('xhsMaterials',{id:parent.id})" />
</details><div class="workflow-tabs"><UButton v-for="tab in [{id:'copy',label:'1 · 标题与正文'},{id:'design',label:'2 · 封面与内页'},{id:'preview',label:'3 · 预览与导出'}]" :key="tab.id" :label="tab.label" :variant="step===tab.id?'solid':'ghost'" :aria-current="step===tab.id?'step':undefined" @click="step=tab.id" /></div><UAlert v-if="generationError" :title="generationError" color="error" /><div v-if="pending" class="workflow-step workflow-actions"><span>已有文案生成请求</span><UButton v-permission="'xhsDrafts:run'" label="查询并取回文案" :loading="generating" @click="recover" /><UButton label="结束此请求" color="neutral" variant="ghost" :disabled="generating" @click="generation.abandon" /></div><details v-if="generatedResult && needsGeneratedReview" class="workflow-step"><summary>查看保留的生成文案</summary><p v-if="generatedSourceChanged" class="workflow-hint">生成结果的资料版本与当前资料不同或未记录，请先核对内容。</p><h3>{{ generatedResult.draft.headline }}</h3><div class="workflow-preview">{{ generatedResult.draft.body }}</div><p>{{ generatedResult.draft.hashtags }}</p><UButton v-permission="'xhsDrafts:' + (record ? 'update' : 'create')" label="应用这份生成文案" variant="outline" :disabled="generating || busy || applying || dirty" @click="applyGenerated" /></details><div v-if="step==='copy'" class="workflow-card workflow-grid"><label class="workflow-field workflow-wide"><span>内部名称</span><UInput :disabled="!canPermission('xhsDrafts:' + (record ? 'update' : 'create'))" v-model="data.title" aria-label="笔记内部名称" maxlength="120" /></label><XhsProfilePicker :current="data.account_profile" :disabled="generating || busy" @apply="applyProfile" /><label class="workflow-field"><span>目标读者</span><UInput :disabled="!canPermission('xhsDrafts:' + (record ? 'update' : 'create'))" v-model="data.audience" maxlength="200" /></label><label class="workflow-field"><span>写作切入点</span><UInput :disabled="!canPermission('xhsDrafts:' + (record ? 'update' : 'create'))" v-model="data.angle" maxlength="2000" placeholder="例如：给家长一套由易到难的练习方法" /></label><div class="workflow-wide workflow-actions"><UButton v-permission="'xhsDrafts:run'" :label="preparing ? '正在读取最新资料…' : '根据资料生成文案'" :loading="generationBusy" :disabled="busy || applying || !!pending" @click="generate" /><span class="workflow-hint">生成后仍可逐项修改，也可以完全手写。</span></div><label class="workflow-field workflow-wide"><span>发布标题 · {{ data.headline.length }}/20</span><UInput :disabled="!canPermission('xhsDrafts:' + (record ? 'update' : 'create'))" v-model="data.headline" aria-label="发布标题" maxlength="20" /></label><div v-if="data.title_options.length" class="workflow-actions workflow-wide"><UButton v-permission="'xhsDrafts:' + (record ? 'update' : 'create')" v-for="(title,index) in data.title_options" :key="index" :label="title" size="sm" variant="outline" @click="data.headline=title.slice(0,20)" /></div><label class="workflow-field workflow-wide"><span>正文 · {{ data.body.length }} 字</span><UTextarea :disabled="!canPermission('xhsDrafts:' + (record ? 'update' : 'create'))" v-model="data.body" aria-label="笔记正文" :rows="12" maxlength="2000" /></label><label class="workflow-field workflow-wide"><span>话题</span><UInput :disabled="!canPermission('xhsDrafts:' + (record ? 'update' : 'create'))" v-model="data.hashtags" maxlength="300" placeholder="#一年级数学 #学习资料" /></label></div><div v-else-if="step==='design'" class="workflow-editor"><div class="workflow-actions"><UButton v-permission="'xhsAssets:view'" label="从素材库选模板" variant="outline" @click="templateLibrary=true" /><UButton v-permission="'xhsAssets:create'" label="保存为封面模板" variant="outline" :loading="exporting" @click="saveTemplate" /></div><div class="workflow-card workflow-grid"><label class="workflow-field"><span>封面主标题</span><UTextarea :disabled="!canPermission('xhsDrafts:' + (record ? 'update' : 'create'))" v-model="data.cover_title" aria-label="封面主标题" :rows="2" maxlength="40" /></label><label class="workflow-field"><span>封面副标题</span><UTextarea :disabled="!canPermission('xhsDrafts:' + (record ? 'update' : 'create'))" v-model="data.cover_subtitle" :rows="2" maxlength="120" /></label><label class="workflow-field"><span>配色</span><USelect :disabled="!canPermission('xhsDrafts:' + (record ? 'update' : 'create'))" v-model="data.theme" :items="[{value:'green',label:'清新绿'},{value:'orange',label:'暖橙'},{value:'blue',label:'学习蓝'}]" /></label><div class="workflow-field"><span>规格</span><p class="workflow-hint">3:4 竖版 · 1080 × 1440 PNG · 最多 9 张</p></div></div><div class="workflow-card"><div class="workflow-actions"><h3>内页内容</h3><UButton v-permission="'xhsDrafts:' + (record ? 'update' : 'create')" label="添加内页" size="sm" :disabled="data.cards.length>=8" @click="data.cards.push({heading:'',body:''})" /></div><div v-for="(card,index) in data.cards" :key="index" class="workflow-exercise workflow-grid"><label class="workflow-field workflow-wide"><span>第 {{ index+1 }} 张内页标题</span><UInput v-model="card.heading" :aria-label="`内页${index+1}标题`" maxlength="80" /></label><label class="workflow-field workflow-wide"><span>内页文字</span><UTextarea v-model="card.body" :rows="5" maxlength="800" /></label><div class="workflow-actions"><UButton v-permission="'xhsDrafts:' + (record ? 'update' : 'create')" label="上移" size="xs" variant="ghost" :disabled="index===0" @click="data.cards.splice(index-1,0,data.cards.splice(index,1)[0]!)" /><UButton v-permission="'xhsDrafts:' + (record ? 'update' : 'create')" label="下移" size="xs" variant="ghost" :disabled="index===data.cards.length-1" @click="data.cards.splice(index+1,0,data.cards.splice(index,1)[0]!)" /><UButton v-permission="'xhsDrafts:' + (record ? 'update' : 'create')" label="删除内页" size="xs" color="error" variant="ghost" @click="data.cards.splice(index,1)" /></div></div></div></div><div v-else class="workflow-editor"><div class="workflow-card"><h3>{{ data.headline || '未填写发布标题' }}</h3><div class="workflow-preview">{{ data.body }}

{{ data.hashtags }}</div><div class="workflow-actions mt-4"><UButton label="预览全部配图" :loading="previewing" @click="previewImages" /><UButton v-permission="'xhsDrafts:export'" label="复制文案" variant="outline" :disabled="!exportReady" @click="copyText" /><UButton v-permission="'xhsDrafts:export'" label="导出文案与配图 ZIP" :loading="exporting" :disabled="!exportReady" @click="exportBundle" /></div><p v-if="!exportReady" class="workflow-hint">请补全发布标题和正文后再导出发布素材；也可以先预览配图。</p><p v-if="!preview.length && !previewing" class="workflow-hint">点击“预览全部配图”查看当前封面与内页；修改配图后需重新预览。</p><div class="workflow-image-grid"><img v-for="(url,index) in preview" :key="index" :src="url" :alt="index===0?'封面预览':`内页${index}预览`" /></div></div><div class="workflow-card workflow-grid"><label class="workflow-field"><span>笔记状态</span><USelect :disabled="!canPermission('xhsDrafts:' + (record ? 'update' : 'create'))" v-model="data.status" :items="[{value:'draft',label:'草稿'},{value:'review',label:'待检查'},{value:'ready',label:'可发布'},{value:'archived',label:'归档'}]" /></label><label class="workflow-field workflow-wide"><span>检查备注</span><UTextarea :disabled="!canPermission('xhsDrafts:' + (record ? 'update' : 'create'))" v-model="data.notes" :rows="3" maxlength="4000" placeholder="检查资料描述、标题、错别字和配图顺序" /></label></div></div><div class="workflow-actions"><XhsWorkflowVersions v-if="record" :record="record" :current="data" :dirty="dirty" :disabled="busy" @restore="restore" /><UButton v-permission="'xhsDrafts:create'" v-if="record" label="复制为新方案" color="neutral" variant="outline" :disabled="busy" @click="w.duplicate" /><UButton v-if="step==='copy'" label="下一步：封面与内页" variant="outline" @click="step='design'" /><UButton v-if="step==='design'" label="下一步：预览与导出" variant="outline" @click="step='preview'" /><UButton v-permission="'xhsPublishing:create'" label="保存并安排发布" :disabled="busy || !data.headline || !data.body" @click="plan" /></div></template><UModal v-model:open="templateLibrary" title="从素材库选模板" :ui="{content:'max-w-5xl'}"><template #body><XhsAssets v-if="templateLibrary" picker="template" @choose="applyTemplate" /></template></UModal></XhsWorkflowFrame></template>
<style scoped>.workflow-source summary{cursor:pointer;font-weight:600}.workflow-source-question{border-top:1px solid #dce8e0;padding-top:12px;margin-top:12px;white-space:pre-wrap;overflow-wrap:anywhere}.workflow-image-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,260px));gap:14px;margin-top:20px}.workflow-image-grid img{width:100%;border-radius:10px;border:1px solid #dce8e0}</style>
