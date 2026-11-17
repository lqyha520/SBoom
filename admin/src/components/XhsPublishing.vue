<script setup lang="ts">
import { permissionDirective as vPermission, canPermission, canAdmin } from '../permissions'
import { computed, ref, watch } from 'vue'
import type { UserInfo } from '../api'
import { adminRoute, navigateAdmin } from '../navigation'
import { downloadBlob } from '../../../shared/download'
import { exportDraft } from '../xhs-content-export'
import { checkPublication, publicationChecks, refreshPublicationDraft, type PublicationCheckResult } from '../xhs-publication'
import { dateTimeLocal, isoDateTime, newPublication, useWorkflow, workflowError, type DraftData } from '../xhs-workflow'
import XhsPublicationCalendar from './XhsPublicationCalendar.vue'
import XhsPublicationAccount from './XhsPublicationAccount.vue'
import XhsParentPicker from './XhsParentPicker.vue'
import XhsWorkflowFrame from './XhsWorkflowFrame.vue'
import XhsWorkflowLinks from './XhsWorkflowLinks.vue'
import XhsWorkflowVersions from './XhsWorkflowVersions.vue'
import XhsPublishAssist from './XhsPublishAssist.vue'
import XhsPublicationMedia from './XhsPublicationMedia.vue'
import type { PublicationMedia } from '../xhs-media-cache'
import type { AssistMedia } from '../xhs-publish-assist'

const props = defineProps<{ user: UserInfo }>()
const w = useWorkflow('publications', newPublication, (parent, data) => {
  if (parent) { const draft = parent.data as DraftData; data.source = 'linked'; data.title = draft.headline || draft.title; data.account_id = draft.account_profile?.id || ''; data.account = draft.account_profile?.name || '' }
}, props.user.id)
const { items,total,page,q,filter,record,data,parent,editing,busy,loading,error,notice,dirty } = w
const statuses = ['planned','ready','published','archived']
const view = ref('list')
const media = ref<AssistMedia[]>([]), mediaEditor = ref<InstanceType<typeof XhsPublicationMedia> | null>(null)
const mediaReady = ref(true)
const publishMethod = ref('manual')
const step = ref('content'), checking = ref(false), exporting = ref(false)
const assessment = ref<PublicationCheckResult | null>(null)
const snapshot = computed(() => record.value?.data.draft_snapshot || (parent.value?.data as DraftData | undefined))
const content = computed(() => data.value.source === 'custom' ? data.value.custom_content : snapshot.value)
const text = computed(() => [content.value?.headline, content.value?.body, content.value?.hashtags].filter(Boolean).join('\n\n'))
const linkedMissing = computed(() => data.value.source === 'linked' && !parent.value)
const isPublished = computed(() => record.value?.status === 'published' || !!record.value?.data.published_at)
const statusesForEdit = computed(() => isPublished.value ? [{ value:'published',label:'已发布' },{ value:'archived',label:'归档' }] : [{ value:'planned',label:'准备中' },{ value:'ready',label:'已复核，待手动发布' },{ value:'published',label:'已发布' },{ value:'archived',label:'归档' }])
watch(() => record.value?.id, () => { step.value = 'content'; assessment.value = null; publishMethod.value = 'manual' })
watch(() => JSON.stringify(data.value), () => { assessment.value = null })

function chooseSource(source: 'linked' | 'custom') {
  if (record.value || source === data.value.source) return
  if (dirty.value && !window.confirm('切换来源会清空当前未保存的内容，是否继续？')) return
  if (parent.value) { navigateAdmin('xhsPublishing', { new:'1' }); return }
  data.value = { ...newPublication(), source }
}
async function inspectContent() {
  if (checking.value) return null
  if (!mediaReady.value) { error.value = '请先恢复配图，或移除缺失项后重新选择。'; return null }
  checking.value = true; error.value = ''
  const signature = JSON.stringify(data.value), id = record.value?.id
  try {
    const result = await checkPublication(data.value, id, parent.value?.id)
    if (record.value?.id !== id || JSON.stringify(data.value) !== signature || adminRoute.tab !== 'xhsPublishing') return null
    assessment.value = result; return result
  } catch (cause) { error.value = workflowError(cause); return null }
  finally { checking.value = false }
}
async function save() {
  if (!data.value.title.trim()) data.value.title = content.value?.headline || '图文发布草稿'
  return w.save()
}
function mediaChanged(references: PublicationMedia[]) {
  data.value.media = references
  data.value.media_checked = false
  if (data.value.status === 'ready') data.value.status = 'planned'
  data.value.custom_content.media_notes = media.value.map((item, i) => `${i + 1}. ${item.file.name}`).join('\n').slice(0, 2000)
}
async function goCheck() { if (await save()) { step.value = 'check'; await inspectContent() } }
async function markReady() {
  if (!(await save())) return
  const result = await inspectContent()
  if (!result || result.blockers.length) return
  data.value.status = 'ready'
  if (await save()) { step.value = 'publish'; notice.value = '图片和文案已准备好。选择下面的发布方式，最后在小红书点击“发布”。' }
}
async function refreshSource() {
  if (!(await w.save()) || !record.value) return
  const id = record.value.id
  busy.value = true
  try {
    await refreshPublicationDraft(id, record.value.revision)
    if (record.value?.id !== id || adminRoute.tab !== 'xhsPublishing') return
    await w.readRoute(true); notice.value = '已更新笔记版本，请重新完成发布前检查。'
  } catch (cause) { error.value = workflowError(cause) }
  finally { busy.value = false }
}
async function copyText() {
  try { await navigator.clipboard.writeText(text.value); notice.value = '发布文案已复制，请在小红书核对后使用。' }
  catch { downloadBlob(new Blob([text.value], {type:'text/plain;charset=utf-8'}), '发布文案.txt') }
}
async function copyPart(part: 'headline' | 'body') {
  const value = part === 'headline' ? content.value?.headline || '' : [content.value?.body, content.value?.hashtags].filter(Boolean).join('\n\n')
  try { await navigator.clipboard.writeText(value); notice.value = part === 'headline' ? '标题已复制，粘贴到小红书的标题框。' : '正文和话题已复制，粘贴到小红书的正文框。' }
  catch { downloadBlob(new Blob([value], { type: 'text/plain;charset=utf-8' }), part === 'headline' ? '发布标题.txt' : '发布正文.txt') }
}
function exportChecklist() {
  const details = [data.value.title, '发布账号：' + data.value.account,
    '计划时间：' + (data.value.scheduled_at ? new Date(data.value.scheduled_at).toLocaleString('zh-CN') : '未设置'),
    '', text.value, '', '图片/视频备注：' + (data.value.source === 'custom' ? data.value.custom_content.media_notes : '使用关联笔记的封面与内页'),
    '', '发布前检查', ...publicationChecks.map(item => (data.value[item.key] ? '[已确认] ' : '[待检查] ') + item.label),
    '', '复核说明：' + data.value.review_notes, '', '本地复核不等于平台审核。请在官方客户端或创作服务平台最终确认，实际发布后回填链接和时间。'].join('\n')
  downloadBlob(new Blob([details],{type:'text/plain;charset=utf-8'}),'发布文案与清单.txt')
}
async function exportImages() {
  if (!snapshot.value) return
  exporting.value = true; error.value = ''
  try { await exportDraft(snapshot.value) } catch (cause) { error.value = workflowError(cause) }
  finally { exporting.value = false }
}
async function review() { if (await save()) navigateAdmin('xhsAnalytics',{id:record.value!.id}) }
async function registerPublished() {
  if (!data.value.url.trim()) { error.value = '请先粘贴发布成功后的笔记链接，再登记为已发布。'; return }
  const previous = data.value.status
  const previousTime = data.value.published_at
  data.value.status = 'published'
  if (!data.value.published_at) data.value.published_at = new Date().toISOString()
  if (!(await save())) { data.value.status = previous; data.value.published_at = previousTime }
}
</script>

<template>
  <XhsWorkflowFrame title="发图文与发布记录" description="选图片、写文案，再去小红书确认发布。" create-label="发一篇图文" v-bind="{items,total,page,editing,busy,loading,error,notice,dirty,statuses}" :backup="w.backup" @reset="w.resetFilters" v-model:q="q" v-model:filter="filter" @open="w.open" @back="w.back" @save="save" @search="w.loadList" @page="page=$event">
    <template #list-tools><div class="workflow-tabs"><UButton label="发布列表" :variant="view==='list'?'solid':'ghost'" @click="view='list'" /><UButton label="发布日历" :variant="view==='calendar'?'solid':'ghost'" @click="view='calendar'" /></div></template><template v-if="view==='calendar'" #list><XhsPublicationCalendar /></template><template #guide><div class="workflow-step quick-publish-intro"><div><strong>已经有图片？直接发一篇图文</strong><p>① 选图片、写标题正文　② 看预览、确认内容　③ 去小红书发布</p><p class="workflow-hint">可以直接开始；发布成功后再登记链接。排期仅作提醒。</p></div><UButton v-permission="'xhsPublishing:create'" label="开始发图文" icon="i-lucide-image-plus" @click="w.open()" /></div></template>
    <div class="publication-layout"><XhsWorkflowLinks :record="record" :parent="parent" />
    <details v-if="linkedMissing" open class="workflow-card"><summary>使用工作台制作的笔记</summary><div class="workflow-actions mt-3" aria-label="发布内容来源">
      <UButton v-permission="'xhsPublishing:' + (record ? 'update' : 'create')" label="自定义内容" :variant="data.source==='custom'?'solid':'outline'" :disabled="!!record" @click="chooseSource('custom')" />
      <UButton v-permission="'xhsPublishing:' + (record ? 'update' : 'create')" label="关联已有笔记" :variant="data.source==='linked'?'solid':'outline'" :disabled="!!record" @click="chooseSource('linked')" />
      <span class="workflow-hint">{{ record ? '内容来源已固定，可复制为新计划。' : '自定义内容可直接准备文字和图片／视频说明。' }}</span>
    </div></details>
    <XhsParentPicker v-if="linkedMissing" kind="drafts" next="publications" />
    <template v-else>
      <div class="workflow-tabs">
        <UButton label="1 · 选图片、写文案" :variant="step==='content'?'solid':'ghost'" @click="step='content'" />
        <UButton label="2 · 预览确认" :variant="step==='check'?'solid':'ghost'" @click="goCheck" />
        <UButton label="3 · 去小红书发布" :variant="step==='publish'?'solid':'ghost'" @click="step='publish'" />
      </div>
      <XhsPublicationMedia v-show="step==='content'" ref="mediaEditor" v-model="media" :owner="user.id" :references="data.media" @availability="mediaReady=$event" :draft="data.source==='linked' ? snapshot : undefined" :disabled="busy || isPublished || data.status==='archived'" @change="mediaChanged" />
      <template v-if="step==='content'">
        <div class="workflow-card workflow-grid">
          <XhsPublicationAccount :current="{id:data.account_id || '',name:data.account}" :disabled="busy || isPublished" @apply="value=>{data.account_id=value.id;data.account=value.name}" />
          <template v-if="data.source==='custom'">
            <label class="workflow-field workflow-wide"><span>发布标题 · {{ data.custom_content.headline.length }}/20</span><UInput :disabled="!canPermission('xhsPublishing:' + (record ? 'update' : 'create'))" v-model="data.custom_content.headline" aria-label="自定义发布标题" maxlength="20" placeholder="写一个让读者看懂的标题" /></label>
            <label class="workflow-field workflow-wide"><span>发布正文 · {{ data.custom_content.body.length }} 字</span><UTextarea :disabled="!canPermission('xhsPublishing:' + (record ? 'update' : 'create'))" v-model="data.custom_content.body" aria-label="自定义发布正文" :rows="7" maxlength="2000" placeholder="介绍图片里的内容，写下你的经验或说明" /></label>
            <label class="workflow-field workflow-wide"><span>话题</span><UInput :disabled="!canPermission('xhsPublishing:' + (record ? 'update' : 'create'))" v-model="data.custom_content.hashtags" aria-label="自定义发布话题" maxlength="300" placeholder="#学习方法 #数学练习" /></label>
          </template>
        </div>
        <details class="workflow-card"><summary>更多设置：排期、账号关联和备注（选填）</summary><div class="workflow-grid mt-4">
          <div v-if="!record" class="workflow-actions workflow-wide" aria-label="发布内容来源"><UButton v-permission="'xhsPublishing:' + (record ? 'update' : 'create')" label="自定义内容" :variant="data.source==='custom'?'solid':'outline'" @click="chooseSource('custom')" /><UButton v-permission="'xhsPublishing:' + (record ? 'update' : 'create')" label="关联已有笔记" :variant="data.source==='linked'?'solid':'outline'" @click="chooseSource('linked')" /></div>
          <label class="workflow-field workflow-wide"><span>发布记录名称</span><UInput :disabled="!canPermission('xhsPublishing:' + (record ? 'update' : 'create'))" v-model="data.title" aria-label="发布记录名称" maxlength="120" placeholder="留空会自动使用发布标题" /></label>
          <label class="workflow-field"><span>计划发布时间（仅提醒）</span><input class="workflow-native" type="datetime-local" aria-label="计划发布时间" :value="dateTimeLocal(data.scheduled_at)" @input="data.scheduled_at=isoDateTime(($event.target as HTMLInputElement).value)" /></label>
          <label class="workflow-field workflow-wide"><span>图片／视频说明</span><UTextarea :disabled="!canPermission('xhsPublishing:' + (record ? 'update' : 'create'))" v-model="data.custom_content.media_notes" aria-label="图片或视频说明" :rows="3" maxlength="2000" placeholder="选择图片后自动记录文件名和顺序，可补充来源说明" /></label>
          <label class="workflow-field workflow-wide"><span>发布备注</span><UTextarea :disabled="!canPermission('xhsPublishing:' + (record ? 'update' : 'create'))" v-model="data.notes" :rows="3" maxlength="4000" placeholder="内部备注，选填" /></label>
        </div></details>
        <div v-if="data.source==='linked' && snapshot" class="workflow-card">
          <h3>关联发布素材 · 第 {{ record?.data.draft_revision || parent?.revision }} 版</h3>
          <p class="workflow-hint">发布记录使用这里保存的版本。修改来源笔记后，需要更新版本并重新复核。</p>
          <div class="workflow-preview">{{ text }}</div>
          <div class="workflow-actions mt-4">
            <UButton v-permission="'xhsDrafts:view'" label="打开关联笔记" variant="outline" @click="navigateAdmin('xhsDrafts',{id:parent!.id})" />
            <UButton v-permission="'xhsPublishing:update'" v-if="record && !isPublished && data.status!=='archived' && parent?.revision!==record.data.draft_revision" label="更新为最新笔记版本" variant="outline" @click="refreshSource" />
          </div>
        </div>
        <div class="workflow-actions"><UButton label="下一步：预览确认" :disabled="busy" @click="goCheck" /><UButton v-permission="'xhsPublishing:' + (record ? 'update' : 'create')" label="先保存草稿" variant="outline" :disabled="busy" @click="save" /></div>
      </template>
      <template v-else-if="step==='check'">
        <div class="workflow-card"><h3>这篇图文的预览</h3><p class="workflow-hint">发布账号：{{ data.account || '尚未填写，请返回第一步填写昵称' }} · {{ media.length ? '已选 '+media.length+' 个文件，第一张为封面' : '图片未在本页选择，可返回第一步选择或在小红书自行上传' }}</p><div class="review-images"><img v-for="(item,i) in media.filter(item=>item.file.type!=='video/mp4')" :key="item.url" :src="item.url" :alt="'图文预览 '+(i+1)" /></div><div class="workflow-preview mt-3">{{ text || '尚未填写文案' }}</div><UButton label="返回修改图片和文案" variant="link" @click="step='content'" /></div>
        <div class="workflow-card">
          <h3>逐项人工复核</h3>
          <p class="workflow-hint">修改文案或发布账号后，复核会重置。先保存内容，再完成检查。商业合作、AI 生成内容等按平台当前要求处理标识。</p>
          <div class="workflow-editor mt-4"><UCheckbox v-for="item in publicationChecks" :key="item.key" v-model="data[item.key]" :label="item.label" /></div>
          <label class="workflow-field mt-4"><span>风险复核说明</span><UTextarea :disabled="!canPermission('xhsPublishing:' + (record ? 'update' : 'create'))" v-model="data.review_notes" aria-label="风险复核说明" :rows="3" maxlength="4000" placeholder="有文字提醒时，记录修改内容或核实依据。不要仅替换谐音、符号来规避审核。" /></label>
          <div class="workflow-actions mt-4"><UButton v-permission="'xhsPublishing:update'" label="确认好了，去发布" :disabled="busy || checking || isPublished || data.status==='archived'" @click="markReady" /><UButton label="重新检查文字" variant="outline" :loading="checking" @click="inspectContent" /></div>
        </div>
        <div v-if="assessment" class="workflow-card" role="status">
          <p class="workflow-hint">{{ assessment.notice }}</p>
          <div v-for="finding in assessment.findings" :key="finding.code" class="workflow-step"><strong>{{ finding.title }}</strong><p>{{ finding.message }}</p><small>命中片段：{{ finding.evidence.join('；') }}</small></div>
          <p v-if="!assessment.findings.length" class="mt-4">本次未命中已配置的文字提醒，仍需完成全部人工检查。</p>
          <ul v-if="assessment.blockers.length" class="publication-blockers"><li v-for="item in assessment.blockers" :key="item">待完成：{{ item }}</li></ul>
          <p v-else class="mt-4">本地检查项已填写，可保存复核记录。</p>
          <UButton v-for="item in assessment.duplicates" :key="item.id" :label="'查看已有记录：'+item.title" variant="link" @click="w.open(item.id)" />
        </div>
      </template>
      <template v-else>
        <div class="workflow-card"><h3>选一种发布方式</h3><div class="workflow-actions mt-3"><UButton label="自己上传到小红书（最简单）" :variant="publishMethod==='manual'?'solid':'outline'" @click="publishMethod='manual'" /><UButton label="使用辅助填入" :variant="publishMethod==='assist'?'solid':'outline'" @click="publishMethod='assist'" /></div><p class="workflow-hint mt-3">两种方式都需要你在小红书页面点击“发布”。</p></div>
        <XhsPublishAssist v-if="publishMethod==='assist'" :key="record?.id" :record="record" :dirty="dirty || !mediaReady" :selected-media="media" />
        <div v-else class="workflow-card manual-publish"><h3>照这三步发出去</h3><ol class="publication-steps"><li><strong>打开小红书，点“发布图文”</strong><p>登录你要发布的账号，选择“上传图文”。</p><UButton href="https://creator.xiaohongshu.com/publish/publish" target="_blank" rel="noopener noreferrer" label="打开小红书发布页" /></li><li><strong>上传刚才选的图片</strong><p>选择本机原文件并按预览顺序排列，第一张是封面。也可以下载有序文件包，解压后按 01、02… 上传。</p><UButton v-permission="'xhsPublishing:export'" label="下载本次有序配图" variant="outline" :disabled="!media.length" @click="mediaEditor?.download()" /><p v-if="!media.length" class="workflow-hint">本页还没有图片，返回第一步选择，或直接在小红书选择本机图片。</p></li><li><strong>粘贴标题正文，核对后点击“发布”</strong><div class="workflow-actions mt-3"><UButton v-permission="'xhsPublishing:export'" label="复制标题" :disabled="!content?.headline" @click="copyPart('headline')" /><UButton v-permission="'xhsPublishing:export'" label="复制正文和话题" :disabled="!content?.body" @click="copyPart('body')" /></div><p>在小红书核对话题、图片顺序和最终预览，再由你点击发布。成功后即可完成，下面的链接登记可以稍后补。</p></li></ol></div>
        <details class="workflow-card"><summary>查看文案与其他导出方式</summary>
        <div class="workflow-card">
          <h3>手动准备与导出</h3>
          <ol class="publication-steps"><li>核对这里的文案和实际上传的图片或视频。</li><li>打开小红书，确认登录账号、话题和所需标识，再由你点击发布。</li><li>确认笔记发布成功后，回来登记具体链接与实际时间。</li></ol>
          <p class="workflow-hint">平台出现验证或限制时，先按官方提示处理。不要反复重试、批量重复发布或刷量。</p>
          <UAlert v-if="!publicationChecks.every(item=>data[item.key])" title="还有人工检查未完成，请先到“发布前检查”核实。" color="warning" class="my-4" />
          <div class="workflow-preview">{{ text || '尚未填写文案' }}</div>
          <div class="workflow-actions mt-4"><UButton v-permission="'xhsPublishing:export'" label="复制发布文案" :disabled="!text" @click="copyText" /><UButton v-permission="'xhsPublishing:export'" label="下载文案与发布清单" variant="outline" @click="exportChecklist" /><UButton v-permission="'xhsPublishing:export'" v-if="data.source==='linked' && snapshot" label="导出关联笔记配图 ZIP" variant="outline" :loading="exporting" @click="exportImages" /><UButton href="https://creator.xiaohongshu.com/" target="_blank" rel="noopener noreferrer" variant="outline" label="打开小红书创作服务平台" /></div>
        </div></details>
        <details :open="isPublished" class="workflow-card"><summary>已经发成功了？登记链接（可稍后补）</summary><div class="workflow-grid mt-4">
          <label class="workflow-field"><span>状态</span><USelect :disabled="!canPermission('xhsPublishing:' + (record ? 'update' : 'create'))" v-model="data.status" aria-label="发布状态" :items="statusesForEdit.filter(item => canAdmin('xhsPublishing', 'publish') || (item.value === 'published') === (record?.status === 'published'))" /></label>
          <label class="workflow-field"><span>实际发布时间</span><input class="workflow-native" type="datetime-local" aria-label="实际发布时间" :value="dateTimeLocal(data.published_at)" @input="data.published_at=isoDateTime(($event.target as HTMLInputElement).value)" /></label>
          <label class="workflow-field workflow-wide"><span>小红书发布链接</span><UInput :disabled="!canPermission('xhsPublishing:' + (record ? 'update' : 'create'))" v-model="data.url" aria-label="小红书发布链接" maxlength="2000" placeholder="粘贴具体笔记的 HTTPS 链接" /></label>
          <p class="workflow-hint workflow-wide">保存为“已发布”仅登记结果；工作台不会操作你的账号发帖。</p>
          <div class="workflow-actions workflow-wide"><UButton v-permission="'xhsPublishing:publish'" label="登记为已发布" :disabled="busy || isPublished" @click="registerPublished" /><UButton v-permission="'xhsPublishing:' + (record ? 'update' : 'create')" label="保存发布记录" variant="outline" :disabled="busy" @click="save" /><UButton v-permission="'xhsAnalytics:update'" label="保存并记录效果" variant="outline" :disabled="busy || data.status!=='published'" @click="review" /><UButton v-if="record?.data.url" :href="record.data.url" target="_blank" rel="noopener noreferrer" variant="outline" label="打开已发布笔记" /></div>
        </div></details>
      </template>
      <div v-if="record" class="workflow-actions"><XhsWorkflowVersions :record="record" readonly /><UButton v-permission="'xhsPublishing:create'" label="复制为新计划" variant="outline" :disabled="busy" @click="w.duplicate" /></div>
    </template></div>
  </XhsWorkflowFrame>
</template>

<style scoped>
.publication-steps { list-style:decimal;padding-left:22px;margin:16px 0;line-height:1.9; }
.publication-blockers { list-style:disc;padding-left:22px;margin-top:16px;color:var(--ui-text-muted);line-height:1.9; }
.publication-layout { display:grid;gap:18px; }
.quick-publish-intro { display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:16px; }
.review-images { display:flex;gap:12px;overflow:auto;margin-top:16px; }
.review-images img { flex:none;width:140px;height:180px;object-fit:contain;background:var(--ui-bg-muted);border-radius:8px; }
summary { cursor:pointer;font-size:14px;color:var(--ui-text-muted); }
.manual-publish li { margin:20px 0; }
.manual-publish li p { font-size:14px;color:var(--ui-text-muted);margin:8px 0; }
@media(max-width:700px) { .quick-publish-intro { flex-direction:column;align-items:flex-start; } }
</style>
